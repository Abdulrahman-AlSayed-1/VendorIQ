import uuid

from fastapi import APIRouter, status

from vendoriq.api.deps import CurrentUserDep, SessionDep
from vendoriq.schemas.cart import CartItemAdd, CartItemUpdate, CartRead
from vendoriq.services.cart_service import cart_service

router = APIRouter(prefix="/cart", tags=["Shopping Cart"])


@router.get(
    "",
    response_model=CartRead,
    status_code=status.HTTP_200_OK,
    summary="Retrieve current customer's shopping cart",
)
async def get_cart(
    current_user: CurrentUserDep,
    session: SessionDep,
) -> CartRead:
    """Retrieve the authenticated customer's shopping cart with recalculated totals."""
    return await cart_service.get_cart_view(session=session, user_id=current_user.id)


@router.post(
    "/items",
    response_model=CartRead,
    status_code=status.HTTP_201_CREATED,
    summary="Add product to shopping cart",
)
async def add_item_to_cart(
    data: CartItemAdd,
    current_user: CurrentUserDep,
    session: SessionDep,
) -> CartRead:
    """Add a product to the cart or increment quantity if already present."""
    return await cart_service.add_item(
        session=session, user_id=current_user.id, data=data
    )


@router.patch(
    "/items/{item_id}",
    response_model=CartRead,
    status_code=status.HTTP_200_OK,
    summary="Update cart item quantity",
)
async def update_cart_item(
    item_id: uuid.UUID,
    data: CartItemUpdate,
    current_user: CurrentUserDep,
    session: SessionDep,
) -> CartRead:
    """Update quantity for a specific line item in customer's cart."""
    return await cart_service.update_item(
        session=session, user_id=current_user.id, item_id=item_id, data=data
    )


@router.delete(
    "/items/{item_id}",
    response_model=CartRead,
    status_code=status.HTTP_200_OK,
    summary="Remove an item from cart",
)
async def remove_cart_item(
    item_id: uuid.UUID,
    current_user: CurrentUserDep,
    session: SessionDep,
) -> CartRead:
    """Remove a single line item from the shopping cart."""
    return await cart_service.remove_item(
        session=session, user_id=current_user.id, item_id=item_id
    )


@router.delete(
    "",
    response_model=CartRead,
    status_code=status.HTTP_200_OK,
    summary="Clear all items from shopping cart",
)
async def clear_cart(
    current_user: CurrentUserDep,
    session: SessionDep,
) -> CartRead:
    """Empty the entire shopping cart."""
    return await cart_service.clear_cart(session=session, user_id=current_user.id)
