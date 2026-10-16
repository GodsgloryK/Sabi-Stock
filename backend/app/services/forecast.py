"""Deterministic demand-forecasting math for the Smart Stock AI endpoints.

All numbers shown in the product come from this module. The LLM layer only
rewrites the computed facts into natural language, so the demo cannot show
hallucinated figures.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date, timedelta

HISTORY_WINDOW_DAYS = 60
TREND_WINDOW_DAYS = 30
RATE_WINDOW_DAYS = 14
FORECAST_HORIZON_DAYS = 7
REORDER_COVERAGE_DAYS = 14
NO_SALES_EPSILON = 0.05

URGENCY_OUT = "out"
URGENCY_CRITICAL = "critical"
URGENCY_SOON = "soon"
URGENCY_OK = "ok"
URGENCY_NO_SALES = "no_sales"

_URGENCY_RANK = {
    URGENCY_OUT: 0,
    URGENCY_CRITICAL: 1,
    URGENCY_SOON: 2,
    URGENCY_OK: 3,
    URGENCY_NO_SALES: 4,
}


@dataclass
class ProductForecastResult:
    product_id: object
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
    history: list[tuple[date, int]] = field(default_factory=list)
    forecast: list[tuple[date, int]] = field(default_factory=list)


def trend_percent(recent_units: int, prior_units: int) -> float:
    if prior_units > 0:
        return round((recent_units - prior_units) / prior_units * 100, 1)
    if recent_units > 0:
        return 100.0
    return 0.0


def average_daily_rate(daily_units: dict[date, int], today: date, window_days: int) -> float:
    start = today - timedelta(days=window_days - 1)
    total = sum(units for day, units in daily_units.items() if start <= day <= today)
    return total / window_days


def urgency_for(
    stock_quantity: int,
    rate: float,
    reorder_by_date: date | None,
    today: date,
) -> str:
    if stock_quantity <= 0:
        return URGENCY_OUT
    if rate < NO_SALES_EPSILON:
        return URGENCY_NO_SALES
    if reorder_by_date is None:
        return URGENCY_OK
    if reorder_by_date <= today:
        return URGENCY_CRITICAL
    if reorder_by_date <= today + timedelta(days=7):
        return URGENCY_SOON
    return URGENCY_OK


def compute_product_forecast(
    product_id: object,
    sku: str,
    name: str,
    stock_quantity: int,
    daily_units: dict[date, int],
    today: date,
    lead_time_days: int,
) -> ProductForecastResult:
    recent_start = today - timedelta(days=TREND_WINDOW_DAYS - 1)
    prior_end = recent_start - timedelta(days=1)
    prior_start = prior_end - timedelta(days=TREND_WINDOW_DAYS - 1)

    recent_units = sum(
        units for day, units in daily_units.items() if recent_start <= day <= today
    )
    prior_units = sum(
        units for day, units in daily_units.items() if prior_start <= day <= prior_end
    )
    trend = trend_percent(recent_units, prior_units)

    rate = round(average_daily_rate(daily_units, today, RATE_WINDOW_DAYS), 2)

    days_of_stock: float | None = None
    stockout_date: date | None = None
    reorder_by: date | None = None
    suggested_qty = 0

    if stock_quantity <= 0:
        days_of_stock = 0.0
        stockout_date = today
        reorder_by = today
        suggested_qty = max(math.ceil(rate * (lead_time_days + REORDER_COVERAGE_DAYS)), 1) if rate >= NO_SALES_EPSILON else 0
    elif rate >= NO_SALES_EPSILON:
        days_of_stock = round(stock_quantity / rate, 1)
        stockout_date = today + timedelta(days=math.floor(stock_quantity / rate))
        reorder_by = max(stockout_date - timedelta(days=lead_time_days), today)
        if reorder_by <= today:
            suggested_qty = max(
                math.ceil(rate * (lead_time_days + REORDER_COVERAGE_DAYS)) - stock_quantity,
                1,
            )
        else:
            suggested_qty = max(
                math.ceil(rate * (lead_time_days + REORDER_COVERAGE_DAYS)) - stock_quantity,
                0,
            )

    urgency = urgency_for(stock_quantity, rate, reorder_by, today)
    if urgency in (URGENCY_OUT, URGENCY_CRITICAL, URGENCY_SOON) and suggested_qty <= 0:
        suggested_qty = 1

    history_start = today - timedelta(days=TREND_WINDOW_DAYS - 1)
    history = [
        (day, daily_units.get(day, 0))
        for day in (history_start + timedelta(days=offset) for offset in range(TREND_WINDOW_DAYS))
    ]
    forecast = [
        (today + timedelta(days=offset + 1), int(round(rate)))
        for offset in range(FORECAST_HORIZON_DAYS)
    ]

    return ProductForecastResult(
        product_id=product_id,
        sku=sku,
        name=name,
        stock_quantity=stock_quantity,
        avg_daily_sales=rate,
        trend_pct=trend,
        days_of_stock=days_of_stock,
        predicted_stockout_date=stockout_date,
        reorder_by_date=reorder_by,
        suggested_reorder_qty=suggested_qty,
        urgency=urgency,
        history=history,
        forecast=forecast,
    )


def urgency_rank(urgency: str) -> int:
    return _URGENCY_RANK.get(urgency, 99)


def build_briefing(results: list[ProductForecastResult], lead_time_days: int) -> str:
    urgent = sorted(
        (item for item in results if item.urgency in (URGENCY_OUT, URGENCY_CRITICAL, URGENCY_SOON)),
        key=lambda item: (urgency_rank(item.urgency), item.reorder_by_date or date.today()),
    )
    total_products = len(results)
    if not urgent:
        return (
            f"Stock looks healthy across all {total_products} products — nothing is "
            f"expected to run out in the next {lead_time_days + 7} days, so no "
            "reorders are needed right now."
        )

    top = urgent[0]
    if top.urgency == URGENCY_OUT:
        lead_sentence = (
            f"{top.name} is out of stock right now"
        )
    else:
        stockout = top.predicted_stockout_date.strftime("%b %d") if top.predicted_stockout_date else "soon"
        reorder_by = top.reorder_by_date.strftime("%b %d") if top.reorder_by_date else "today"
        lead_sentence = (
            f"{top.name} is the most urgent reorder: {top.stock_quantity} in stock, "
            f"selling ~{top.avg_daily_sales:g}/day, projected to run out around {stockout} — "
            f"order by {reorder_by} (about {top.suggested_reorder_qty} units)"
        )
    others = len(urgent) - 1
    others_sentence = (
        f" {others} other product{'s' if others != 1 else ''} also "
        f"{'need' if others != 1 else 'needs'} attention soon."
        if others
        else ""
    )
    return f"{lead_sentence}.{others_sentence}"
