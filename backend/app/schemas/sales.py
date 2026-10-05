from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field


class SaleCreate(BaseModel):
    product_id: UUID
    quantity: int = Field(gt=0, le=2_147_483_647)


class SaleResponse(BaseModel):
    id: UUID
    business_id: UUID
    product_id: UUID
    product_name: str
    quantity: int
    selling_price: Decimal
    buying_price: Decimal
    profit: Decimal
    total_amount: Decimal
    created_at: datetime
