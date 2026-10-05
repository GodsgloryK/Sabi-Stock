from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class ProductWrite(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    category: str = Field(min_length=1, max_length=80)
    buying_price: Decimal = Field(ge=0, max_digits=12, decimal_places=2)
    selling_price: Decimal = Field(ge=0, max_digits=12, decimal_places=2)
    stock_quantity: int = Field(ge=0, le=2_147_483_647)

    @field_validator("name", "category")
    @classmethod
    def normalize_required_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("This field cannot be blank.")
        return value


class ProductResponse(BaseModel):
    id: UUID
    business_id: UUID
    name: str
    category: str
    buying_price: Decimal
    selling_price: Decimal
    stock_quantity: int
    created_at: datetime
    updated_at: datetime
