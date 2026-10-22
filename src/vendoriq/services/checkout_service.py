import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from vendoriq.core.config import settings
from vendoriq.models.cart import Cart, CartItem
from vendoriq.models.order import Order, OrderItem, OrderStatus
from vendoriq.models.payment import Payment, PaymentStatus
from vendoriq.models.user import User
from vendoriq.schemas.checkout import CheckoutSessionResponse
from vendoriq.services.inventory_service import inventory_service
from vendoriq.services.payment_service import payment_service


class CheckoutService:
    """Service orchestrating the checkout flow, inventory reservations, and Stripe Sessions."""

    @staticmethod
    def generate_order_number() -> str:
        date_str = datetime.now(UTC).strftime("%Y%m%d")
        suffix = uuid.uuid4().hex[:6].upper()
        return f"ORD-{date_str}-{suffix}"

    async def initiate_checkout(
        self,
        session: AsyncSession,
        user: User,
    ) -> CheckoutSessionResponse:
        # 1. Load active cart and items
        cart_stmt = (
            select(Cart)
            .where(Cart.user_id == user.id)
            .options(selectinload(Cart.items).selectinload(CartItem.product))
        )
        cart_res = await session.execute(cart_stmt)
        cart = cart_res.scalar_one_or_none()

        if not cart or not cart.items:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot checkout with an empty shopping cart.",
            )

        # Collect items to reserve
        items_to_reserve = [(item.product_id, item.quantity) for item in cart.items]

        # 2. Transaction 1: Reserve stock, create Order & OrderItems, clear cart
        order_id = uuid.uuid4()
        order_number = self.generate_order_number()
        expires_at = datetime.now(UTC) + timedelta(
            minutes=settings.CHECKOUT_RESERVATION_MINUTES
        )

        subtotal = Decimal("0.00")
        order_items: list[OrderItem] = []

        # Lock and reserve stock atomically
        await inventory_service.reserve_inventory(session, items_to_reserve)

        for item in cart.items:
            product = item.product
            unit_price = product.price
            line_total = unit_price * item.quantity
            subtotal += line_total

            order_items.append(
                OrderItem(
                    order_id=order_id,
                    product_id=product.id,
                    product_name_snapshot=product.name,
                    sku_snapshot=product.sku,
                    unit_price_snapshot=unit_price,
                    quantity=item.quantity,
                    line_total=line_total,
                )
            )

        discount = Decimal("0.00")
        total = subtotal - discount

        order = Order(
            id=order_id,
            order_number=order_number,
            user_id=user.id,
            status=OrderStatus.PENDING_PAYMENT,
            currency="usd",
            subtotal=subtotal,
            discount=discount,
            total=total,
            expires_at=expires_at,
        )
        order.items = order_items

        session.add(order)

        # Clear customer's active cart immediately
        await session.execute(delete(CartItem).where(CartItem.cart_id == cart.id))

        # Commit Transaction 1 before calling external payment gateway
        await session.commit()
        await session.refresh(order)

        # 3. External Call: Create Stripe Checkout Session (OUTSIDE DB Transaction)
        try:
            stripe_session = payment_service.create_checkout_session(
                order=order,
                customer_email=user.email,
            )
        except Exception:
            # Compensating transaction: release inventory and cancel pending order
            await inventory_service.release_inventory(session, items_to_reserve)
            order.status = OrderStatus.CANCELLED
            await session.commit()
            raise

        # 4. Transaction 2: Persist Payment record with Stripe Session ID
        payment_id = uuid.uuid4()
        payment = Payment(
            id=payment_id,
            order_id=order.id,
            payment_provider="stripe",
            payment_status=PaymentStatus.PENDING,
            amount=order.total,
            currency=order.currency,
            stripe_checkout_session_id=stripe_session.id,
        )
        session.add(payment)
        await session.commit()

        return CheckoutSessionResponse(
            order_id=order.id,
            order_number=order.order_number,
            payment_id=payment.id,
            stripe_checkout_session_id=stripe_session.id,
            checkout_url=stripe_session.url or "",
            expires_at=order.expires_at,
        )


checkout_service = CheckoutService()
