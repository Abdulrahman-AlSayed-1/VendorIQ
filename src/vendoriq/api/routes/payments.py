import uuid

from fastapi import APIRouter, status

from vendoriq.api.deps import CurrentUserDep, SessionDep
from vendoriq.schemas.payment import PaymentRead
from vendoriq.services.order_service import order_service

router = APIRouter(prefix="/payments", tags=["Payments"])


@router.get(
    "/{payment_id}",
    response_model=PaymentRead,
    status_code=status.HTTP_200_OK,
    summary="Get authoritative payment status",
)
async def get_payment_status(
    payment_id: uuid.UUID,
    current_user: CurrentUserDep,
    session: SessionDep,
) -> PaymentRead:
    """Retrieve authoritative database payment status for an order (IDOR protected)."""
    payment = await order_service.get_payment_by_id(
        session=session, payment_id=payment_id, user=current_user
    )
    return PaymentRead.model_validate(payment)
