import uuid
from typing import Annotated

from fastapi import APIRouter, Query, status

from vendoriq.api.deps import CurrentAdminDep, SessionDep
from vendoriq.models.order import OrderStatus
from vendoriq.schemas.category import CategoryCreate, CategoryRead, CategoryUpdate
from vendoriq.schemas.order import (
    OrderPaginationResponse,
    OrderRead,
    OrderStatusUpdate,
)
from vendoriq.schemas.product import (
    ProductCreate,
    ProductRead,
    ProductStockUpdate,
    ProductUpdate,
)
from vendoriq.services.inventory_service import inventory_service
from vendoriq.services.order_service import order_service
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
    category = await product_service.create_category(session=session, data=data)
    return CategoryRead.model_validate(category)


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
    category = await product_service.update_category(
        session=session, category_id=category_id, data=data
    )
    return CategoryRead.model_validate(category)


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
    product = await product_service.create_product(session=session, data=data)
    return ProductRead.model_validate(product)


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
    product = await product_service.update_product(
        session=session, product_id=product_id, data=data
    )
    return ProductRead.model_validate(product)


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
    product = await product_service.update_product_stock(
        session=session, product_id=product_id, new_stock=data.stock
    )
    return ProductRead.model_validate(product)


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
    product = await product_service.deactivate_product(
        session=session, product_id=product_id
    )
    return ProductRead.model_validate(product)


# -----------------------------------------------------------------------------
# Admin Order & Inventory Management
# -----------------------------------------------------------------------------
@router.get(
    "/orders",
    response_model=OrderPaginationResponse,
    status_code=status.HTTP_200_OK,
    summary="List all customer orders with filters (Admin only)",
)
async def list_orders_admin(
    session: SessionDep,
    _admin: CurrentAdminDep,
    order_status: Annotated[
        OrderStatus | None,
        Query(description="Filter by order status"),
    ] = None,
    page: Annotated[int, Query(ge=1, description="Page number")] = 1,
    page_size: Annotated[int, Query(ge=1, le=100, description="Items per page")] = 20,
) -> OrderPaginationResponse:
    orders, total, total_pages = await order_service.get_all_orders_admin(
        session=session,
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


@router.patch(
    "/orders/{order_id}/status",
    response_model=OrderRead,
    status_code=status.HTTP_200_OK,
    summary="Update order fulfillment status (Admin only)",
)
async def update_order_status_admin(
    order_id: uuid.UUID,
    data: OrderStatusUpdate,
    session: SessionDep,
    _admin: CurrentAdminDep,
) -> OrderRead:
    order = await order_service.update_order_status_admin(
        session=session, order_id=order_id, new_status=data.status
    )
    return OrderRead.model_validate(order)


@router.post(
    "/orders/reconcile-expired",
    status_code=status.HTTP_200_OK,
    summary="Reconcile and release expired unpaid checkout reservations (Admin only)",
)
async def reconcile_expired_orders(
    session: SessionDep,
    _admin: CurrentAdminDep,
):
    cancelled_ids = await inventory_service.reconcile_expired_reservations(
        session=session
    )
    return {
        "status": "success",
        "cancelled_orders_count": len(cancelled_ids),
        "cancelled_order_ids": [str(oid) for oid in cancelled_ids],
    }
