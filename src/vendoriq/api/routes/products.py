import uuid
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Query, status

from vendoriq.api.deps import SessionDep
from vendoriq.schemas.product import (
    ProductPaginationResponse,
    ProductRead,
    ProductSortOption,
)
from vendoriq.services.product_service import product_service

router = APIRouter(prefix="/products", tags=["Products"])


@router.get(
    "",
    response_model=ProductPaginationResponse,
    status_code=status.HTTP_200_OK,
    summary="List, search, and filter catalog products",
)
async def list_products(
    session: SessionDep,
    search: Annotated[
        str | None,
        Query(description="Keyword search across name, brand, description"),
    ] = None,
    category_id: Annotated[
        uuid.UUID | None, Query(description="Filter by category UUID")
    ] = None,
    category_slug: Annotated[
        str | None, Query(description="Filter by category slug")
    ] = None,
    brand: Annotated[str | None, Query(description="Filter by product brand")] = None,
    min_price: Annotated[
        Decimal | None, Query(ge=0, description="Minimum unit price")
    ] = None,
    max_price: Annotated[
        Decimal | None, Query(ge=0, description="Maximum unit price")
    ] = None,
    in_stock: Annotated[
        bool | None,
        Query(description="Filter only products with available stock"),
    ] = None,
    sort: Annotated[
        ProductSortOption,
        Query(description="Sorting criteria (price_asc, price_desc, newest)"),
    ] = "newest",
    page: Annotated[int, Query(ge=1, description="Page number")] = 1,
    page_size: Annotated[int, Query(ge=1, le=100, description="Items per page")] = 20,
) -> ProductPaginationResponse:
    """Retrieve paginated, filtered, and sorted catalog products."""
    products, total, total_pages = await product_service.get_products(
        session=session,
        search=search,
        category_id=category_id,
        category_slug=category_slug,
        brand=brand,
        min_price=min_price,
        max_price=max_price,
        in_stock=in_stock,
        sort=sort,
        page=page,
        page_size=page_size,
        include_inactive=False,
    )
    return ProductPaginationResponse(
        items=products,  # type: ignore[arg-type]
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


@router.get(
    "/{id_or_slug}",
    response_model=ProductRead,
    status_code=status.HTTP_200_OK,
    summary="Get single product details by UUID or slug",
)
async def get_product(
    id_or_slug: str,
    session: SessionDep,
) -> ProductRead:
    """Retrieve details for a single product identified by UUID or slug."""
    product = await product_service.get_product_by_id_or_slug(
        session=session, id_or_slug=id_or_slug, include_inactive=False
    )
    return ProductRead.model_validate(product)
