import uuid
from collections.abc import Sequence
from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from vendoriq.models.order import Order, OrderStatus
from vendoriq.models.payment import PaymentStatus
from vendoriq.models.product import Product


class InventoryService:
    """Service handling atomic inventory reservations, releases, and concurrency safety."""

    async def reserve_inventory(
        self,
        session: AsyncSession,
        items: Sequence[tuple[uuid.UUID, int]],
    ) -> None:
        """Atomically reserve inventory using row-level locking (SELECT ... FOR UPDATE).

        Sorts product IDs to prevent deadlock when concurrent transactions
        request overlapping products.
        """
        if not items:
            return

        # Sort product IDs to ensure deterministic lock acquisition order
        sorted_items = sorted(items, key=lambda x: str(x[0]))
        product_ids = [pid for pid, _ in sorted_items]

        stmt = select(Product).where(Product.id.in_(product_ids)).with_for_update()
        res = await session.execute(stmt)
        products_by_id = {p.id: p for p in res.scalars().all()}

        # Verify all products exist, are active, and have sufficient stock
        for product_id, requested_qty in sorted_items:
            product = products_by_id.get(product_id)
            if not product:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Product '{product_id}' was not found in catalog.",
                )
            if not product.is_active:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Product '{product.name}' is inactive and cannot be purchased.",
                )
            if product.stock < requested_qty:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=(
                        f"Insufficient stock for '{product.name}'. "
                        f"Available: {product.stock}, requested: {requested_qty}."
                    ),
                )

        # Decrement stock to hold reservation
        for product_id, requested_qty in sorted_items:
            product = products_by_id[product_id]
            product.stock -= requested_qty

    async def release_inventory(
        self,
        session: AsyncSession,
        items: Sequence[tuple[uuid.UUID, int]],
    ) -> None:
        """Atomically release reserved inventory back to catalog."""
        if not items:
            return

        sorted_items = sorted(items, key=lambda x: str(x[0]))
        product_ids = [pid for pid, _ in sorted_items if pid is not None]

        if not product_ids:
            return

        stmt = select(Product).where(Product.id.in_(product_ids)).with_for_update()
        res = await session.execute(stmt)
        products_by_id = {p.id: p for p in res.scalars().all()}

        for product_id, release_qty in sorted_items:
            product = products_by_id.get(product_id)
            if product:
                product.stock += release_qty

    async def reconcile_expired_reservations(
        self,
        session: AsyncSession,
    ) -> list[uuid.UUID]:
        """Find pending orders whose reservation TTL has expired, cancel them, and release stock."""
        now = datetime.now(UTC)
        stmt = (
            select(Order)
            .where(
                Order.status == OrderStatus.PENDING_PAYMENT,
                Order.expires_at <= now,
            )
            .options(selectinload(Order.items), selectinload(Order.payment))
            .with_for_update()
        )
        res = await session.execute(stmt)
        expired_orders = list(res.scalars().all())

        cancelled_order_ids: list[uuid.UUID] = []

        for order in expired_orders:
            # Release inventory
            items_to_release = [
                (item.product_id, item.quantity)
                for item in order.items
                if item.product_id is not None
            ]
            await self.release_inventory(session, items_to_release)

            # Update statuses
            order.status = OrderStatus.CANCELLED
            if order.payment:
                order.payment.payment_status = PaymentStatus.CANCELLED
                order.payment.failure_message = "Reservation expired without payment."

            cancelled_order_ids.append(order.id)

        await session.commit()
        return cancelled_order_ids


inventory_service = InventoryService()
