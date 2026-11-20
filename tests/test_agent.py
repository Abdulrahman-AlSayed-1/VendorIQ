import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from vendoriq.ai.agent import SessionManager
from vendoriq.ai.bot import check_and_notify_paid_orders, is_private_chat
from vendoriq.ai.tools import CustomerTools
from vendoriq.models.category import Category
from vendoriq.models.order import Order, OrderItem, OrderStatus
from vendoriq.models.product import Product
from vendoriq.models.user import User, UserRole
from vendoriq.services.auth_service import auth_service
from vendoriq.services.payment_service import payment_service


@pytest.mark.asyncio
async def test_get_or_create_whatsapp_user(
    db_session: AsyncSession, override_ai_session_maker
):
    phone = "+1 (555) 019-2834"
    user1 = await auth_service.get_or_create_whatsapp_user(
        session=db_session,
        phone_number=phone,
        name="Alice WhatsApp",
    )
    assert user1.id is not None
    assert user1.email == "whatsapp_15550192834@vendoriq.com"
    assert user1.role == UserRole.CUSTOMER
    assert user1.name == "Alice WhatsApp"

    # Calling again should retrieve the exact same record
    user2 = await auth_service.get_or_create_whatsapp_user(
        session=db_session,
        phone_number=phone,
    )
    assert user2.id == user1.id


@pytest.mark.asyncio
async def test_customer_tools_catalog_and_cart(
    db_session: AsyncSession, regular_user: User, override_ai_session_maker
):
    # Setup category & product
    cat = Category(
        id=uuid.uuid4(),
        name="Wearables",
        slug="wearables",
        description="Smart devices",
        is_active=True,
    )
    db_session.add(cat)
    await db_session.flush()

    prod = Product(
        id=uuid.uuid4(),
        name="Smart Fitness Watch",
        slug="smart-fitness-watch",
        sku="WBL-WCH-001",
        description="Fitness tracker with heart rate monitor",
        price=Decimal("99.99"),
        stock=10,
        is_active=True,
        category_id=cat.id,
    )
    db_session.add(prod)
    await db_session.commit()

    tools = CustomerTools(user=regular_user)

    # 1. List categories
    cats = await tools.list_categories()
    assert len(cats) >= 1
    assert any(c["slug"] == "wearables" for c in cats)

    # 2. Search products
    search_res = await tools.search_products(query="Fitness")
    assert search_res["total_found"] >= 1
    assert search_res["products"][0]["name"] == "Smart Fitness Watch"

    # 3. Get product details
    details = await tools.get_product_details(str(prod.id))
    assert details["sku"] == "WBL-WCH-001"
    assert details["price"] == 99.99
    assert details["stock"] == 10

    # 4. Add to cart
    add_res = await tools.add_to_cart(str(prod.id), quantity=2)
    assert add_res["status"] == "success"
    assert add_res["cart_item_count"] == 2
    assert add_res["grand_total"] == 199.98

    # 5. View cart
    cart_view = await tools.get_cart()
    assert cart_view["item_count"] == 2
    assert len(cart_view["items"]) == 1
    item_id = cart_view["items"][0]["item_id"]

    # 6. Update cart item
    upd_res = await tools.update_cart_item(item_id, quantity=3)
    assert upd_res["status"] == "success"
    assert upd_res["cart_item_count"] == 3

    # 7. Remove item from cart
    rem_res = await tools.remove_from_cart(item_id)
    assert rem_res["status"] == "success"
    assert rem_res["cart_item_count"] == 0

    # 8. Clear cart
    await tools.add_to_cart(str(prod.id), quantity=1)
    clear_res = await tools.clear_cart()
    assert clear_res["status"] == "success"
    cart_after = await tools.get_cart()
    assert cart_after["item_count"] == 0


@pytest.mark.asyncio
async def test_customer_tools_checkout_and_orders(
    db_session: AsyncSession, regular_user: User, monkeypatch, override_ai_session_maker
):
    # Setup product
    prod = Product(
        id=uuid.uuid4(),
        name="ANC Earbuds",
        slug="anc-earbuds",
        sku="AUD-EAR-001",
        description="Active noise cancelling earbuds",
        price=Decimal("49.99"),
        stock=5,
        is_active=True,
    )
    db_session.add(prod)
    await db_session.commit()

    tools = CustomerTools(user=regular_user)
    await tools.add_to_cart(str(prod.id), quantity=1)

    # Mock Stripe Checkout Session creation
    mock_stripe_session = MagicMock()
    mock_stripe_session.id = "cs_test_mock_12345"
    mock_stripe_session.url = "https://checkout.stripe.com/pay/cs_test_mock_12345"
    monkeypatch.setattr(
        payment_service,
        "create_checkout_session",
        lambda *args, **kwargs: mock_stripe_session,
    )

    # Initiate checkout via tool
    checkout_res = await tools.create_checkout()
    assert checkout_res["status"] == "success"
    order_number = checkout_res["order_number"]
    assert order_number.startswith("ORD-")
    assert "https://checkout.stripe.com" in checkout_res["checkout_url"]

    # Check order status by order number
    order_status = await tools.check_order_status(order_number)
    assert order_status["order_number"] == order_number
    assert order_status["status"] == "pending_payment"
    assert order_status["total"] == 49.99

    # List order history
    history = await tools.list_order_history()
    assert history["total_orders"] >= 1
    assert history["orders"][0]["order_number"] == order_number

    # Cancel order
    cancel_res = await tools.cancel_order(order_number)
    assert cancel_res["status"] == "success"
    assert cancel_res["order_status"] == "cancelled"


@pytest.mark.asyncio
async def test_session_manager_lifecycle(
    db_session: AsyncSession, monkeypatch, override_ai_session_maker
):
    mgr = SessionManager()

    # Mock Gemini client initialization
    mock_chat = MagicMock()

    async def mock_init_chat(user):
        return CustomerTools(user), mock_chat

    monkeypatch.setattr(mgr, "_init_chat", mock_init_chat)

    sess1 = await mgr.get_or_create_session("+15551112233", "Bob")
    assert sess1.phone_number == "+15551112233"
    assert sess1.user.name == "Bob"

    # Getting same session returns cached instance
    sess2 = await mgr.get_or_create_session("+15551112233")
    assert sess2 is sess1

    # Simulate expired session
    sess1.last_active_at = datetime.now(UTC) - timedelta(hours=2)
    cleaned = await mgr.cleanup_expired()
    assert cleaned == 1
    assert "+15551112233" not in mgr._sessions


@pytest.mark.asyncio
async def test_gemini_model_fallback_on_error(
    db_session: AsyncSession, monkeypatch, override_ai_session_maker
):
    """Verify that when the primary model fails, the session manager automatically switches to the fallback model."""
    mgr = SessionManager()

    primary_chat = MagicMock()
    # Simulate primary model rate limit / overload failure
    primary_chat.send_message = AsyncMock(
        side_effect=Exception(
            "429 ResourceExhausted: Model overloaded or quota exceeded"
        )
    )

    fallback_chat = MagicMock()
    fallback_resp = MagicMock()
    fallback_resp.text = "Hello! I am ready to help you shop."
    fallback_chat.send_message = AsyncMock(return_value=fallback_resp)

    async def mock_init_chat(user, model_name=None):
        if model_name == "gemini-2.0-flash":
            return CustomerTools(user), fallback_chat, "gemini-2.0-flash"
        return CustomerTools(user), primary_chat, "gemini-4-hydrogen"

    monkeypatch.setattr(mgr, "_init_chat", mock_init_chat)

    response_text = await mgr.process_message(
        phone_number="+15554443322",
        text="Find me a mechanical keyboard",
    )

    # 1. User gets the successful response from fallback model
    assert response_text == "Hello! I am ready to help you shop."

    # 2. Verify primary model was tried, failed, and fallback model was called
    primary_chat.send_message.assert_called_once_with("Find me a mechanical keyboard")
    fallback_chat.send_message.assert_called_once_with("Find me a mechanical keyboard")

    # 3. Session now points to the fallback model
    session = mgr._sessions["+15554443322"]
    assert session.current_model == "gemini-2.0-flash"
    assert session.turn_count == 1


def test_is_private_chat_filter():
    """Verify group chats and broadcasts are strictly ignored, and only direct private chats pass."""

    def make_mock_message(is_group: bool, server: str, user: str = "123456789"):
        chat_jid = MagicMock()
        chat_jid.Server = server
        chat_jid.User = user

        source = MagicMock()
        source.IsGroup = is_group
        source.Chat = chat_jid

        info = MagicMock()
        info.MessageSource = source

        msg = MagicMock()
        msg.Info = info
        return msg

    # Direct 1-on-1 private chat -> ALLOW
    assert (
        is_private_chat(make_mock_message(is_group=False, server="s.whatsapp.net"))
        is True
    )
    assert is_private_chat(make_mock_message(is_group=False, server="c.us")) is True

    # Group chats -> IGNORE
    assert is_private_chat(make_mock_message(is_group=True, server="g.us")) is False
    assert (
        is_private_chat(make_mock_message(is_group=True, server="s.whatsapp.net"))
        is False
    )
    assert is_private_chat(make_mock_message(is_group=False, server="g.us")) is False

    # Broadcast lists & Newsletters/Channels -> IGNORE
    assert (
        is_private_chat(make_mock_message(is_group=False, server="broadcast")) is False
    )
    assert (
        is_private_chat(make_mock_message(is_group=False, server="newsletter")) is False
    )

    # Malformed messages without Info or MessageSource -> IGNORE
    empty_msg = MagicMock()
    empty_msg.Info = None
    assert is_private_chat(empty_msg) is False


@pytest.mark.asyncio
async def test_proactive_order_confirmation(
    db_session: AsyncSession, override_ai_session_maker
):
    """Verify newly paid orders trigger a single proactive confirmation and update whatsapp_notified_at."""
    # 1. Create a WhatsApp user
    wa_user = await auth_service.get_or_create_whatsapp_user(
        session=db_session,
        phone_number="+15559876543",
        name="Charlie Test",
    )

    # 2. Create a PAID order without notification timestamp
    order = Order(
        id=uuid.uuid4(),
        order_number="ORD-20261117-TEST01",
        user_id=wa_user.id,
        status=OrderStatus.PAID,
        currency="usd",
        subtotal=Decimal("120.00"),
        discount=Decimal("0.00"),
        total=Decimal("120.00"),
        expires_at=datetime.now(UTC) + timedelta(minutes=30),
        whatsapp_notified_at=None,
    )
    db_session.add(order)
    await db_session.flush()

    item = OrderItem(
        id=uuid.uuid4(),
        order_id=order.id,
        product_name_snapshot="Mechanical Keyboard",
        sku_snapshot="KB-001",
        unit_price_snapshot=Decimal("120.00"),
        quantity=1,
        line_total=Decimal("120.00"),
    )
    db_session.add(item)
    await db_session.commit()

    # 3. Mock WhatsApp bot client
    mock_bot = MagicMock()
    mock_bot.send_message.return_value = MagicMock(ID="msg_test_123")

    # 4. Run check_and_notify_paid_orders
    notified_count = await check_and_notify_paid_orders(
        bot_client=mock_bot,
        session_factory=override_ai_session_maker,
    )
    assert notified_count == 1
    mock_bot.send_message.assert_called_once()
    call_args = mock_bot.send_message.call_args[1]
    assert "ORD-20261117-TEST01" in call_args["message"]
    assert "Mechanical Keyboard" in call_args["message"]
    assert "120.00" in call_args["message"]

    # Refresh order and check whatsapp_notified_at is populated
    await db_session.refresh(order)
    assert order.whatsapp_notified_at is not None

    # 5. Subsequent run should NOT resend (Idempotent)
    mock_bot.send_message.reset_mock()
    second_run = await check_and_notify_paid_orders(
        bot_client=mock_bot,
        session_factory=override_ai_session_maker,
    )
    assert second_run == 0
    mock_bot.send_message.assert_not_called()
