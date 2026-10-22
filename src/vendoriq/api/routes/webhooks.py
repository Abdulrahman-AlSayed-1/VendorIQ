from fastapi import APIRouter, Header, HTTPException, Request, status

from vendoriq.api.deps import SessionDep
from vendoriq.services.payment_service import payment_service
from vendoriq.services.webhook_service import webhook_service

router = APIRouter(prefix="/webhooks", tags=["Webhooks"])


@router.post(
    "/stripe",
    status_code=status.HTTP_200_OK,
    summary="Receive and verify Stripe webhook events",
)
async def stripe_webhook(
    request: Request,
    session: SessionDep,
    stripe_signature: str = Header(None, alias="stripe-signature"),
):
    """Receive raw Stripe webhook payload, verify HMAC signature, and process event idempotently."""
    if not stripe_signature:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing stripe-signature header.",
        )

    # Read raw request body bytes for HMAC verification
    payload_bytes = await request.body()

    # Verify signature
    event = payment_service.verify_webhook_signature(
        payload_bytes=payload_bytes,
        signature_header=stripe_signature,
    )

    # Idempotent processing
    return await webhook_service.process_stripe_event(session, event)
