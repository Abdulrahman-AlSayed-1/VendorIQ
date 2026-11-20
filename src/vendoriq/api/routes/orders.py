import uuid
from typing import Annotated

from fastapi import APIRouter, Query, status

from vendoriq.api.deps import CurrentUserDep, SessionDep
from vendoriq.models.order import OrderStatus
from vendoriq.schemas.order import OrderPaginationResponse, OrderRead
from vendoriq.services.order_service import order_service

router = APIRouter(prefix="/orders", tags=["Orders"])


@router.get(
    "",
    response_model=OrderPaginationResponse,
    status_code=status.HTTP_200_OK,
    summary="List authenticated customer's order history",
)
async def list_customer_orders(
    current_user: CurrentUserDep,
    session: SessionDep,
    order_status: Annotated[
        OrderStatus | None,
        Query(description="Filter by order status"),
    ] = None,
    page: Annotated[int, Query(ge=1, description="Page number")] = 1,
    page_size: Annotated[int, Query(ge=1, le=100, description="Items per page")] = 20,
) -> OrderPaginationResponse:
    """Retrieve paginated order history for the current customer."""
    orders, total, total_pages = await order_service.get_customer_orders(
        session=session,
        user_id=current_user.id,
        status_filter=order_status,
        page=page,
        page_size=page_size,
    )
    return OrderPaginationResponse(
        items=orders,  # type: ignore[arg-type]
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


@router.get(
    "/{order_id}",
    response_model=OrderRead,
    status_code=status.HTTP_200_OK,
    summary="Get customer order details by ID",
)
async def get_customer_order(
    order_id: uuid.UUID,
    current_user: CurrentUserDep,
    session: SessionDep,
) -> OrderRead:
    """Retrieve detailed order information including immutable item snapshots (IDOR protected)."""
    order = await order_service.get_order_by_id(
        session=session, order_id=order_id, user=current_user
    )
    return OrderRead.model_validate(order)


@router.post(
    "/{order_id}/cancel",
    response_model=OrderRead,
    status_code=status.HTTP_200_OK,
    summary="Cancel a pending order and release reserved inventory",
)
async def cancel_customer_order(
    order_id: uuid.UUID,
    current_user: CurrentUserDep,
    session: SessionDep,
) -> OrderRead:
    """Cancel a pending unpaid order, atomically releasing the reserved stock back to the catalog."""
    order = await order_service.cancel_customer_order(
        session=session, order_id=order_id, user=current_user
    )
    return OrderRead.model_validate(order)
