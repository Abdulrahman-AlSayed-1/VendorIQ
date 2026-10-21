from fastapi import APIRouter

from vendoriq.api.deps import CurrentUserDep
from vendoriq.models.user import User
from vendoriq.schemas.user import UserRead

router = APIRouter(prefix="/users", tags=["Users"])


@router.get("/me", response_model=UserRead, summary="Get current user profile")
async def get_current_user_profile(current_user: CurrentUserDep) -> User:
    """Retrieve current user profile."""
    return current_user
