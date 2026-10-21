from fastapi import APIRouter, status

from vendoriq.api.deps import SessionDep
from vendoriq.schemas.category import CategoryRead
from vendoriq.services.product_service import product_service

router = APIRouter(prefix="/categories", tags=["Categories"])


@router.get(
    "",
    response_model=list[CategoryRead],
    status_code=status.HTTP_200_OK,
    summary="List all active product categories",
)
async def list_categories(session: SessionDep) -> list[CategoryRead]:
    """Retrieve all active product categories ordered alphabetically."""
    return await product_service.get_categories(session=session)


@router.get(
    "/{id_or_slug}",
    response_model=CategoryRead,
    status_code=status.HTTP_200_OK,
    summary="Get category details by UUID or slug",
)
async def get_category(id_or_slug: str, session: SessionDep) -> CategoryRead:
    """Retrieve details for a single category identified by UUID or slug."""
    return await product_service.get_category_by_id_or_slug(
        session=session, id_or_slug=id_or_slug
    )
