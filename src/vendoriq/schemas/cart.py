import uuid
from decimal import Decimal

from pydantic import BaseModel, Field


class CartItemAdd(BaseModel):
    product_id: uuid.UUID
    quantity: int = Field(1, ge=1, description="Quantity to add to cart")


class CartItemUpdate(BaseModel):
    quantity: int = Field(..., ge=1, description="Absolute quantity to set")


class CartItemRead(BaseModel):
    id: uuid.UUID
    product_id: uuid.UUID
    product_name: str
    sku: str
    unit_price: Decimal
    quantity: int
    line_total: Decimal
    in_stock: bool
    available_stock: int


class CartRead(BaseModel):
    id: uuid.UUID
    items: list[CartItemRead]
    currency: str = "usd"
    subtotal: Decimal
    discount_total: Decimal = Decimal("0.00")
    grand_total: Decimal
    item_count: int
