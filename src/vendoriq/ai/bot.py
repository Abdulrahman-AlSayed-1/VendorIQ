import asyncio
import logging
import signal
import sys
import threading
import time
from concurrent.futures import Future
from datetime import UTC, datetime
from typing import Any

from neonize.client import NewClient, build_jid
from neonize.events import ConnectedEv, MessageEv, PairStatusEv
from neonize.utils import extract_text
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import selectinload

from vendoriq.ai.agent import session_manager
from vendoriq.core.config import settings
from vendoriq.core.db import async_session_maker
from vendoriq.models.order import Order, OrderStatus

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("vendoriq.whatsapp")

# Dedicated asyncio background loop for running agent tasks and DB queries
_async_loop: asyncio.AbstractEventLoop | None = None
_loop_thread: threading.Thread | None = None

# Track messages sent by the bot to prevent echo loops when testing via "Message Yourself"
_sent_message_ids: set[str] = set()
_recent_sent_texts: dict[str, float] = {}
# Cache known JID objects by user/phone identifier for accurate proactive delivery
_user_jids: dict[str, Any] = {}
_notification_task: Future[None] | None = None


def get_async_loop() -> asyncio.AbstractEventLoop:
    global _async_loop, _loop_thread
    if _async_loop is None or not _async_loop.is_running():
        _async_loop = asyncio.new_event_loop()
        _loop_thread = threading.Thread(
            target=_async_loop.run_forever,
            name="VendorIQ-Agent-Loop",
            daemon=True,
        )
        _loop_thread.start()
        logger.info("Initialized background agent asyncio event loop.")
    return _async_loop


def is_private_chat(message: MessageEv) -> bool:
    """Return True if the incoming message is a 1-on-1 private direct chat (including self-chat).

    Excludes group chats, broadcast lists, and newsletter/channel updates.
    """
    info = getattr(message, "Info", None)
    if info is None:
        return False

    source = getattr(info, "MessageSource", None)
    if source is None:
        return False

    if getattr(source, "IsGroup", False):
        return False

    chat_jid = getattr(source, "Chat", None)
    if chat_jid is None:
        return False

    server = getattr(chat_jid, "Server", "")
    return server not in ("g.us", "broadcast", "newsletter")


async def check_and_notify_paid_orders(
    bot_client: NewClient,
    session_factory: async_sessionmaker[AsyncSession] | None = None,
) -> int:
    """Find orders marked as PAID that haven't received a WhatsApp confirmation yet, and send confirmation."""
    factory = session_factory or async_session_maker
    notified_count = 0

    async with factory() as session:
        stmt = (
            select(Order)
            .options(selectinload(Order.user), selectinload(Order.items))
            .where(
                Order.status == OrderStatus.PAID,
                Order.whatsapp_notified_at.is_(None),
            )
            .order_by(Order.created_at.asc())
        )
        orders = (await session.execute(stmt)).scalars().all()

        for order in orders:
            user_email = order.user.email if order.user else ""
            is_whatsapp_user = (
                user_email.startswith("whatsapp_") and "@vendoriq.com" in user_email
            )

            if is_whatsapp_user:
                phone = user_email.removeprefix("whatsapp_").split("@")[0].lstrip("+")
                items_summary = (
                    "\n".join(
                        f"  • {item.quantity}x *{item.product_name_snapshot}* (${item.unit_price_snapshot:.2f})"
                        for item in order.items
                    )
                    or "  • 1x Order Item"
                )

                customer_name = order.user.name if order.user else "Customer"
                msg_text = (
                    f"🎉 *Payment Confirmed!*\n\n"
                    f"Hello *{customer_name}*, your payment for order *{order.order_number}* "
                    f"was received successfully.\n\n"
                    f"📦 *Purchased Items:*\n"
                    f"{items_summary}\n\n"
                    f"💵 *Total Paid:* ${order.total:.2f}\n"
                    f"🚚 *Status:* Paid & preparing for shipment\n\n"
                    f"Thank you for shopping with VendorIQ!"
                )

                try:
                    dest_jid = _user_jids.get(phone)
                    if dest_jid is None:
                        dest_jid = build_jid(phone)

                    send_resp = bot_client.send_message(to=dest_jid, message=msg_text)
                    if send_resp and getattr(send_resp, "ID", None):
                        _sent_message_ids.add(send_resp.ID)
                        if len(_sent_message_ids) > 500:
                            _sent_message_ids.pop()

                    _recent_sent_texts[msg_text.strip()] = time.time()
                    logger.info(
                        "📤 Sent proactive payment confirmation for %s to %s",
                        order.order_number,
                        phone,
                    )
                except Exception as send_err:  # noqa: BLE001
                    logger.error(
                        "Failed to deliver proactive confirmation for %s: %s",
                        order.order_number,
                        send_err,
                    )

            # Mark order as notified with UTC timestamp
            order.whatsapp_notified_at = datetime.now(UTC)
            notified_count += 1

        if notified_count > 0:
            await session.commit()

    return notified_count


async def order_notification_loop(
    bot_client: NewClient,
    poll_interval: float = 3.0,
    session_factory: async_sessionmaker[AsyncSession] | None = None,
) -> None:
    """Background polling loop checking for newly paid orders to confirm via WhatsApp."""
    logger.info("Started proactive order notification background worker.")
    while True:
        try:
            await check_and_notify_paid_orders(
                bot_client=bot_client,
                session_factory=session_factory,
            )
        except asyncio.CancelledError:
            logger.info("Order notification background worker stopped.")
            break
        except Exception as err:  # noqa: BLE001
            logger.warning("Error in order notification background worker: %s", err)
        await asyncio.sleep(poll_interval)


def build_whatsapp_bot(session_name: str | None = None) -> NewClient:
    db_name = session_name or settings.WHATSAPP_SESSION_NAME
    client = NewClient(db_name)

    @client.event(ConnectedEv)
    def on_connected(_client: NewClient, _data: ConnectedEv) -> None:
        global _notification_task
        logger.info("🟢 VendorIQ WhatsApp bot successfully connected and online!")
        loop = get_async_loop()
        if _notification_task is None or _notification_task.done():
            _notification_task = asyncio.run_coroutine_threadsafe(
                order_notification_loop(_client), loop
            )

    @client.event(PairStatusEv)
    def on_pair_status(_client: NewClient, data: PairStatusEv) -> None:
        logger.info("📱 WhatsApp Pairing Status: %s (ID: %s)", data.Status, data.ID)

    @client.event(MessageEv)
    def on_message(bot_client: NewClient, message: MessageEv) -> None:
        # Ignore group chats, broadcast channels, and status updates — only reply to private 1-on-1 chats
        if not is_private_chat(message):
            return

        chat_jid = message.Info.MessageSource.Chat
        sender_phone = message.Info.MessageSource.Sender.User or getattr(
            chat_jid, "User", "unknown"
        )
        if sender_phone and chat_jid:
            _user_jids[sender_phone] = chat_jid

        chat_user = getattr(chat_jid, "User", "")
        is_self_chat = sender_phone == chat_user

        # Ignore outgoing messages sent to others, but allow "Message Yourself"
        if message.Info.MessageSource.IsFromMe and not is_self_chat:
            return

        # Prevent bot echo loops if message was sent by the bot itself
        msg_id = getattr(message.Info, "ID", "")
        if msg_id and msg_id in _sent_message_ids:
            return

        text = extract_text(message.Message)
        if not text or not text.strip():
            return

        # Double guard: skip if text matches a response the bot recently sent
        clean_text = text.strip()
        now = time.time()
        if clean_text in _recent_sent_texts and (
            now - _recent_sent_texts[clean_text] < 60
        ):
            return

        push_name = getattr(message.Info, "Pushname", None)

        logger.info(
            "📩 Incoming message from %s (%s) [self_chat=%s]: %s",
            sender_phone,
            push_name or "Anonymous",
            is_self_chat,
            text[:50],
        )

        async def _async_handle() -> None:
            try:
                response = await session_manager.process_message(
                    phone_number=sender_phone,
                    text=text,
                    push_name=push_name,
                )

                # Record sent text and timestamp to prevent self-chat loops
                sent_time = time.time()
                _recent_sent_texts[response.strip()] = sent_time
                # Prune old cache entries (> 120s)
                old_keys = [
                    k for k, t in _recent_sent_texts.items() if sent_time - t > 120
                ]
                for k in old_keys:
                    _recent_sent_texts.pop(k, None)

                send_resp = bot_client.send_message(to=chat_jid, message=response)
                if send_resp and getattr(send_resp, "ID", None):
                    _sent_message_ids.add(send_resp.ID)
                    if len(_sent_message_ids) > 500:
                        _sent_message_ids.pop()

                logger.info(
                    "📤 Sent response to %s (%d chars)", sender_phone, len(response)
                )
            except Exception:
                logger.exception("Failed to handle message for %s", sender_phone)
                try:
                    bot_client.send_message(
                        to=chat_jid,
                        message="⚠️ An unexpected error occurred while processing your message. Please try again.",
                    )
                except Exception as send_err:  # noqa: BLE001
                    logger.warning(
                        "Failed to send fallback error message: %s", send_err
                    )

        loop = get_async_loop()
        asyncio.run_coroutine_threadsafe(_async_handle(), loop)

    return client


def main() -> None:
    """Entry point for running the VendorIQ WhatsApp AI Bot standalone."""
    logger.info("Starting VendorIQ WhatsApp AI Agent Bot...")
    loop = get_async_loop()

    client = build_whatsapp_bot()

    def _shutdown_handler(signum: int, _frame: object) -> None:
        logger.info("Received termination signal (%d). Shutting down bot...", signum)
        if _notification_task is not None and not _notification_task.done():
            _notification_task.cancel()
        try:
            client.disconnect()
        except Exception as disconn_err:  # noqa: BLE001
            logger.debug("Client disconnect note: %s", disconn_err)
        if loop.is_running():
            loop.call_soon_threadsafe(loop.stop)
        sys.exit(0)

    signal.signal(signal.SIGINT, _shutdown_handler)
    signal.signal(signal.SIGTERM, _shutdown_handler)

    try:
        logger.info("Connecting to WhatsApp network (scan QR code if first run)...")
        client.connect()
    except KeyboardInterrupt:
        _shutdown_handler(signal.SIGINT, None)
    except Exception:
        logger.exception("WhatsApp bot encountered fatal error")
        sys.exit(1)


if __name__ == "__main__":
    main()
