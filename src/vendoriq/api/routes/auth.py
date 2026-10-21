from fastapi import APIRouter, status

from vendoriq.api.deps import CurrentUserDep, SessionDep
from vendoriq.models.user import User
from vendoriq.schemas.user import Token, UserLogin, UserRead, UserRegister
from vendoriq.services.auth_service import auth_service

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post(
    "/register",
    response_model=UserRead,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new customer account",
)
async def register(
    data: UserRegister,
    session: SessionDep,
) -> User:
    """Register a new customer. Public registration creates customer accounts only."""
    return await auth_service.register_user(session, data)


@router.post(
    "/login",
    response_model=Token,
    status_code=status.HTTP_200_OK,
    summary="Authenticate and obtain access token",
)
async def login(
    data: UserLogin,
    session: SessionDep,
) -> Token:
    """Authenticate with normalized email and password to receive a JWT access token."""
    user = await auth_service.authenticate_user(session, data)
    return auth_service.create_user_token(user)


@router.get(
    "/me",
    response_model=UserRead,
    status_code=status.HTTP_200_OK,
    summary="Get current authenticated user profile",
)
async def get_me(
    current_user: CurrentUserDep,
) -> User:
    """Return the currently authenticated user's profile."""
    return current_user
