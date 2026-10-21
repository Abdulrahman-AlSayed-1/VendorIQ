from datetime import timedelta

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from vendoriq.core.config import settings
from vendoriq.core.security import create_access_token, hash_password, verify_password
from vendoriq.models.user import User, UserRole
from vendoriq.schemas.user import Token, UserLogin, UserRegister


class AuthService:
    """Service handling user registration, authentication, and token management."""

    @staticmethod
    def normalize_email(email: str) -> str:
        return email.strip().lower()

    async def register_user(self, session: AsyncSession, data: UserRegister) -> User:
        normalized_email = self.normalize_email(data.email)

        # Check existing user
        stmt = select(User).where(User.email == normalized_email)
        res = await session.execute(stmt)
        if res.scalar_one_or_none() is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A user with this email address already exists.",
            )

        hashed = hash_password(data.password)
        new_user = User(
            name=data.name.strip(),
            email=normalized_email,
            password_hash=hashed,
            role=UserRole.CUSTOMER,  # Public registration strictly creates customers
            is_active=True,
        )
        session.add(new_user)
        await session.commit()
        await session.refresh(new_user)
        return new_user

    async def authenticate_user(self, session: AsyncSession, data: UserLogin) -> User:
        normalized_email = self.normalize_email(data.email)
        stmt = select(User).where(User.email == normalized_email)
        res = await session.execute(stmt)
        user = res.scalar_one_or_none()

        if not user or not verify_password(data.password, user.password_hash):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password.",
                headers={"WWW-Authenticate": "Bearer"},
            )

        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Inactive user account.",
            )

        return user

    def create_user_token(self, user: User) -> Token:
        expires_delta = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        token_str = create_access_token(
            subject=str(user.id),
            secret_key=settings.SECRET_KEY,
            algorithm=settings.ALGORITHM,
            expires_delta=expires_delta,
            extra_claims={"role": user.role.value, "email": user.email},
        )
        return Token(
            access_token=token_str,
            token_type="bearer",
            expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        )


auth_service = AuthService()
