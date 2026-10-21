import uuid

from fastapi import APIRouter, status

from vendoriq.api.deps import CurrentAdminDep, SessionDep
from vendoriq.schemas.category import CategoryCreate, CategoryRead, CategoryUpdate
from vendoriq.schemas.product import (
    ProductCreate,
    ProductRead,
    ProductStockUpdate,
    ProductUpdate,
)
from vendoriq.services.product_service import product_service

router = APIRouter(prefix="/admin", tags=["Administration"])


# -----------------------------------------------------------------------------
# Admin Category Management
# -----------------------------------------------------------------------------
@router.post(
    "/categories",
    response_model=CategoryRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new catalog category (Admin only)",
)
async def create_category(
    data: CategoryCreate,
    session: SessionDep,
    _admin: CurrentAdminDep,
) -> CategoryRead:
    return await product_service.create_category(session=session, data=data)


@router.patch(
    "/categories/{category_id}",
    response_model=CategoryRead,
    status_code=status.HTTP_200_OK,
    summary="Update category details (Admin only)",
)
async def update_category(
    category_id: uuid.UUID,
    data: CategoryUpdate,
    session: SessionDep,
    _admin: CurrentAdminDep,
) -> CategoryRead:
    return await product_service.update_category(
        session=session, category_id=category_id, data=data
    )


# -----------------------------------------------------------------------------
# Admin Product Management
# -----------------------------------------------------------------------------
@router.post(
    "/products",
    response_model=ProductRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new product (Admin only)",
)
async def create_product(
    data: ProductCreate,
    session: SessionDep,
    _admin: CurrentAdminDep,
) -> ProductRead:
    return await product_service.create_product(session=session, data=data)


@router.patch(
    "/products/{product_id}",
    response_model=ProductRead,
    status_code=status.HTTP_200_OK,
    summary="Update product details (Admin only)",
)
async def update_product(
    product_id: uuid.UUID,
    data: ProductUpdate,
    session: SessionDep,
    _admin: CurrentAdminDep,
) -> ProductRead:
    return await product_service.update_product(
        session=session, product_id=product_id, data=data
    )


@router.patch(
    "/products/{product_id}/stock",
    response_model=ProductRead,
    status_code=status.HTTP_200_OK,
    summary="Update product inventory stock (Admin only)",
)
async def update_product_stock(
    product_id: uuid.UUID,
    data: ProductStockUpdate,
    session: SessionDep,
    _admin: CurrentAdminDep,
) -> ProductRead:
    return await product_service.update_product_stock(
        session=session, product_id=product_id, new_stock=data.stock
    )


@router.delete(
    "/products/{product_id}",
    response_model=ProductRead,
    status_code=status.HTTP_200_OK,
    summary="Soft-deactivate a product (Admin only)",
)
async def deactivate_product(
    product_id: uuid.UUID,
    session: SessionDep,
    _admin: CurrentAdminDep,
) -> ProductRead:
    """Soft-deactivate product. The product is never physically deleted to preserve historical order integrity."""
    return await product_service.deactivate_product(
        session=session, product_id=product_id
    )
