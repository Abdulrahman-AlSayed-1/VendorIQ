import uuid
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from vendoriq.models.category import Category
from vendoriq.models.product import Product
from vendoriq.models.user import User


@pytest.fixture
async def sample_category(db_session: AsyncSession) -> Category:
    cat = Category(
        id=uuid.uuid4(),
        name="Electronics",
        slug="electronics",
        description="Electronic gadgets and devices",
        is_active=True,
    )
    db_session.add(cat)
    await db_session.commit()
    await db_session.refresh(cat)
    return cat


@pytest.fixture
async def sample_products(
    db_session: AsyncSession, sample_category: Category
) -> list[Product]:
    p1 = Product(
        id=uuid.uuid4(),
        category_id=sample_category.id,
        name="Wireless Noise-Canceling Headphones",
        slug="wireless-noise-canceling-headphones",
        sku="AUDIO-001",
        description="Premium headphones with active noise cancellation",
        brand="SoundWave",
        price=Decimal("199.99"),
        currency="usd",
        stock=15,
        attributes={"color": "black", "wireless": True},
        image_urls=["https://example.com/img1.jpg"],
        is_active=True,
    )
    p2 = Product(
        id=uuid.uuid4(),
        category_id=sample_category.id,
        name="Bluetooth Speaker Pro",
        slug="bluetooth-speaker-pro",
        sku="AUDIO-002",
        description="Portable waterproof speaker",
        brand="SoundWave",
        price=Decimal("89.99"),
        currency="usd",
        stock=0,  # Out of stock
        attributes={"waterproof": True},
        image_urls=["https://example.com/speaker.jpg"],
        is_active=True,
    )
    p3 = Product(
        id=uuid.uuid4(),
        category_id=sample_category.id,
        name="Legacy Wired Earphones",
        slug="legacy-wired-earphones",
        sku="AUDIO-003",
        description="Old generation earphones",
        brand="VintageAudio",
        price=Decimal("29.99"),
        currency="usd",
        stock=5,
        attributes={},
        image_urls=[],
        is_active=False,  # Inactive product
    )
    db_session.add_all([p1, p2, p3])
    await db_session.commit()
    for p in [p1, p2, p3]:
        await db_session.refresh(p)
    return [p1, p2, p3]


# =============================================================================
# Public Category Tests
# =============================================================================
@pytest.mark.asyncio
async def test_list_categories(async_client: AsyncClient, sample_category: Category):
    response = await async_client.get("/api/v1/categories")
    assert response.status_code == 200
    data = response.json()
    assert len(data) >= 1
    assert any(c["slug"] == sample_category.slug for c in data)


@pytest.mark.asyncio
async def test_get_category_by_id_and_slug(
    async_client: AsyncClient, sample_category: Category
):
    # Lookup by UUID
    res1 = await async_client.get(f"/api/v1/categories/{sample_category.id}")
    assert res1.status_code == 200
    assert res1.json()["name"] == "Electronics"

    # Lookup by Slug
    res2 = await async_client.get(f"/api/v1/categories/{sample_category.slug}")
    assert res2.status_code == 200
    assert res2.json()["name"] == "Electronics"

    # Lookup non-existent
    res3 = await async_client.get("/api/v1/categories/non-existent-category")
    assert res3.status_code == 404


# =============================================================================
# Public Product Tests (Filtering, Sorting, Search, Inactive exclusion)
# =============================================================================
@pytest.mark.asyncio
async def test_list_products_excludes_inactive(
    async_client: AsyncClient, sample_products: list[Product]
):
    response = await async_client.get("/api/v1/products")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 2  # p1 and p2 only; p3 is inactive
    items = data["items"]
    slugs = [p["slug"] for p in items]
    assert "wireless-noise-canceling-headphones" in slugs
    assert "bluetooth-speaker-pro" in slugs
    assert "legacy-wired-earphones" not in slugs


@pytest.mark.asyncio
async def test_product_search(
    async_client: AsyncClient, sample_products: list[Product]
):
    # Search by keyword in name
    res = await async_client.get("/api/v1/products?search=headphones")
    assert res.status_code == 200
    data = res.json()
    assert data["total"] == 1
    assert data["items"][0]["sku"] == "AUDIO-001"

    # Search by brand
    res_brand = await async_client.get("/api/v1/products?search=SoundWave")
    assert res_brand.status_code == 200
    assert res_brand.json()["total"] == 2


@pytest.mark.asyncio
async def test_product_filter_in_stock(
    async_client: AsyncClient, sample_products: list[Product]
):
    res = await async_client.get("/api/v1/products?in_stock=true")
    assert res.status_code == 200
    data = res.json()
    assert data["total"] == 1
    assert data["items"][0]["stock"] == 15


@pytest.mark.asyncio
async def test_product_filter_price_range(
    async_client: AsyncClient, sample_products: list[Product]
):
    res = await async_client.get("/api/v1/products?min_price=50.00&max_price=100.00")
    assert res.status_code == 200
    data = res.json()
    assert data["total"] == 1
    assert data["items"][0]["price"] == "89.99"


@pytest.mark.asyncio
async def test_product_sorting(
    async_client: AsyncClient, sample_products: list[Product]
):
    # Ascending
    res_asc = await async_client.get("/api/v1/products?sort=price_asc")
    assert res_asc.status_code == 200
    items_asc = res_asc.json()["items"]
    assert items_asc[0]["price"] == "89.99"
    assert items_asc[1]["price"] == "199.99"

    # Descending
    res_desc = await async_client.get("/api/v1/products?sort=price_desc")
    assert res_desc.status_code == 200
    items_desc = res_desc.json()["items"]
    assert items_desc[0]["price"] == "199.99"
    assert items_desc[1]["price"] == "89.99"


@pytest.mark.asyncio
async def test_get_product_detail_public(
    async_client: AsyncClient, sample_products: list[Product]
):
    p1 = sample_products[0]
    p3_inactive = sample_products[2]

    # Active product by UUID
    res1 = await async_client.get(f"/api/v1/products/{p1.id}")
    assert res1.status_code == 200
    assert res1.json()["name"] == p1.name

    # Active product by slug
    res2 = await async_client.get(f"/api/v1/products/{p1.slug}")
    assert res2.status_code == 200
    assert res2.json()["name"] == p1.name

    # Inactive product lookup must return 404 for public
    res3 = await async_client.get(f"/api/v1/products/{p3_inactive.id}")
    assert res3.status_code == 404


# =============================================================================
# Admin Catalog Operations & Authorization Tests
# =============================================================================
@pytest.mark.asyncio
async def test_admin_category_management(
    async_client: AsyncClient, admin_user: User, regular_user: User
):
    # Customer gets 403
    cust_token = (
        await async_client.post(
            "/api/v1/auth/login",
            json={"email": regular_user.email, "password": "Customer123!"},
        )
    ).json()["access_token"]
    forbidden_res = await async_client.post(
        "/api/v1/admin/categories",
        headers={"Authorization": f"Bearer {cust_token}"},
        json={"name": "Books", "slug": "books"},
    )
    assert forbidden_res.status_code == 403

    # Admin creates category
    admin_token = (
        await async_client.post(
            "/api/v1/auth/login",
            json={"email": admin_user.email, "password": "AdminSecure123!"},
        )
    ).json()["access_token"]
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    create_res = await async_client.post(
        "/api/v1/admin/categories",
        headers=admin_headers,
        json={
            "name": "Computers",
            "slug": "computers",
            "description": "Laptops & Desktops",
        },
    )
    assert create_res.status_code == 201
    cat_data = create_res.json()
    assert "id" in cat_data

    # Duplicate slug raises 409
    dup_res = await async_client.post(
        "/api/v1/admin/categories",
        headers=admin_headers,
        json={"name": "Duplicate Computers", "slug": "computers"},
    )
    assert dup_res.status_code == 409


@pytest.mark.asyncio
async def test_admin_product_lifecycle(
    async_client: AsyncClient, admin_user: User, sample_category: Category
):
    admin_token = (
        await async_client.post(
            "/api/v1/auth/login",
            json={"email": admin_user.email, "password": "AdminSecure123!"},
        )
    ).json()["access_token"]
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    # 1. Admin creates product
    prod_payload = {
        "category_id": str(sample_category.id),
        "name": "Ultra Mechanical Keyboard",
        "slug": "ultra-mechanical-keyboard",
        "sku": "KB-MECH-001",
        "description": "RGB mechanical keyboard",
        "brand": "KeyCraft",
        "price": 129.50,
        "stock": 25,
        "attributes": {"switches": "Cherry MX Blue"},
        "image_urls": ["https://example.com/kb.jpg"],
    }
    create_res = await async_client.post(
        "/api/v1/admin/products",
        headers=admin_headers,
        json=prod_payload,
    )
    assert create_res.status_code == 201
    created_prod = create_res.json()
    assert created_prod["price"] == "129.50"
    prod_id = created_prod["id"]

    # 2. Admin updates stock
    stock_res = await async_client.patch(
        f"/api/v1/admin/products/{prod_id}/stock",
        headers=admin_headers,
        json={"stock": 50},
    )
    assert stock_res.status_code == 200
    assert stock_res.json()["stock"] == 50

    # 3. Admin soft-deactivates product
    delete_res = await async_client.delete(
        f"/api/v1/admin/products/{prod_id}",
        headers=admin_headers,
    )
    assert delete_res.status_code == 200
    assert delete_res.json()["is_active"] is False

    # 4. Deactivated product is immediately hidden from public listing
    public_res = await async_client.get(f"/api/v1/products/{prod_id}")
    assert public_res.status_code == 404
