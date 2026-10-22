import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from vendoriq.models.order import OrderStatus


class OrderItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    product_id: uuid.UUID | None
    product_name_snapshot: str
    sku_snapshot: str
    unit_price_snapshot: Decimal
    quantity: int
    line_total: Decimal
    created_at: datetime


class OrderRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    order_number: str
    user_id: uuid.UUID
    status: OrderStatus
    currency: str
    subtotal: Decimal
    discount: Decimal
    total: Decimal
    expires_at: datetime
    created_at: datetime
    updated_at: datetime
    items: list[OrderItemRead] = Field(default_factory=list)


class OrderPaginationResponse(BaseModel):
    items: list[OrderRead]
    total: int
    page: int
    page_size: int
    total_pages: int


class OrderStatusUpdate(BaseModel):
    status: OrderStatus
