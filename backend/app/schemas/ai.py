from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class HistoryPoint(BaseModel):
    day: date
    units: int


class ProductForecast(BaseModel):
    product_id: UUID
    sku: str
    name: str
    stock_quantity: int
    avg_daily_sales: float
    trend_pct: float
    days_of_stock: float | None
    predicted_stockout_date: date | None
    reorder_by_date: date | None
    suggested_reorder_qty: int
    urgency: str
    history: list[HistoryPoint]
    forecast: list[HistoryPoint]


class ForecastResponse(BaseModel):
    briefing: str
    briefing_source: str
    lead_time_days: int
    generated_at: datetime
    products: list[ProductForecast]


class Insight(BaseModel):
    type: str
    severity: str
    title: str
    detail: str
    product_id: UUID | None
    product_name: str | None
    sku: str | None


class InsightsResponse(BaseModel):
    generated_at: datetime
    insights: list[Insight]


class ChatTurn(BaseModel):
    role: str
    text: str = Field(min_length=1, max_length=2000)

    @field_validator("role")
    @classmethod
    def validate_role(cls, value: str) -> str:
        if value not in {"user", "assistant"}:
            raise ValueError("Role must be 'user' or 'assistant'.")
        return value


class AssistantRequest(BaseModel):
    message: str = Field(min_length=1, max_length=1000)
    history: list[ChatTurn] = Field(default_factory=list, max_length=10)


class AssistantResponse(BaseModel):
    reply: str
    source: str
