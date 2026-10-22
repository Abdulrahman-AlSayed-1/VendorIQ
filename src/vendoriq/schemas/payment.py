import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from vendoriq.models.payment import PaymentStatus


class PaymentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    order_id: uuid.UUID
    payment_provider: str
    payment_status: PaymentStatus
    amount: Decimal
    currency: str
    stripe_checkout_session_id: str
    stripe_payment_intent_id: str | None
    failure_message: str | None
    created_at: datetime
    updated_at: datetime
