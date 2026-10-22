import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from vendoriq.core.security import hash_password
from vendoriq.models.order import Order, OrderItem, OrderStatus
from vendoriq.models.payment import Payment, PaymentStatus
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
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


@pytest.fixture
async def admin_headers(async_client: AsyncClient, admin_user: User) -> dict[str, str]:
    res = await async_client.post(
        "/api/v1/auth/login",
        json={"email": admin_user.email, "password": "AdminSecure123!"},
    )
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


@pytest.fixture
async def other_customer(db_session: AsyncSession) -> User:
    other = User(
        id=uuid.uuid4(),
        name="Second Customer",
        email="second@example.com",
        password_hash=hash_password("SecondPass123!"),
        role=UserRole.CUSTOMER,
        is_active=True,
    )
    db_session.add(other)
    await db_session.commit()
    await db_session.refresh(other)
    return other


@pytest.fixture
async def order_fixture(
    db_session: AsyncSession, regular_user: User
) -> tuple[Order, Payment, Product]:
    prod = Product(
        id=uuid.uuid4(),
        name="Smart Fitness Watch",
        slug="smart-fitness-watch",
        sku="WAT-001",
        description="Waterproof fitness tracker with heart rate monitor",
        brand="FitLife",
        price=Decimal("120.00"),
        currency="usd",
        stock=5,  # 3 remaining, 2 in order
        attributes={},
        image_urls=[],
        is_active=True,
    )
    db_session.add(prod)

    order_id = uuid.uuid4()
    order = Order(
        id=order_id,
        order_number="ORD-20261022-WATCH1",
        user_id=regular_user.id,
        status=OrderStatus.PENDING_PAYMENT,
        currency="usd",
        subtotal=Decimal("240.00"),
        discount=Decimal("0.00"),
        total=Decimal("240.00"),
        expires_at=datetime.now(UTC) + timedelta(minutes=30),
    )
    order_item = OrderItem(
        id=uuid.uuid4(),
        order_id=order_id,
        product_id=prod.id,
        product_name_snapshot=prod.name,
        sku_snapshot=prod.sku,
        unit_price_snapshot=prod.price,
        quantity=2,
        line_total=Decimal("240.00"),
    )
    payment = Payment(
        id=uuid.uuid4(),
        order_id=order_id,
        payment_provider="stripe",
        payment_status=PaymentStatus.PENDING,
        amount=Decimal("240.00"),
        currency="usd",
        stripe_checkout_session_id="cs_test_watch_session",
    )
    db_session.add_all([order, order_item, payment])
    await db_session.commit()
    await db_session.refresh(order)
    await db_session.refresh(payment)
    await db_session.refresh(prod)
    return order, payment, prod


@pytest.mark.asyncio
async def test_get_customer_orders_list(
    async_client: AsyncClient,
    customer_headers: dict[str, str],
    order_fixture: tuple[Order, Payment, Product],
):
    order, _, _ = order_fixture
    res = await async_client.get("/api/v1/orders", headers=customer_headers)
    assert res.status_code == 200
    data = res.json()
    assert data["total"] >= 1
    assert any(o["id"] == str(order.id) for o in data["items"])


@pytest.mark.asyncio
async def test_get_customer_order_detail(
    async_client: AsyncClient,
    customer_headers: dict[str, str],
    order_fixture: tuple[Order, Payment, Product],
):
    order, _, _ = order_fixture
    res = await async_client.get(f"/api/v1/orders/{order.id}", headers=customer_headers)
    assert res.status_code == 200
    data = res.json()
    assert data["order_number"] == order.order_number
    assert len(data["items"]) == 1
    item = data["items"][0]
    assert item["product_name_snapshot"] == "Smart Fitness Watch"
    assert item["quantity"] == 2
    assert item["line_total"] == "240.00"


@pytest.mark.asyncio
async def test_order_and_payment_idor_isolation(
    async_client: AsyncClient,
    other_customer: User,
    order_fixture: tuple[Order, Payment, Product],
):
    order, payment, _ = order_fixture

    # Customer B logs in
    login_res = await async_client.post(
        "/api/v1/auth/login",
        json={"email": other_customer.email, "password": "SecondPass123!"},
    )
    other_headers = {"Authorization": f"Bearer {login_res.json()['access_token']}"}

    # Customer B tries to view Customer A's order -> 404
    order_res = await async_client.get(
        f"/api/v1/orders/{order.id}", headers=other_headers
    )
    assert order_res.status_code == 404

    # Customer B tries to cancel Customer A's order -> 404
    cancel_res = await async_client.post(
        f"/api/v1/orders/{order.id}/cancel", headers=other_headers
    )
    assert cancel_res.status_code == 404

    # Customer B tries to view Customer A's payment -> 404
    payment_res = await async_client.get(
        f"/api/v1/payments/{payment.id}", headers=other_headers
    )
    assert payment_res.status_code == 404


@pytest.mark.asyncio
async def test_customer_cancel_order_releases_stock(
    async_client: AsyncClient,
    customer_headers: dict[str, str],
    order_fixture: tuple[Order, Payment, Product],
    db_session: AsyncSession,
):
    order, payment, prod = order_fixture
    assert prod.stock == 5  # 2 units were reserved

    res = await async_client.post(
        f"/api/v1/orders/{order.id}/cancel", headers=customer_headers
    )
    assert res.status_code == 200
    assert res.json()["status"] == "cancelled"

    # Verify inventory was restored (5 + 2 = 7)
    await db_session.refresh(prod)
    assert prod.stock == 7

    # Verify payment status was cancelled
    await db_session.refresh(payment)
    assert payment.payment_status == PaymentStatus.CANCELLED


@pytest.mark.asyncio
async def test_customer_cannot_cancel_paid_order(
    async_client: AsyncClient,
    customer_headers: dict[str, str],
    order_fixture: tuple[Order, Payment, Product],
    db_session: AsyncSession,
):
    order, _, _ = order_fixture
    order.status = OrderStatus.PAID
    await db_session.commit()

    res = await async_client.post(
        f"/api/v1/orders/{order.id}/cancel", headers=customer_headers
    )
    assert res.status_code == 409
    assert "cannot be cancelled in 'paid' status" in res.json()["detail"].lower()


@pytest.mark.asyncio
async def test_admin_order_lifecycle_and_transitions(
    async_client: AsyncClient,
    admin_headers: dict[str, str],
    order_fixture: tuple[Order, Payment, Product],
):
    order, _, _ = order_fixture

    # 1. Admin lists orders
    list_res = await async_client.get("/api/v1/admin/orders", headers=admin_headers)
    assert list_res.status_code == 200
    assert list_res.json()["total"] >= 1

    # 2. Transition pending_payment -> paid
    t1 = await async_client.patch(
        f"/api/v1/admin/orders/{order.id}/status",
        headers=admin_headers,
        json={"status": "paid"},
    )
    assert t1.status_code == 200
    assert t1.json()["status"] == "paid"

    # 3. Transition paid -> processing
    t2 = await async_client.patch(
        f"/api/v1/admin/orders/{order.id}/status",
        headers=admin_headers,
        json={"status": "processing"},
    )
    assert t2.status_code == 200
    assert t2.json()["status"] == "processing"

    # 4. Transition processing -> shipped
    t3 = await async_client.patch(
        f"/api/v1/admin/orders/{order.id}/status",
        headers=admin_headers,
        json={"status": "shipped"},
    )
    assert t3.status_code == 200
    assert t3.json()["status"] == "shipped"

    # 5. Transition shipped -> delivered
    t4 = await async_client.patch(
        f"/api/v1/admin/orders/{order.id}/status",
        headers=admin_headers,
        json={"status": "delivered"},
    )
    assert t4.status_code == 200
    assert t4.json()["status"] == "delivered"

    # 6. Illegal transition from delivered -> paid raises 409
    illegal_res = await async_client.patch(
        f"/api/v1/admin/orders/{order.id}/status",
        headers=admin_headers,
        json={"status": "paid"},
    )
    assert illegal_res.status_code == 409
    assert "illegal order transition" in illegal_res.json()["detail"].lower()


@pytest.mark.asyncio
async def test_admin_reconcile_expired_orders(
    async_client: AsyncClient,
    admin_headers: dict[str, str],
    order_fixture: tuple[Order, Payment, Product],
    db_session: AsyncSession,
):
    order, _payment, prod = order_fixture

    # Artificially expire the order
    order.expires_at = datetime.now(UTC) - timedelta(minutes=5)
    await db_session.commit()

    # Trigger admin reconciliation
    res = await async_client.post(
        "/api/v1/admin/orders/reconcile-expired",
        headers=admin_headers,
    )
    assert res.status_code == 200
    data = res.json()
    assert data["cancelled_orders_count"] >= 1
    assert str(order.id) in data["cancelled_order_ids"]

    # Verify order is now cancelled and stock is released
    await db_session.refresh(order)
    assert order.status == OrderStatus.CANCELLED
    await db_session.refresh(prod)
    assert prod.stock == 7
