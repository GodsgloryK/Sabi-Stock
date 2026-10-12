from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field


class SaleCreate(BaseModel):
    product_id: UUID
    quantity: int = Field(gt=0, le=2_147_483_647)


class SaleBatchItemCreate(BaseModel):
    product_id: UUID
    quantity: int = Field(gt=0, le=2_147_483_647)


class SaleBatchCreate(BaseModel):
    items: list[SaleBatchItemCreate] = Field(min_length=1, max_length=50)


class SaleResponse(BaseModel):
    id: UUID
    business_id: UUID
    product_id: UUID
    product_name: str
    product_sku: str
    quantity: int
    selling_price: Decimal
    buying_price: Decimal
    profit: Decimal
    total_amount: Decimal
    recorded_by_user_id: UUID | None = None
    recorded_by_name: str | None = None
    created_at: datetime


class SalesSummaryResponse(BaseModel):
    total_amount: Decimal
    total_profit: Decimal
    total_units: int
    sale_count: int
