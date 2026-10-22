import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import patch

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from vendoriq.models.order import Order, OrderItem, OrderStatus
from vendoriq.models.payment import Payment, PaymentStatus
from vendoriq.models.product import Product
from vendoriq.models.user import User


@pytest.fixture
async def pending_order_with_payment(
    db_session: AsyncSession, regular_user: User
) -> tuple[Order, Payment, Product]:
    # Create product with reserved stock (originally 10, 2 reserved -> 8 in stock)
    prod = Product(
        id=uuid.uuid4(),
        name="Ultra Monitor 4K",
        slug="ultra-monitor-4k",
        sku="MON-001",
        description="High refresh rate display",
        brand="ScreenPro",
        price=Decimal("400.00"),
        currency="usd",
        stock=8,
        attributes={},
        image_urls=[],
        is_active=True,
    )
    db_session.add(prod)

    order_id = uuid.uuid4()
    order = Order(
        id=order_id,
        order_number="ORD-20261022-TEST1",
        user_id=regular_user.id,
        status=OrderStatus.PENDING_PAYMENT,
        currency="usd",
        subtotal=Decimal("800.00"),
        discount=Decimal("0.00"),
        total=Decimal("800.00"),
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
        line_total=Decimal("800.00"),
    )
    payment = Payment(
        id=uuid.uuid4(),
        order_id=order_id,
        payment_provider="stripe",
        payment_status=PaymentStatus.PENDING,
        amount=Decimal("800.00"),
        currency="usd",
        stripe_checkout_session_id="cs_test_wh_session_999",
    )
    db_session.add_all([order, order_item, payment])
    await db_session.commit()
    await db_session.refresh(order)
    await db_session.refresh(payment)
    await db_session.refresh(prod)
    return order, payment, prod


@pytest.mark.asyncio
async def test_webhook_missing_signature(async_client: AsyncClient):
    res = await async_client.post("/api/v1/webhooks/stripe", content=b"{}")
    assert res.status_code == 400
    assert "missing stripe-signature" in res.json()["detail"].lower()


@pytest.mark.asyncio
async def test_webhook_invalid_signature(async_client: AsyncClient):
    headers = {"stripe-signature": "t=123,v1=invalid_sig"}
    res = await async_client.post(
        "/api/v1/webhooks/stripe", content=b"{}", headers=headers
    )
    assert res.status_code == 400
    assert "invalid webhook signature" in res.json()["detail"].lower()


@pytest.mark.asyncio
async def test_webhook_checkout_session_completed_paid(
    async_client: AsyncClient,
    pending_order_with_payment: tuple[Order, Payment, Product],
    db_session: AsyncSession,
):
    order, payment, _ = pending_order_with_payment

    event_payload = {
        "id": "evt_test_payment_succeeded_001",
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "id": payment.stripe_checkout_session_id,
                "payment_status": "paid",
                "payment_intent": "pi_test_intent_777",
            }
        },
    }

    headers = {"stripe-signature": "t=123,v1=valid_mocked_sig"}
    with patch("stripe.Webhook.construct_event", return_value=event_payload):
        res = await async_client.post(
            "/api/v1/webhooks/stripe", content=b'{"fake":"bytes"}', headers=headers
        )
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "success"

    # Verify Order is marked paid
    await db_session.refresh(order)
    assert order.status == OrderStatus.PAID

    # Verify Payment is marked succeeded with PaymentIntent ID
    await db_session.refresh(payment)
    assert payment.payment_status == PaymentStatus.SUCCEEDED
    assert payment.stripe_payment_intent_id == "pi_test_intent_777"


@pytest.mark.asyncio
async def test_webhook_idempotent_duplicate_delivery(
    async_client: AsyncClient,
    pending_order_with_payment: tuple[Order, Payment, Product],
    db_session: AsyncSession,
):
    _, payment, _ = pending_order_with_payment

    event_payload = {
        "id": "evt_test_duplicate_002",
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "id": payment.stripe_checkout_session_id,
                "payment_status": "paid",
            }
        },
    }
    headers = {"stripe-signature": "t=123,v1=valid_mocked_sig"}

    with patch("stripe.Webhook.construct_event", return_value=event_payload):
        # First delivery
        res1 = await async_client.post(
            "/api/v1/webhooks/stripe", content=b'{"fake":"bytes"}', headers=headers
        )
        assert res1.status_code == 200
        assert res1.json()["status"] == "success"

        # Duplicate delivery
        res2 = await async_client.post(
            "/api/v1/webhooks/stripe", content=b'{"fake":"bytes"}', headers=headers
        )
        assert res2.status_code == 200
        assert res2.json()["status"] == "already_processed"


@pytest.mark.asyncio
async def test_webhook_checkout_session_expired_releases_stock(
    async_client: AsyncClient,
    pending_order_with_payment: tuple[Order, Payment, Product],
    db_session: AsyncSession,
):
    order, payment, prod = pending_order_with_payment
    assert prod.stock == 8  # 2 units were reserved

    event_payload = {
        "id": "evt_test_expired_003",
        "type": "checkout.session.expired",
        "data": {
            "object": {
                "id": payment.stripe_checkout_session_id,
            }
        },
    }
    headers = {"stripe-signature": "t=123,v1=valid_mocked_sig"}

    with patch("stripe.Webhook.construct_event", return_value=event_payload):
        res = await async_client.post(
            "/api/v1/webhooks/stripe", content=b'{"fake":"bytes"}', headers=headers
        )
        assert res.status_code == 200
        assert res.json()["status"] == "success"

    # Order cancelled
    await db_session.refresh(order)
    assert order.status == OrderStatus.CANCELLED

    # Payment cancelled
    await db_session.refresh(payment)
    assert payment.payment_status == PaymentStatus.CANCELLED

    # Stock restored from 8 to 10
    await db_session.refresh(prod)
    assert prod.stock == 10
