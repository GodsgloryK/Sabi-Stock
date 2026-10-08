from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel


class LowStockProduct(BaseModel):
    id: UUID
    name: str
    category: str
    stock_quantity: int


class BestSellingProduct(BaseModel):
    product_id: UUID
    product_name: str
    quantity_sold: int


class DashboardResponse(BaseModel):
    low_stock_threshold: int
    total_products: int
    total_stock_quantity: int
    today_total_sales: Decimal
    today_total_profit: Decimal
    low_stock_products: list[LowStockProduct]
    top_selling_products: list[BestSellingProduct]


class TrendPoint(BaseModel):
    day: str
    total_amount: Decimal
    profit: Decimal
    units_sold: int


class SalesTrendResponse(BaseModel):
    days: int
    points: list[TrendPoint]
