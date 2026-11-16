from decimal import Decimal
from typing import Any

import stripe
from fastapi import HTTPException, status
from stripe import StripeError

from vendoriq.core.config import settings
from vendoriq.models.order import Order


class PaymentService:
    """Payment abstraction layer encapsulating all Stripe SDK operations."""

    def __init__(self) -> None:
        stripe.api_key = settings.STRIPE_SECRET_KEY

    @staticmethod
    def decimal_to_cents(amount: Decimal) -> int:
        """Convert Decimal monetary amount to integer cents for Stripe."""
        return int(amount * 100)

    def create_checkout_session(
        self,
        order: Order,
        customer_email: str,
    ) -> stripe.checkout.Session:
        """Create a Stripe-hosted Checkout Session with fully itemized line items."""
        stripe.api_key = settings.STRIPE_SECRET_KEY

        # Construct itemized line items
        line_items: list[dict[str, Any]] = []
        for item in order.items:
            unit_amount_cents = self.decimal_to_cents(item.unit_price_snapshot)
            line_items.append(
                {
                    "price_data": {
                        "currency": order.currency.lower(),
                        "unit_amount": unit_amount_cents,
                        "product_data": {
                            "name": item.product_name_snapshot,
                            "metadata": {
                                "sku": item.sku_snapshot,
                            },
                        },
                    },
                    "quantity": item.quantity,
                }
            )

        # Build idempotency key derived deterministically from internal order ID
        idempotency_key = f"checkout_session_{order.id}"

        # Stripe expires_at must be at least 30 minutes in future and within 24 hours
        expires_timestamp = int(order.expires_at.timestamp())

        try:
            session = stripe.checkout.Session.create(
                mode="payment",
                customer_email=customer_email,
                client_reference_id=str(order.id),
                line_items=line_items,
                metadata={
                    "order_id": str(order.id),
                    "order_number": order.order_number,
                },
                expires_at=expires_timestamp,
                success_url=f"{settings.STRIPE_SUCCESS_URL}?session_id={{CHECKOUT_SESSION_ID}}",
                cancel_url=settings.STRIPE_CANCEL_URL,
                idempotency_key=idempotency_key,
            )
            return session
        except StripeError as e:
            # Mask internal gateway details from client
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Payment gateway error: {e.user_message or 'Unable to initiate checkout session.'}",
            )

    def verify_webhook_signature(
        self,
        payload_bytes: bytes,
        signature_header: str,
    ) -> stripe.Event:
        """Verify the raw HTTP webhook signature using Stripe's official verification utility."""
        try:
            event = stripe.Webhook.construct_event(
                payload=payload_bytes,
                sig_header=signature_header,
                secret=settings.STRIPE_WEBHOOK_SECRET,
            )
            return event
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid webhook payload.",
            )
        except stripe.SignatureVerificationError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid webhook signature.",
            )


payment_service = PaymentService()
