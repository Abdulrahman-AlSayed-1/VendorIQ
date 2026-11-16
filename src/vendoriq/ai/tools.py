import uuid
from decimal import Decimal
from typing import Any

from fastapi import HTTPException

from vendoriq.core.db import async_session_maker
from vendoriq.models.user import User
from vendoriq.schemas.cart import CartItemAdd, CartItemUpdate
from vendoriq.services.cart_service import cart_service
from vendoriq.services.checkout_service import checkout_service
from vendoriq.services.order_service import order_service
from vendoriq.services.product_service import product_service


class CustomerTools:
    """Encapsulates all domain function tools bound to a specific customer session."""

    def __init__(self, user: User) -> None:
        self.user = user

    async def list_categories(self) -> list[dict[str, Any]]:
        """List all available product categories in the catalog."""
        async with async_session_maker() as session:
            try:
                categories = await product_service.get_categories(session)
                return [
                    {
                        "id": str(c.id),
                        "name": c.name,
                        "slug": c.slug,
                        "description": c.description or "",
                    }
                    for c in categories
                ]
            except Exception as exc:  # noqa: BLE001
                return [{"error": str(exc)}]

    async def search_products(
        self,
        query: str = "",
        category_slug: str = "",
        min_price: float | None = None,
        max_price: float | None = None,
        in_stock_only: bool = True,
    ) -> dict[str, Any]:
        """Search products in the store catalog with optional filters for name, category, and price range.

        Args:
            query: Keyword search term matching product name, brand, or description.
            category_slug: Filter by category slug (e.g. 'audio', 'computing').
            min_price: Minimum price filter in USD.
            max_price: Maximum price filter in USD.
            in_stock_only: Filter only products currently in stock (default True).
        """
        async with async_session_maker() as session:
            try:
                min_p = Decimal(str(min_price)) if min_price is not None else None
                max_p = Decimal(str(max_price)) if max_price is not None else None
                products, total, _pages = await product_service.get_products(
                    session=session,
                    search=query if query else None,
                    category_slug=category_slug if category_slug else None,
                    min_price=min_p,
                    max_price=max_p,
                    in_stock=True if in_stock_only else None,
                    page=1,
                    page_size=15,
                )
                return {
                    "total_found": total,
                    "products": [
                        {
                            "id": str(p.id),
                            "name": p.name,
                            "sku": p.sku,
                            "brand": p.brand,
                            "price": float(p.price),
                            "stock": p.stock,
                            "category": p.category.name
                            if p.category
                            else "Uncategorized",
                        }
                        for p in products
                    ],
                }
            except Exception as exc:  # noqa: BLE001
                return {"error": str(exc)}

    async def get_product_details(self, product_id_or_slug: str) -> dict[str, Any]:
        """Get full details of a specific product by its UUID or unique slug.

        Args:
            product_id_or_slug: The product UUID or URL slug.
        """
        async with async_session_maker() as session:
            try:
                product = await product_service.get_product_by_id_or_slug(
                    session=session, id_or_slug=product_id_or_slug
                )
                return {
                    "id": str(product.id),
                    "name": product.name,
                    "slug": product.slug,
                    "sku": product.sku,
                    "brand": product.brand,
                    "description": product.description,
                    "price": float(product.price),
                    "stock": product.stock,
                    "in_stock": product.stock > 0,
                    "attributes": product.attributes or {},
                    "category": product.category.name
                    if product.category
                    else "Uncategorized",
                }
            except HTTPException as exc:
                return {"error": exc.detail}
            except Exception as exc:  # noqa: BLE001
                return {"error": str(exc)}

    async def get_cart(self) -> dict[str, Any]:
        """View the customer's current shopping cart, including all items, quantities, and totals."""
        async with async_session_maker() as session:
            try:
                cart = await cart_service.get_cart_view(
                    session=session, user_id=self.user.id
                )
                return {
                    "item_count": cart.item_count,
                    "subtotal": float(cart.subtotal),
                    "grand_total": float(cart.grand_total),
                    "currency": cart.currency,
                    "items": [
                        {
                            "item_id": str(item.id),
                            "product_id": str(item.product_id),
                            "product_name": item.product_name,
                            "sku": item.sku,
                            "quantity": item.quantity,
                            "unit_price": float(item.unit_price),
                            "line_total": float(item.line_total),
                            "in_stock": item.in_stock,
                            "available_stock": item.available_stock,
                        }
                        for item in cart.items
                    ],
                }
            except Exception as exc:  # noqa: BLE001
                return {"error": str(exc)}

    async def add_to_cart(self, product_id: str, quantity: int = 1) -> dict[str, Any]:
        """Add a product to the customer's shopping cart by product ID with the requested quantity.

        Args:
            product_id: UUID of the product to add.
            quantity: Number of units to add (must be at least 1).
        """
        async with async_session_maker() as session:
            try:
                parsed_id = uuid.UUID(product_id)
                cart_view = await cart_service.add_item(
                    session=session,
                    user_id=self.user.id,
                    data=CartItemAdd(product_id=parsed_id, quantity=max(1, quantity)),
                )
                return {
                    "status": "success",
                    "message": f"Successfully added {quantity} unit(s) to cart.",
                    "cart_item_count": cart_view.item_count,
                    "grand_total": float(cart_view.grand_total),
                }
            except ValueError:
                return {"error": f"Invalid product ID format: '{product_id}'."}
            except HTTPException as exc:
                return {"error": exc.detail}
            except Exception as exc:  # noqa: BLE001
                return {"error": str(exc)}

    async def update_cart_item(self, item_id: str, quantity: int) -> dict[str, Any]:
        """Update the quantity of an item already in the cart. If quantity is 0 or less, removes it.

        Args:
            item_id: The cart item ID (UUID) from the cart view.
            quantity: The new target quantity.
        """
        async with async_session_maker() as session:
            try:
                parsed_id = uuid.UUID(item_id)
                if quantity <= 0:
                    cart_view = await cart_service.remove_item(
                        session=session, user_id=self.user.id, item_id=parsed_id
                    )
                    return {
                        "status": "success",
                        "message": "Item removed from cart.",
                        "cart_item_count": cart_view.item_count,
                        "grand_total": float(cart_view.grand_total),
                    }

                cart_view = await cart_service.update_item(
                    session=session,
                    user_id=self.user.id,
                    item_id=parsed_id,
                    data=CartItemUpdate(quantity=quantity),
                )
                return {
                    "status": "success",
                    "message": f"Updated quantity to {quantity}.",
                    "cart_item_count": cart_view.item_count,
                    "grand_total": float(cart_view.grand_total),
                }
            except ValueError:
                return {"error": f"Invalid item ID format: '{item_id}'."}
            except HTTPException as exc:
                return {"error": exc.detail}
            except Exception as exc:  # noqa: BLE001
                return {"error": str(exc)}

    async def remove_from_cart(self, item_id: str) -> dict[str, Any]:
        """Remove an item from the customer's cart by cart item ID.

        Args:
            item_id: The cart item ID (UUID) to remove.
        """
        return await self.update_cart_item(item_id=item_id, quantity=0)

    async def clear_cart(self) -> dict[str, Any]:
        """Empty all items currently in the shopping cart."""
        async with async_session_maker() as session:
            try:
                await cart_service.clear_cart(session=session, user_id=self.user.id)
                return {
                    "status": "success",
                    "message": "Shopping cart has been emptied.",
                }
            except Exception as exc:  # noqa: BLE001
                return {"error": str(exc)}

    async def create_checkout(self) -> dict[str, Any]:
        """Proceed to checkout with all items in the shopping cart.

        Reserves inventory stock for 30 minutes and generates a secure Stripe Checkout URL.
        """
        async with async_session_maker() as session:
            try:
                checkout_res = await checkout_service.initiate_checkout(
                    session=session, user=self.user
                )
                return {
                    "status": "success",
                    "order_number": checkout_res.order_number,
                    "checkout_url": checkout_res.checkout_url,
                    "expires_at": checkout_res.expires_at.isoformat(),
                    "message": (
                        f"Order {checkout_res.order_number} initiated. "
                        f"Items are reserved for 30 minutes. "
                        f"Payment link: {checkout_res.checkout_url}"
                    ),
                }
            except HTTPException as exc:
                return {"error": exc.detail}
            except Exception as exc:  # noqa: BLE001
                return {"error": str(exc)}

    async def check_order_status(self, order_id_or_number: str) -> dict[str, Any]:
        """Check the status, payment, and items for an order by order UUID or order number.

        Args:
            order_id_or_number: Order UUID or public tracking number (e.g. 'ORD-20261116-XXXXXX').
        """
        async with async_session_maker() as session:
            try:
                order = await order_service.get_order_by_id_or_number(
                    session=session, identifier=order_id_or_number, user=self.user
                )
                return {
                    "order_number": order.order_number,
                    "status": order.status.value,
                    "total": float(order.total),
                    "currency": order.currency,
                    "created_at": order.created_at.isoformat(),
                    "payment_status": order.payment.payment_status.value
                    if order.payment
                    else "unpaid",
                    "items": [
                        {
                            "name": item.product_name_snapshot,
                            "sku": item.sku_snapshot,
                            "quantity": item.quantity,
                            "unit_price": float(item.unit_price_snapshot),
                            "line_total": float(item.line_total),
                        }
                        for item in order.items
                    ],
                }
            except HTTPException as exc:
                return {"error": exc.detail}
            except Exception as exc:  # noqa: BLE001
                return {"error": str(exc)}

    async def list_order_history(self, page: int = 1) -> dict[str, Any]:
        """List the customer's previous order history with order numbers and statuses."""
        async with async_session_maker() as session:
            try:
                orders, total, total_pages = await order_service.get_customer_orders(
                    session=session,
                    user_id=self.user.id,
                    page=max(1, page),
                    page_size=10,
                )
                return {
                    "total_orders": total,
                    "page": page,
                    "total_pages": total_pages,
                    "orders": [
                        {
                            "order_number": o.order_number,
                            "status": o.status.value,
                            "total": float(o.total),
                            "currency": o.currency,
                            "created_at": o.created_at.isoformat(),
                            "item_count": len(o.items),
                        }
                        for o in orders
                    ],
                }
            except Exception as exc:  # noqa: BLE001
                return {"error": str(exc)}

    async def cancel_order(self, order_id_or_number: str) -> dict[str, Any]:
        """Cancel a pending unpaid order and release reserved stock.

        Args:
            order_id_or_number: Order UUID or order number.
        """
        async with async_session_maker() as session:
            try:
                order = await order_service.get_order_by_id_or_number(
                    session=session, identifier=order_id_or_number, user=self.user
                )
                cancelled_order = await order_service.cancel_customer_order(
                    session=session, order_id=order.id, user=self.user
                )
                return {
                    "status": "success",
                    "message": f"Order {cancelled_order.order_number} has been cancelled and stock released.",
                    "order_status": cancelled_order.status.value,
                }
            except HTTPException as exc:
                return {"error": exc.detail}
            except Exception as exc:  # noqa: BLE001
                return {"error": str(exc)}

    def get_tool_callables(self) -> list[Any]:
        """Return the list of bound callable methods to register with Gemini."""
        return [
            self.list_categories,
            self.search_products,
            self.get_product_details,
            self.get_cart,
            self.add_to_cart,
            self.update_cart_item,
            self.remove_from_cart,
            self.clear_cart,
            self.create_checkout,
            self.check_order_status,
            self.list_order_history,
            self.cancel_order,
        ]
