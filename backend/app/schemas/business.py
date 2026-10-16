from uuid import UUID

from pydantic import BaseModel, Field, field_validator
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


class BusinessSettingsResponse(BaseModel):
    business_id: UUID
    business_name: str
    low_stock_threshold: int
    timezone: str


class BusinessSettingsUpdate(BaseModel):
    low_stock_threshold: int = Field(ge=0, le=10_000)
    timezone: str = Field(min_length=1, max_length=64)

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, value: str) -> str:
        value = value.strip()
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError, KeyError) as exc:
            raise ValueError(
                "Unknown timezone. Use an IANA timezone name such as 'Africa/Lagos'."
            ) from exc
        return value
