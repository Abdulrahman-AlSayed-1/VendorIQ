import uuid
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from vendoriq.models.cart import Cart, CartItem
from vendoriq.models.product import Product
from vendoriq.schemas.cart import CartItemAdd, CartItemRead, CartItemUpdate, CartRead


class CartService:
    """Service managing customer shopping cart operations and server-side pricing."""

    async def get_or_create_cart(
        self, session: AsyncSession, user_id: uuid.UUID
    ) -> Cart:
        stmt = select(Cart).where(Cart.user_id == user_id)
        res = await session.execute(stmt)
        cart = res.scalar_one_or_none()

        if not cart:
            cart = Cart(user_id=user_id)
            session.add(cart)
            await session.commit()
            await session.refresh(cart)
        return cart

    async def get_cart_view(
        self, session: AsyncSession, user_id: uuid.UUID
    ) -> CartRead:
        cart = await self.get_or_create_cart(session, user_id)

        # Directly query items with fresh product eager loading
        stmt = (
            select(CartItem)
            .where(CartItem.cart_id == cart.id)
            .options(selectinload(CartItem.product))
            .order_by(CartItem.created_at.asc())
        )
        res = await session.execute(stmt)
        items = list(res.scalars().all())

        items_read: list[CartItemRead] = []
        subtotal = Decimal("0.00")
        item_count = 0

        for item in items:
            product = item.product
            # Server-side pricing: Always use authoritative catalog price
            unit_price = product.price
            line_total = unit_price * item.quantity
            in_stock = product.is_active and (product.stock >= item.quantity)

            items_read.append(
                CartItemRead(
                    id=item.id,
                    product_id=product.id,
                    product_name=product.name,
                    sku=product.sku,
                    unit_price=unit_price,
                    quantity=item.quantity,
                    line_total=line_total,
                    in_stock=in_stock,
                    available_stock=product.stock,
                )
            )
            subtotal += line_total
            item_count += item.quantity

        discount_total = Decimal("0.00")
        grand_total = subtotal - discount_total

        return CartRead(
            id=cart.id,
            items=items_read,
            currency="usd",
            subtotal=subtotal,
            discount_total=discount_total,
            grand_total=grand_total,
            item_count=item_count,
        )

    async def add_item(
        self, session: AsyncSession, user_id: uuid.UUID, data: CartItemAdd
    ) -> CartRead:
        # Validate product exists and is active
        product = await session.get(Product, data.product_id)
        if not product or not product.is_active:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Product not found or is currently inactive.",
            )

        cart = await self.get_or_create_cart(session, user_id)

        # Query existing item directly
        stmt = select(CartItem).where(
            CartItem.cart_id == cart.id,
            CartItem.product_id == data.product_id,
        )
        existing_res = await session.execute(stmt)
        existing_item = existing_res.scalar_one_or_none()

        if existing_item:
            new_quantity = existing_item.quantity + data.quantity
            if new_quantity > product.stock:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=(
                        f"Cannot add {data.quantity} units. Only {product.stock} units "
                        f"available in stock ({existing_item.quantity} already in cart)."
                    ),
                )
            existing_item.quantity = new_quantity
        else:
            if data.quantity > product.stock:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Requested quantity ({data.quantity}) exceeds available stock ({product.stock}).",
                )
            new_item = CartItem(
                cart_id=cart.id,
                product_id=product.id,
                quantity=data.quantity,
            )
            session.add(new_item)

        await session.commit()
        return await self.get_cart_view(session, user_id)

    async def update_item(
        self,
        session: AsyncSession,
        user_id: uuid.UUID,
        item_id: uuid.UUID,
        data: CartItemUpdate,
    ) -> CartRead:
        cart = await self.get_or_create_cart(session, user_id)

        stmt = (
            select(CartItem)
            .where(CartItem.id == item_id, CartItem.cart_id == cart.id)
            .options(selectinload(CartItem.product))
        )
        res = await session.execute(stmt)
        item = res.scalar_one_or_none()

        if not item:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Cart item '{item_id}' not found in your cart.",
            )

        product = item.product
        if data.quantity > product.stock:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Requested quantity ({data.quantity}) exceeds available stock ({product.stock}).",
            )

        item.quantity = data.quantity
        await session.commit()
        return await self.get_cart_view(session, user_id)

    async def remove_item(
        self, session: AsyncSession, user_id: uuid.UUID, item_id: uuid.UUID
    ) -> CartRead:
        cart = await self.get_or_create_cart(session, user_id)

        stmt = select(CartItem).where(
            CartItem.id == item_id, CartItem.cart_id == cart.id
        )
        res = await session.execute(stmt)
        item = res.scalar_one_or_none()

        if not item:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Cart item '{item_id}' not found in your cart.",
            )

        await session.delete(item)
        await session.commit()
        return await self.get_cart_view(session, user_id)

    async def clear_cart(self, session: AsyncSession, user_id: uuid.UUID) -> CartRead:
        cart = await self.get_or_create_cart(session, user_id)
        stmt = delete(CartItem).where(CartItem.cart_id == cart.id)
        await session.execute(stmt)
        await session.commit()
        return await self.get_cart_view(session, user_id)


cart_service = CartService()
