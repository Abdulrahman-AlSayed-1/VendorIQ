from fastapi import APIRouter

from vendoriq.api.routes import auth, health, users

api_router = APIRouter()

api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(users.router)

__all__ = ["api_router"]
