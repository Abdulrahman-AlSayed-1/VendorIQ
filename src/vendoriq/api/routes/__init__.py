from fastapi import APIRouter

from vendoriq.api.routes import (
    admin,
    auth,
    cart,
    categories,
    health,
    products,
    users,
)

api_router = APIRouter()

api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(categories.router)
api_router.include_router(products.router)
api_router.include_router(cart.router)
api_router.include_router(admin.router)

__all__ = ["api_router"]
