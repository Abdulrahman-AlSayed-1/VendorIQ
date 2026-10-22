import uuid
from datetime import datetime

from pydantic import BaseModel


class CheckoutSessionResponse(BaseModel):
    order_id: uuid.UUID
    order_number: str
    payment_id: uuid.UUID
    stripe_checkout_session_id: str
    checkout_url: str
    expires_at: datetime
