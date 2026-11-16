import asyncio
import logging
import signal
import sys
import threading

from neonize.client import NewClient
from neonize.events import ConnectedEv, MessageEv, PairStatusEv
from neonize.utils import extract_text

from vendoriq.ai.agent import session_manager
from vendoriq.core.config import settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("vendoriq.whatsapp")

# Dedicated asyncio background loop for running agent tasks and DB queries
_async_loop: asyncio.AbstractEventLoop | None = None
_loop_thread: threading.Thread | None = None


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


def build_whatsapp_bot(session_name: str | None = None) -> NewClient:
    db_name = session_name or settings.WHATSAPP_SESSION_NAME
    client = NewClient(db_name)

    @client.event(ConnectedEv)
    def on_connected(_client: NewClient, _data: ConnectedEv) -> None:
        logger.info("🟢 VendorIQ WhatsApp bot successfully connected and online!")

    @client.event(PairStatusEv)
    def on_pair_status(_client: NewClient, data: PairStatusEv) -> None:
        logger.info("📱 WhatsApp Pairing Status: %s (ID: %s)", data.Status, data.ID)

    @client.event(MessageEv)
    def on_message(bot_client: NewClient, message: MessageEv) -> None:
        # Ignore messages sent by the bot itself
        if message.Info.MessageSource.IsFromMe:
            return

        text = extract_text(message.Message)
        if not text or not text.strip():
            return

        chat_jid = message.Info.MessageSource.Chat
        sender_phone = message.Info.MessageSource.Sender.User or getattr(
            chat_jid, "User", "unknown"
        )
        push_name = getattr(message.Info, "Pushname", None)

        logger.info(
            "📩 Incoming message from %s (%s): %s",
            sender_phone,
            push_name or "Anonymous",
            text[:50],
        )

        async def _async_handle() -> None:
            try:
                response = await session_manager.process_message(
                    phone_number=sender_phone,
                    text=text,
                    push_name=push_name,
                )
                bot_client.send_message(to=chat_jid, message=response)
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
