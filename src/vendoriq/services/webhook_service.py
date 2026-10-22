from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from vendoriq.models.order import Order, OrderStatus
from vendoriq.models.payment import Payment, PaymentStatus
from vendoriq.models.webhook_event import StripeWebhookEvent, WebhookEventStatus
from vendoriq.services.inventory_service import inventory_service


class WebhookService:
    """Service handling idempotent processing of verified Stripe webhook events."""

    async def process_stripe_event(
        self,
        session: AsyncSession,
        event: dict[str, Any],
    ) -> dict[str, str]:
        event_id = event["id"]
        event_type = event["type"]
        data_object = event.get("data", {}).get("object", {})

        # 1. Idempotency Check: Query event ledger
        stmt = select(StripeWebhookEvent).where(
            StripeWebhookEvent.stripe_event_id == event_id
        )
        existing_event = (await session.execute(stmt)).scalar_one_or_none()

        if (
            existing_event
            and existing_event.processing_status == WebhookEventStatus.PROCESSED
        ):
            return {"status": "already_processed", "event_id": event_id}

        if not existing_event:
            webhook_record = StripeWebhookEvent(
                stripe_event_id=event_id,
                event_type=event_type,
                processing_status=WebhookEventStatus.PENDING,
                payload=event,
            )
            session.add(webhook_record)
            await session.commit()
            await session.refresh(webhook_record)
        else:
            webhook_record = existing_event

        # 2. Dispatch event to state handlers
        try:
            if event_type == "checkout.session.completed":
                await self._handle_checkout_session_completed(session, data_object)
            elif event_type == "checkout.session.async_payment_succeeded":
                await self._handle_async_payment_succeeded(session, data_object)
            elif event_type == "checkout.session.async_payment_failed":
                await self._handle_async_payment_failed(session, data_object)
            elif event_type == "checkout.session.expired":
                await self._handle_checkout_session_expired(session, data_object)
            elif event_type == "payment_intent.payment_failed":
                await self._handle_payment_intent_failed(session, data_object)

            # Mark processed
            webhook_record.processing_status = WebhookEventStatus.PROCESSED
            webhook_record.error_message = None
            await session.commit()
            return {"status": "success", "event_id": event_id}

        except Exception as e:
            # Mark failed and commit failure state
            webhook_record.processing_status = WebhookEventStatus.FAILED
            webhook_record.error_message = str(e)
            await session.commit()
            # Return HTTP 500 to trigger Stripe's automatic exponential retry
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Internal error processing webhook event.",
            ) from e

    async def _handle_checkout_session_completed(
        self, session: AsyncSession, session_obj: dict[str, Any]
    ) -> None:
        session_id = session_obj.get("id")
        payment_status_str = session_obj.get("payment_status")
        payment_intent_id = session_obj.get("payment_intent")

        stmt = (
            select(Payment)
            .where(Payment.stripe_checkout_session_id == session_id)
            .options(selectinload(Payment.order))
        )
        payment = (await session.execute(stmt)).scalar_one_or_none()
        if not payment:
            return

        if payment_intent_id and isinstance(payment_intent_id, str):
            payment.stripe_payment_intent_id = payment_intent_id

        # Authoritative check: Only mark paid if Stripe confirms payment_status == 'paid'
        if payment_status_str == "paid":
            payment.payment_status = PaymentStatus.SUCCEEDED
            if payment.order.status == OrderStatus.PENDING_PAYMENT:
                payment.order.status = OrderStatus.PAID
                payment.order.expires_at = (
                    payment.order.expires_at
                )  # Reservation finalized

    async def _handle_async_payment_succeeded(
        self, session: AsyncSession, session_obj: dict[str, Any]
    ) -> None:
        session_id = session_obj.get("id")
        stmt = (
            select(Payment)
            .where(Payment.stripe_checkout_session_id == session_id)
            .options(selectinload(Payment.order))
        )
        payment = (await session.execute(stmt)).scalar_one_or_none()
        if payment:
            payment.payment_status = PaymentStatus.SUCCEEDED
            if payment.order.status == OrderStatus.PENDING_PAYMENT:
                payment.order.status = OrderStatus.PAID

    async def _handle_async_payment_failed(
        self, session: AsyncSession, session_obj: dict[str, Any]
    ) -> None:
        session_id = session_obj.get("id")
        stmt = (
            select(Payment)
            .where(Payment.stripe_checkout_session_id == session_id)
            .options(selectinload(Payment.order).selectinload(Order.items))
        )
        payment = (await session.execute(stmt)).scalar_one_or_none()
        if payment and payment.order.status == OrderStatus.PENDING_PAYMENT:
            payment.payment_status = PaymentStatus.FAILED
            payment.order.status = OrderStatus.CANCELLED
            # Release inventory reservation
            items_to_release = [
                (item.product_id, item.quantity)
                for item in payment.order.items
                if item.product_id is not None
            ]
            await inventory_service.release_inventory(session, items_to_release)

    async def _handle_checkout_session_expired(
        self, session: AsyncSession, session_obj: dict[str, Any]
    ) -> None:
        session_id = session_obj.get("id")
        stmt = (
            select(Payment)
            .where(Payment.stripe_checkout_session_id == session_id)
            .options(selectinload(Payment.order).selectinload(Order.items))
        )
        payment = (await session.execute(stmt)).scalar_one_or_none()
        if payment and payment.order.status == OrderStatus.PENDING_PAYMENT:
            payment.payment_status = PaymentStatus.CANCELLED
            payment.failure_message = "Stripe Checkout session expired."
            payment.order.status = OrderStatus.CANCELLED
            # Release inventory reservation
            items_to_release = [
                (item.product_id, item.quantity)
                for item in payment.order.items
                if item.product_id is not None
            ]
            await inventory_service.release_inventory(session, items_to_release)

    async def _handle_payment_intent_failed(
        self, session: AsyncSession, pi_obj: dict[str, Any]
    ) -> None:
        pi_id = pi_obj.get("id")
        stmt = select(Payment).where(Payment.stripe_payment_intent_id == pi_id)
        payment = (await session.execute(stmt)).scalar_one_or_none()
        if payment:
            payment.payment_status = PaymentStatus.FAILED
            last_err = pi_obj.get("last_payment_error", {})
            payment.failure_message = last_err.get("message", "Payment failed.")


webhook_service = WebhookService()
