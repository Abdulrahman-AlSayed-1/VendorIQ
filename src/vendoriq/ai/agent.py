import asyncio
import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from google import genai
from google.genai.chats import AsyncChat
from google.genai.types import GenerateContentConfig

from vendoriq.ai.tools import CustomerTools
from vendoriq.core.config import settings
from vendoriq.core.db import async_session_maker
from vendoriq.models.user import User
from vendoriq.services.auth_service import auth_service

logger = logging.getLogger("vendoriq.agent")

SYSTEM_INSTRUCTION = """\
You are VendorIQ's official intelligent e-commerce shopping assistant on WhatsApp.
Your goal is to assist customers in discovering products, managing their cart, completing checkout, and tracking orders.

Key Guidelines:
1. Tone & Formatting:
   - Be helpful, polite, concise, and friendly.
   - Use WhatsApp formatting naturally (*bold* for product names/totals, _italics_ for hints, bullet points for lists).
   - Keep answers clear and scannable on mobile screens.

2. Tool Usage & Grounding:
   - ALWAYS use your tools to query the catalog, stock, shopping cart, checkout, and orders.
   - NEVER invent or assume prices, products, or order statuses.
   - When suggesting products, include their price, availability, and brief highlights.

3. Cart & Checkout Flow:
   - When a user wants to buy something, find the product ID and use `add_to_cart`.
   - When the user asks to checkout, call `create_checkout`.
   - When `create_checkout` succeeds, provide the order number and the Stripe checkout link clearly. Remind them that stock is reserved for 30 minutes.

4. Error Handling & Limits:
   - If a product is out of stock or requested quantity exceeds available inventory, explain gently and suggest alternatives if available.
   - If an order is not found, verify the order ID or order number format (e.g., ORD-YYYYMMDD-XXXX).
"""


@dataclass
class ChatSession:
    """Represents an active in-memory chat session for a WhatsApp customer."""

    phone_number: str
    user: User
    tools: CustomerTools
    chat: AsyncChat
    last_active_at: datetime
    turn_count: int = 0
    current_model: str = ""


class SessionManager:
    """Manages in-memory chat sessions with sliding window turns and TTL expiration."""

    def __init__(self) -> None:
        self._sessions: dict[str, ChatSession] = {}
        self._lock = asyncio.Lock()
        self._client: genai.Client | None = None

    def _get_client(self) -> genai.Client:
        if self._client is None:
            api_key = settings.GEMINI_API_KEY
            if not api_key or api_key == "YOUR_KEY":
                logger.warning(
                    "GEMINI_API_KEY is not set or using placeholder. Gemini calls will fail."
                )
            self._client = genai.Client(api_key=api_key)
        return self._client

    def _is_session_expired(self, session: ChatSession) -> bool:
        ttl = timedelta(minutes=settings.AI_SESSION_TTL_MINUTES)
        return datetime.now(UTC) - session.last_active_at > ttl

    async def _init_chat(
        self, user: User, model_name: str | None = None
    ) -> tuple[CustomerTools, AsyncChat, str]:
        client = self._get_client()
        tools_instance = CustomerTools(user=user)
        tool_callables = tools_instance.get_tool_callables()

        chosen_model = model_name or settings.GEMINI_MODEL or "gemini-4-hydrogen"

        config = GenerateContentConfig(
            system_instruction=SYSTEM_INSTRUCTION,
            tools=tool_callables,
            temperature=settings.GEMINI_TEMPERATURE,
        )

        chat = client.aio.chats.create(
            model=chosen_model,
            config=config,
        )
        return tools_instance, chat, chosen_model

    async def get_or_create_session(
        self, phone_number: str, push_name: str | None = None
    ) -> ChatSession:
        async with self._lock:
            # Check existing session and TTL
            existing = self._sessions.get(phone_number)
            if existing:
                if (
                    not self._is_session_expired(existing)
                    and existing.turn_count < settings.AI_SESSION_MAX_TURNS
                ):
                    existing.last_active_at = datetime.now(UTC)
                    return existing
                logger.info(
                    "Session for %s expired or exceeded max turns (%d). Recreating.",
                    phone_number,
                    existing.turn_count,
                )

            # Auto-resolve or create user in database
            async with async_session_maker() as db_session:
                user = await auth_service.get_or_create_whatsapp_user(
                    session=db_session,
                    phone_number=phone_number,
                    name=push_name,
                )

            init_res = await self._init_chat(user)
            if len(init_res) == 3:
                tools_instance, chat, chosen_model = init_res
            else:
                tools_instance, chat = init_res[0], init_res[1]
                chosen_model = settings.GEMINI_MODEL

            session = ChatSession(
                phone_number=phone_number,
                user=user,
                tools=tools_instance,
                chat=chat,
                last_active_at=datetime.now(UTC),
                turn_count=0,
                current_model=chosen_model,
            )
            self._sessions[phone_number] = session
            return session

    async def process_message(
        self, phone_number: str, text: str, push_name: str | None = None
    ) -> str:
        """Process an incoming WhatsApp message and return the agent's response."""
        try:
            session = await self.get_or_create_session(phone_number, push_name)
            try:
                response = await session.chat.send_message(text)
            except Exception as primary_err:
                fallback_model = settings.GEMINI_FALLBACK_MODEL
                if fallback_model and session.current_model != fallback_model:
                    logger.warning(
                        "Primary Gemini model '%s' failed for %s: %s. Switching to fallback model '%s'...",
                        session.current_model,
                        phone_number,
                        primary_err,
                        fallback_model,
                    )
                    init_res = await self._init_chat(
                        session.user, model_name=fallback_model
                    )
                    if len(init_res) == 3:
                        session.tools, session.chat, session.current_model = init_res
                    else:
                        session.tools, session.chat = init_res[0], init_res[1]
                        session.current_model = fallback_model

                    response = await session.chat.send_message(text)
                else:
                    raise

            session.turn_count += 1
            session.last_active_at = datetime.now(UTC)

            if response.text:
                return response.text.strip()
            return "I processed your request, but have no text response."
        except Exception:
            logger.exception("Error processing message for %s", phone_number)
            return (
                "⚠️ Sorry, I encountered an issue processing your request. "
                "Please try again in a moment."
            )

    async def cleanup_expired(self) -> int:
        """Periodically purge expired chat sessions from memory."""
        async with self._lock:
            now = datetime.now(UTC)
            ttl = timedelta(minutes=settings.AI_SESSION_TTL_MINUTES)
            expired_keys = [
                phone
                for phone, sess in self._sessions.items()
                if (now - sess.last_active_at) > ttl
            ]
            for key in expired_keys:
                del self._sessions[key]
            return len(expired_keys)


session_manager = SessionManager()
