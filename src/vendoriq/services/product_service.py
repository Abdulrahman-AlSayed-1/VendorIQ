import math
import uuid
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from vendoriq.models.category import Category
from vendoriq.models.product import Product
from vendoriq.schemas.category import CategoryCreate, CategoryUpdate
from vendoriq.schemas.product import (
    ProductCreate,
    ProductSortOption,
    ProductUpdate,
)


class ProductService:
    """Service handling product catalog search, filtering, and administration."""

    # -------------------------------------------------------------------------
    # Public Category Queries
    # -------------------------------------------------------------------------
    async def get_categories(
        self, session: AsyncSession, include_inactive: bool = False
    ) -> list[Category]:
        stmt = select(Category).order_by(Category.name.asc())
        if not include_inactive:
            stmt = stmt.where(Category.is_active.is_(True))
        result = await session.execute(stmt)
        return list(result.scalars().all())

    async def get_category_by_id_or_slug(
        self,
        session: AsyncSession,
        id_or_slug: str,
        include_inactive: bool = False,
    ) -> Category:
        is_uuid = False
        try:
            parsed_uuid = uuid.UUID(id_or_slug)
            is_uuid = True
        except ValueError:
            parsed_uuid = None

        if is_uuid and parsed_uuid:
            stmt = select(Category).where(Category.id == parsed_uuid)
        else:
            stmt = select(Category).where(Category.slug == id_or_slug)

        if not include_inactive:
            stmt = stmt.where(Category.is_active.is_(True))

        result = await session.execute(stmt)
        category = result.scalar_one_or_none()
        if not category:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Category '{id_or_slug}' not found.",
            )
        return category

    # -------------------------------------------------------------------------
    # Public Product Queries
    # -------------------------------------------------------------------------
    async def get_products(
        self,
        session: AsyncSession,
        search: str | None = None,
        category_id: uuid.UUID | None = None,
        category_slug: str | None = None,
        brand: str | None = None,
        min_price: Decimal | None = None,
        max_price: Decimal | None = None,
        in_stock: bool | None = None,
        sort: ProductSortOption = "newest",
        page: int = 1,
        page_size: int = 20,
        include_inactive: bool = False,
    ) -> tuple[list[Product], int, int]:
        # Validate price range
        if min_price is not None and max_price is not None and min_price > max_price:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="min_price cannot be greater than max_price.",
            )

        stmt = select(Product)
        count_stmt = select(func.count(Product.id))

        if not include_inactive:
            stmt = stmt.where(Product.is_active.is_(True))
            count_stmt = count_stmt.where(Product.is_active.is_(True))

        # Search filter
        if search:
            term = f"%{search.strip()}%"
            search_clause = or_(
                Product.name.ilike(term),
                Product.brand.ilike(term),
                Product.description.ilike(term),
            )
            stmt = stmt.where(search_clause)
            count_stmt = count_stmt.where(search_clause)

        # Category filter (by id or slug)
        if category_id:
            stmt = stmt.where(Product.category_id == category_id)
            count_stmt = count_stmt.where(Product.category_id == category_id)
        elif category_slug:
            stmt = stmt.join(Category).where(Category.slug == category_slug)
            count_stmt = count_stmt.join(Category).where(Category.slug == category_slug)

        # Brand filter
        if brand:
            stmt = stmt.where(Product.brand.ilike(brand.strip()))
            count_stmt = count_stmt.where(Product.brand.ilike(brand.strip()))

        # Price range filter
        if min_price is not None:
            stmt = stmt.where(Product.price >= min_price)
            count_stmt = count_stmt.where(Product.price >= min_price)
        if max_price is not None:
            stmt = stmt.where(Product.price <= max_price)
            count_stmt = count_stmt.where(Product.price <= max_price)

        # In stock filter
        if in_stock is True:
            stmt = stmt.where(Product.stock > 0)
            count_stmt = count_stmt.where(Product.stock > 0)

        # Sorting
        if sort == "price_asc":
            stmt = stmt.order_by(Product.price.asc(), Product.id.asc())
        elif sort == "price_desc":
            stmt = stmt.order_by(Product.price.desc(), Product.id.asc())
        else:  # newest
            stmt = stmt.order_by(Product.created_at.desc(), Product.id.asc())

        # Total count
        total_res = await session.execute(count_stmt)
        total = total_res.scalar_one() or 0
        total_pages = math.ceil(total / page_size) if total > 0 else 1

        # Pagination
        offset = (page - 1) * page_size
        stmt = stmt.offset(offset).limit(page_size)

        res = await session.execute(stmt)
        products = list(res.scalars().all())
        return products, total, total_pages

    async def get_product_by_id_or_slug(
        self,
        session: AsyncSession,
        id_or_slug: str,
        include_inactive: bool = False,
    ) -> Product:
        is_uuid = False
        try:
            parsed_uuid = uuid.UUID(id_or_slug)
            is_uuid = True
        except ValueError:
            parsed_uuid = None

        if is_uuid and parsed_uuid:
            stmt = select(Product).where(Product.id == parsed_uuid)
        else:
            stmt = select(Product).where(Product.slug == id_or_slug)

        if not include_inactive:
            stmt = stmt.where(Product.is_active.is_(True))

        result = await session.execute(stmt)
        product = result.scalar_one_or_none()
        if not product:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Product '{id_or_slug}' not found.",
            )
        return product

    # -------------------------------------------------------------------------
    # Admin Management Methods
    # -------------------------------------------------------------------------
    async def create_category(
        self, session: AsyncSession, data: CategoryCreate
    ) -> Category:
        existing = await session.execute(
            select(Category).where(Category.slug == data.slug.strip().lower())
        )
        if existing.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Category with slug '{data.slug}' already exists.",
            )

        cat = Category(
            name=data.name.strip(),
            slug=data.slug.strip().lower(),
            description=data.description,
            is_active=True,
        )
        session.add(cat)
        await session.commit()
        await session.refresh(cat)
        return cat

    async def update_category(
        self, session: AsyncSession, category_id: uuid.UUID, data: CategoryUpdate
    ) -> Category:
        cat = await session.get(Category, category_id)
        if not cat:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Category with ID '{category_id}' not found.",
            )

        if data.slug and data.slug.strip().lower() != cat.slug:
            existing = await session.execute(
                select(Category).where(
                    Category.slug == data.slug.strip().lower(),
                    Category.id != category_id,
                )
            )
            if existing.scalar_one_or_none():
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Category with slug '{data.slug}' already exists.",
                )
            cat.slug = data.slug.strip().lower()

        if data.name is not None:
            cat.name = data.name.strip()
        if data.description is not None:
            cat.description = data.description
        if data.is_active is not None:
            cat.is_active = data.is_active

        await session.commit()
        await session.refresh(cat)
        return cat

    async def create_product(
        self, session: AsyncSession, data: ProductCreate
    ) -> Product:
        # Check slug uniqueness
        existing_slug = await session.execute(
            select(Product).where(Product.slug == data.slug.strip().lower())
        )
        if existing_slug.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Product with slug '{data.slug}' already exists.",
            )

        # Check SKU uniqueness
        existing_sku = await session.execute(
            select(Product).where(Product.sku == data.sku.strip().upper())
        )
        if existing_sku.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Product with SKU '{data.sku}' already exists.",
            )

        # Validate category exists if provided
        if data.category_id:
            category = await session.get(Category, data.category_id)
            if not category:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Category with ID '{data.category_id}' not found.",
                )

        product = Product(
            category_id=data.category_id,
            name=data.name.strip(),
            slug=data.slug.strip().lower(),
            sku=data.sku.strip().upper(),
            description=data.description,
            brand=data.brand.strip() if data.brand else None,
            price=data.price,
            currency=data.currency.lower(),
            stock=data.stock,
            attributes=data.attributes,
            image_urls=data.image_urls,
            is_active=True,
        )
        session.add(product)
        await session.commit()
        await session.refresh(product)
        return product

    async def update_product(
        self, session: AsyncSession, product_id: uuid.UUID, data: ProductUpdate
    ) -> Product:
        product = await session.get(Product, product_id)
        if not product:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Product with ID '{product_id}' not found.",
            )

        if data.slug and data.slug.strip().lower() != product.slug:
            existing = await session.execute(
                select(Product).where(
                    Product.slug == data.slug.strip().lower(),
                    Product.id != product_id,
                )
            )
            if existing.scalar_one_or_none():
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Product with slug '{data.slug}' already exists.",
                )
            product.slug = data.slug.strip().lower()

        if data.sku and data.sku.strip().upper() != product.sku:
            existing = await session.execute(
                select(Product).where(
                    Product.sku == data.sku.strip().upper(),
                    Product.id != product_id,
                )
            )
            if existing.scalar_one_or_none():
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Product with SKU '{data.sku}' already exists.",
                )
            product.sku = data.sku.strip().upper()

        if data.category_id is not None:
            category = await session.get(Category, data.category_id)
            if not category:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Category with ID '{data.category_id}' not found.",
                )
            product.category_id = data.category_id

        if data.name is not None:
            product.name = data.name.strip()
        if data.description is not None:
            product.description = data.description
        if data.brand is not None:
            product.brand = data.brand.strip() if data.brand else None
        if data.price is not None:
            product.price = data.price
        if data.currency is not None:
            product.currency = data.currency.lower()
        if data.stock is not None:
            product.stock = data.stock
        if data.attributes is not None:
            product.attributes = data.attributes
        if data.image_urls is not None:
            product.image_urls = data.image_urls
        if data.is_active is not None:
            product.is_active = data.is_active

        await session.commit()
        await session.refresh(product)
        return product

    async def update_product_stock(
        self, session: AsyncSession, product_id: uuid.UUID, new_stock: int
    ) -> Product:
        product = await session.get(Product, product_id)
        if not product:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Product with ID '{product_id}' not found.",
            )
        product.stock = new_stock
        await session.commit()
        await session.refresh(product)
        return product

    async def deactivate_product(
        self, session: AsyncSession, product_id: uuid.UUID
    ) -> Product:
        """Soft-deactivate a product (is_active = False). Never physically delete."""
        product = await session.get(Product, product_id)
        if not product:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Product with ID '{product_id}' not found.",
            )
        product.is_active = False
        await session.commit()
        await session.refresh(product)
        return product


product_service = ProductService()
