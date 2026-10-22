from fastapi import APIRouter, status

from vendoriq.api.deps import CurrentUserDep, SessionDep
from vendoriq.schemas.checkout import CheckoutSessionResponse
from vendoriq.services.checkout_service import checkout_service

router = APIRouter(prefix="/checkout", tags=["Checkout"])


@router.post(
    "/sessions",
    response_model=CheckoutSessionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Initiate Stripe Checkout session from active shopping cart",
)
async def create_checkout_session(
    current_user: CurrentUserDep,
    session: SessionDep,
) -> CheckoutSessionResponse:
    """Validate cart and inventory, create pending order and payment, and generate a Stripe Checkout Session."""
    return await checkout_service.initiate_checkout(session=session, user=current_user)
