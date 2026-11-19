import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class ProductBase(BaseModel):
    name: str = Field(..., min_length=2, max_length=255)
    slug: str = Field(..., min_length=2, max_length=255)
    sku: str = Field(..., min_length=2, max_length=100)
    description: str | None = None
    brand: str | None = None
    price: Decimal = Field(..., ge=Decimal("0.00"), decimal_places=2)
    currency: str = Field("usd", min_length=3, max_length=3)
    stock: int = Field(0, ge=0)
    attributes: dict[str, Any] = Field(default_factory=dict)
    image_urls: list[str] = Field(default_factory=list)


class ProductCreate(ProductBase):
    category_id: uuid.UUID | None = None


class ProductUpdate(BaseModel):
    category_id: uuid.UUID | None = None
    name: str | None = Field(None, min_length=2, max_length=255)
    slug: str | None = Field(None, min_length=2, max_length=255)
    sku: str | None = Field(None, min_length=2, max_length=100)
    description: str | None = None
    brand: str | None = None
    price: Decimal | None = Field(None, ge=Decimal("0.00"), decimal_places=2)
    currency: str | None = Field(None, min_length=3, max_length=3)
    stock: int | None = Field(None, ge=0)
    attributes: dict[str, Any] | None = None
    image_urls: list[str] | None = None
    is_active: bool | None = None


class ProductStockUpdate(BaseModel):
    stock: int = Field(..., ge=0)


class ProductRead(ProductBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    category_id: uuid.UUID | None
    is_active: bool
    created_at: datetime
    updated_at: datetime


class ProductPaginationResponse(BaseModel):
    items: list[ProductRead]
    total: int
    page: int
    page_size: int
    total_pages: int


ProductSortOption = Literal["price_asc", "price_desc", "newest"]
