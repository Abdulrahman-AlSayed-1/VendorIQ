import uuid
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
import stripe
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from vendoriq.models.order import Order, OrderStatus
from vendoriq.models.payment import Payment, PaymentStatus
from vendoriq.models.product import Product
from vendoriq.models.user import User


@pytest.fixture
async def customer_auth_headers(
    async_client: AsyncClient, regular_user: User
) -> dict[str, str]:
    res = await async_client.post(
        "/api/v1/auth/login",
        json={"email": regular_user.email, "password": "Customer123!"},
    )
    token = res.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
async def active_product(db_session: AsyncSession) -> Product:
    prod = Product(
        id=uuid.uuid4(),
        name="Mechanical Keyboard Pro",
        slug="mech-kb-pro",
        sku="KB-001",
        description="RGB keyboard",
        brand="KeyMaster",
        price=Decimal("150.00"),
        currency="usd",
        stock=5,
        attributes={"switches": "blue"},
        image_urls=[],
        is_active=True,
    )
    db_session.add(prod)
    await db_session.commit()
    await db_session.refresh(prod)
    return prod


@pytest.mark.asyncio
async def test_checkout_empty_cart_fails(
    async_client: AsyncClient, customer_auth_headers: dict[str, str]
):
    res = await async_client.post(
        "/api/v1/checkout/sessions", headers=customer_auth_headers
    )
    assert res.status_code == 400
    assert "empty shopping cart" in res.json()["detail"].lower()


@pytest.mark.asyncio
async def test_checkout_successful_initiation(
    async_client: AsyncClient,
    customer_auth_headers: dict[str, str],
    active_product: Product,
    db_session: AsyncSession,
):
    # 1. Add 2 items to cart
    await async_client.post(
        "/api/v1/cart/items",
        headers=customer_auth_headers,
        json={"product_id": str(active_product.id), "quantity": 2},
    )

    # 2. Mock Stripe SDK call
    mock_stripe_session = MagicMock()
    mock_stripe_session.id = "cs_test_mock_123456"
    mock_stripe_session.url = "https://checkout.stripe.com/pay/cs_test_mock_123456"

    with patch(
        "stripe.checkout.Session.create", return_value=mock_stripe_session
    ) as mock_create:
        res = await async_client.post(
            "/api/v1/checkout/sessions", headers=customer_auth_headers
        )
        assert res.status_code == 201
        data = res.json()

        assert data["stripe_checkout_session_id"] == "cs_test_mock_123456"
        assert (
            data["checkout_url"]
            == "https://checkout.stripe.com/pay/cs_test_mock_123456"
        )
        assert "ORD-" in data["order_number"]

        # Verify Stripe SDK call arguments
        mock_create.assert_called_once()
        call_kwargs = mock_create.call_args[1]
        assert call_kwargs["idempotency_key"] == f"checkout_session_{data['order_id']}"
        assert len(call_kwargs["line_items"]) == 1
        line_item = call_kwargs["line_items"][0]
        assert line_item["price_data"]["unit_amount"] == 15000  # $150.00 in cents
        assert line_item["quantity"] == 2

    # 3. Verify stock was reserved in DB (5 - 2 = 3)
    await db_session.refresh(active_product)
    assert active_product.stock == 3

    # 4. Verify cart was cleared
    cart_res = await async_client.get("/api/v1/cart", headers=customer_auth_headers)
    assert len(cart_res.json()["items"]) == 0

    # 5. Verify Order record created in pending_payment state
    order_stmt = select(Order).where(Order.id == uuid.UUID(data["order_id"]))
    order = (await db_session.execute(order_stmt)).scalar_one_or_none()
    assert order is not None
    assert order.status == OrderStatus.PENDING_PAYMENT
    assert order.total == Decimal("300.00")

    # 6. Verify Payment record created in pending state
    payment_stmt = select(Payment).where(Payment.id == uuid.UUID(data["payment_id"]))
    payment = (await db_session.execute(payment_stmt)).scalar_one_or_none()
    assert payment is not None
    assert payment.payment_status == PaymentStatus.PENDING
    assert payment.amount == Decimal("300.00")


@pytest.mark.asyncio
async def test_checkout_gateway_failure_releases_stock(
    async_client: AsyncClient,
    customer_auth_headers: dict[str, str],
    active_product: Product,
    db_session: AsyncSession,
):
    # Add 2 items to cart
    await async_client.post(
        "/api/v1/cart/items",
        headers=customer_auth_headers,
        json={"product_id": str(active_product.id), "quantity": 2},
    )

    # Mock Stripe failure
    with patch(
        "stripe.checkout.Session.create",
        side_effect=stripe.APIConnectionError("Simulated Stripe network timeout"),
    ):
        res = await async_client.post(
            "/api/v1/checkout/sessions", headers=customer_auth_headers
        )
        assert res.status_code == 502

    # Verify inventory was restored via compensating transaction (stock remains 5)
    await db_session.refresh(active_product)
    assert active_product.stock == 5
