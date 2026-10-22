import math
import uuid

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from vendoriq.models.order import Order, OrderStatus
from vendoriq.models.payment import Payment, PaymentStatus
from vendoriq.models.user import User, UserRole
from vendoriq.services.inventory_service import inventory_service


class OrderService:
    """Service handling order retrieval, lifecycle transitions, and customer authorization."""

    # -------------------------------------------------------------------------
    # Customer Order Operations (Strict IDOR Scoping)
    # -------------------------------------------------------------------------
    async def get_customer_orders(
        self,
        session: AsyncSession,
        user_id: uuid.UUID,
        status_filter: OrderStatus | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[Order], int, int]:
        stmt = (
            select(Order)
            .where(Order.user_id == user_id)
            .options(selectinload(Order.items))
            .order_by(Order.created_at.desc())
        )
        count_stmt = select(func.count(Order.id)).where(Order.user_id == user_id)

        if status_filter:
            stmt = stmt.where(Order.status == status_filter)
            count_stmt = count_stmt.where(Order.status == status_filter)

        total_res = await session.execute(count_stmt)
        total = total_res.scalar_one() or 0
        total_pages = math.ceil(total / page_size) if total > 0 else 1

        offset = (page - 1) * page_size
        stmt = stmt.offset(offset).limit(page_size)

        res = await session.execute(stmt)
        orders = list(res.scalars().all())
        return orders, total, total_pages

    async def get_order_by_id(
        self,
        session: AsyncSession,
        order_id: uuid.UUID,
        user: User,
    ) -> Order:
        stmt = (
            select(Order)
            .where(Order.id == order_id)
            .options(selectinload(Order.items), selectinload(Order.payment))
        )
        order = (await session.execute(stmt)).scalar_one_or_none()

        if not order:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Order '{order_id}' was not found.",
            )

        # IDOR barrier: Customer can only view their own order
        if user.role != UserRole.ADMIN and order.user_id != user.id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Order '{order_id}' was not found.",
            )

        return order

    async def cancel_customer_order(
        self,
        session: AsyncSession,
        order_id: uuid.UUID,
        user: User,
    ) -> Order:
        order = await self.get_order_by_id(session, order_id, user)

        # Customers can only cancel while status == PENDING_PAYMENT
        if order.status != OrderStatus.PENDING_PAYMENT:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"Order cannot be cancelled in '{order.status.value}' status. "
                    "Only pending unpaid orders can be cancelled by customers."
                ),
            )

        # Release reserved inventory
        items_to_release = [
            (item.product_id, item.quantity)
            for item in order.items
            if item.product_id is not None
        ]
        await inventory_service.release_inventory(session, items_to_release)

        order.status = OrderStatus.CANCELLED
        if order.payment:
            order.payment.payment_status = PaymentStatus.CANCELLED
            order.payment.failure_message = "Order cancelled by customer."

        await session.commit()
        await session.refresh(order)
        return order

    async def get_payment_by_id(
        self,
        session: AsyncSession,
        payment_id: uuid.UUID,
        user: User,
    ) -> Payment:
        stmt = (
            select(Payment)
            .where(Payment.id == payment_id)
            .options(selectinload(Payment.order))
        )
        payment = (await session.execute(stmt)).scalar_one_or_none()

        if not payment:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Payment '{payment_id}' was not found.",
            )

        # IDOR barrier
        if user.role != UserRole.ADMIN and payment.order.user_id != user.id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Payment '{payment_id}' was not found.",
            )

        return payment

    # -------------------------------------------------------------------------
    # Administrator Order Operations
    # -------------------------------------------------------------------------
    async def get_all_orders_admin(
        self,
        session: AsyncSession,
        status_filter: OrderStatus | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[Order], int, int]:
        stmt = (
            select(Order)
            .options(selectinload(Order.items), selectinload(Order.payment))
            .order_by(Order.created_at.desc())
        )
        count_stmt = select(func.count(Order.id))

        if status_filter:
            stmt = stmt.where(Order.status == status_filter)
            count_stmt = count_stmt.where(Order.status == status_filter)

        total_res = await session.execute(count_stmt)
        total = total_res.scalar_one() or 0
        total_pages = math.ceil(total / page_size) if total > 0 else 1

        offset = (page - 1) * page_size
        stmt = stmt.offset(offset).limit(page_size)

        orders = list((await session.execute(stmt)).scalars().all())
        return orders, total, total_pages

    async def update_order_status_admin(
        self,
        session: AsyncSession,
        order_id: uuid.UUID,
        new_status: OrderStatus,
    ) -> Order:
        stmt = (
            select(Order)
            .where(Order.id == order_id)
            .options(selectinload(Order.items), selectinload(Order.payment))
        )
        order = (await session.execute(stmt)).scalar_one_or_none()

        if not order:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Order '{order_id}' was not found.",
            )

        current = order.status

        # Legal state transitions mapping
        valid_transitions = {
            OrderStatus.PENDING_PAYMENT: {OrderStatus.PAID, OrderStatus.CANCELLED},
            OrderStatus.PAID: {OrderStatus.PROCESSING, OrderStatus.CANCELLED},
            OrderStatus.PROCESSING: {OrderStatus.SHIPPED, OrderStatus.CANCELLED},
            OrderStatus.SHIPPED: {OrderStatus.DELIVERED},
            OrderStatus.DELIVERED: set(),
            OrderStatus.CANCELLED: set(),
        }

        if new_status not in valid_transitions.get(current, set()):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Illegal order transition from '{current.value}' to '{new_status.value}'.",
            )

        # If transitioning to CANCELLED, release stock
        if new_status == OrderStatus.CANCELLED:
            items_to_release = [
                (item.product_id, item.quantity)
                for item in order.items
                if item.product_id is not None
            ]
            await inventory_service.release_inventory(session, items_to_release)
            if order.payment:
                order.payment.payment_status = PaymentStatus.CANCELLED
                order.payment.failure_message = "Order cancelled by administrator."

        order.status = new_status
        await session.commit()
        await session.refresh(order)
        return order


order_service = OrderService()
