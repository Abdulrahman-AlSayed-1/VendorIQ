import uuid
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from vendoriq.core.security import hash_password
from vendoriq.models.product import Product
from vendoriq.models.user import User, UserRole


@pytest.fixture
async def customer_headers(
    async_client: AsyncClient, regular_user: User
) -> dict[str, str]:
    res = await async_client.post(
        "/api/v1/auth/login",
        json={"email": regular_user.email, "password": "Customer123!"},
    )
    token = res.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
async def other_customer(db_session: AsyncSession) -> User:
    other = User(
        id=uuid.uuid4(),
        name="Other Customer",
        email="other@example.com",
        password_hash=hash_password("OtherPassword123!"),
        role=UserRole.CUSTOMER,
        is_active=True,
    )
    db_session.add(other)
    await db_session.commit()
    await db_session.refresh(other)
    return other


@pytest.fixture
async def catalog_product(db_session: AsyncSession) -> Product:
    prod = Product(
        id=uuid.uuid4(),
        name="Ergonomic Mouse",
        slug="ergonomic-mouse",
        sku="MOU-ERG-001",
        description="Wireless ergonomic vertical mouse",
        brand="LogiTech",
        price=Decimal("49.99"),
        currency="usd",
        stock=10,
        attributes={"dpi": 4000},
        image_urls=[],
        is_active=True,
    )
    db_session.add(prod)
    await db_session.commit()
    await db_session.refresh(prod)
    return prod


@pytest.mark.asyncio
async def test_cart_unauthorized(async_client: AsyncClient):
    res = await async_client.get("/api/v1/cart")
    assert res.status_code == 401


@pytest.mark.asyncio
async def test_get_empty_cart(
    async_client: AsyncClient, customer_headers: dict[str, str]
):
    res = await async_client.get("/api/v1/cart", headers=customer_headers)
    assert res.status_code == 200
    data = res.json()
    assert data["items"] == []
    assert data["subtotal"] == "0.00"
    assert data["grand_total"] == "0.00"
    assert data["item_count"] == 0


@pytest.mark.asyncio
async def test_add_item_to_cart(
    async_client: AsyncClient,
    customer_headers: dict[str, str],
    catalog_product: Product,
):
    payload = {"product_id": str(catalog_product.id), "quantity": 2}
    res = await async_client.post(
        "/api/v1/cart/items", headers=customer_headers, json=payload
    )
    assert res.status_code == 201
    data = res.json()
    assert len(data["items"]) == 1
    item = data["items"][0]
    assert item["product_id"] == str(catalog_product.id)
    assert item["quantity"] == 2
    assert item["unit_price"] == "49.99"
    assert item["line_total"] == "99.98"
    assert data["subtotal"] == "99.98"
    assert data["grand_total"] == "99.98"
    assert data["item_count"] == 2


@pytest.mark.asyncio
async def test_add_existing_item_increments_quantity(
    async_client: AsyncClient,
    customer_headers: dict[str, str],
    catalog_product: Product,
):
    # Add 2 items
    await async_client.post(
        "/api/v1/cart/items",
        headers=customer_headers,
        json={"product_id": str(catalog_product.id), "quantity": 2},
    )
    # Add 3 more items of the same product
    res = await async_client.post(
        "/api/v1/cart/items",
        headers=customer_headers,
        json={"product_id": str(catalog_product.id), "quantity": 3},
    )
    assert res.status_code == 201
    data = res.json()
    assert len(data["items"]) == 1
    assert data["items"][0]["quantity"] == 5
    assert data["items"][0]["line_total"] == "249.95"
    assert data["subtotal"] == "249.95"


@pytest.mark.asyncio
async def test_add_exceeding_stock_fails(
    async_client: AsyncClient,
    customer_headers: dict[str, str],
    catalog_product: Product,
):
    # Product stock is 10. Attempt to add 11.
    res = await async_client.post(
        "/api/v1/cart/items",
        headers=customer_headers,
        json={"product_id": str(catalog_product.id), "quantity": 11},
    )
    assert res.status_code == 409
    assert "exceeds available stock" in res.json()["detail"].lower()


@pytest.mark.asyncio
async def test_update_cart_item_quantity(
    async_client: AsyncClient,
    customer_headers: dict[str, str],
    catalog_product: Product,
):
    # Add 1 item
    add_res = await async_client.post(
        "/api/v1/cart/items",
        headers=customer_headers,
        json={"product_id": str(catalog_product.id), "quantity": 1},
    )
    item_id = add_res.json()["items"][0]["id"]

    # Update to 4 items
    update_res = await async_client.patch(
        f"/api/v1/cart/items/{item_id}",
        headers=customer_headers,
        json={"quantity": 4},
    )
    assert update_res.status_code == 200
    data = update_res.json()
    assert data["items"][0]["quantity"] == 4
    assert data["subtotal"] == "199.96"


@pytest.mark.asyncio
async def test_remove_cart_item(
    async_client: AsyncClient,
    customer_headers: dict[str, str],
    catalog_product: Product,
):
    add_res = await async_client.post(
        "/api/v1/cart/items",
        headers=customer_headers,
        json={"product_id": str(catalog_product.id), "quantity": 2},
    )
    item_id = add_res.json()["items"][0]["id"]

    # Remove item
    del_res = await async_client.delete(
        f"/api/v1/cart/items/{item_id}",
        headers=customer_headers,
    )
    assert del_res.status_code == 200
    data = del_res.json()
    assert len(data["items"]) == 0
    assert data["subtotal"] == "0.00"


@pytest.mark.asyncio
async def test_clear_cart(
    async_client: AsyncClient,
    customer_headers: dict[str, str],
    catalog_product: Product,
):
    await async_client.post(
        "/api/v1/cart/items",
        headers=customer_headers,
        json={"product_id": str(catalog_product.id), "quantity": 3},
    )

    clear_res = await async_client.delete("/api/v1/cart", headers=customer_headers)
    assert clear_res.status_code == 200
    data = clear_res.json()
    assert len(data["items"]) == 0
    assert data["item_count"] == 0


@pytest.mark.asyncio
async def test_cart_idor_protection(
    async_client: AsyncClient,
    customer_headers: dict[str, str],
    other_customer: User,
    catalog_product: Product,
):
    # Customer A adds item
    add_res = await async_client.post(
        "/api/v1/cart/items",
        headers=customer_headers,
        json={"product_id": str(catalog_product.id), "quantity": 1},
    )
    item_id = add_res.json()["items"][0]["id"]

    # Customer B logs in
    b_token = (
        await async_client.post(
            "/api/v1/auth/login",
            json={"email": other_customer.email, "password": "OtherPassword123!"},
        )
    ).json()["access_token"]
    b_headers = {"Authorization": f"Bearer {b_token}"}

    # Customer B tries to update Customer A's cart item -> 404 Not Found (IDOR prevented)
    idor_patch = await async_client.patch(
        f"/api/v1/cart/items/{item_id}",
        headers=b_headers,
        json={"quantity": 5},
    )
    assert idor_patch.status_code == 404

    # Customer B tries to delete Customer A's cart item -> 404 Not Found
    idor_del = await async_client.delete(
        f"/api/v1/cart/items/{item_id}",
        headers=b_headers,
    )
    assert idor_del.status_code == 404


@pytest.mark.asyncio
async def test_dynamic_price_drift(
    async_client: AsyncClient,
    customer_headers: dict[str, str],
    catalog_product: Product,
    db_session: AsyncSession,
):
    # Add item when price is 49.99
    await async_client.post(
        "/api/v1/cart/items",
        headers=customer_headers,
        json={"product_id": str(catalog_product.id), "quantity": 2},
    )

    # Merchant updates catalog price to 59.99 in DB
    catalog_product.price = Decimal("59.99")
    await db_session.commit()

    # Customer retrieves cart -> price and total automatically reflect the updated catalog price
    cart_res = await async_client.get("/api/v1/cart", headers=customer_headers)
    assert cart_res.status_code == 200
    cart_data = cart_res.json()
    assert cart_data["items"][0]["unit_price"] == "59.99"
    assert cart_data["items"][0]["line_total"] == "119.98"
    assert cart_data["subtotal"] == "119.98"
    assert cart_data["grand_total"] == "119.98"
