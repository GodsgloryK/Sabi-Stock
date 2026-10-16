"""Deterministic anomaly detection over sales history.

Flags unusual patterns a shop owner should look at: sudden sales spikes and
drops, sales recorded below cost, and stock that stopped moving. Pure math —
no LLM involvement, so results are reproducible.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

SEVERITY_HIGH = "high"
SEVERITY_MEDIUM = "medium"
SEVERITY_LOW = "low"

_SEVERITY_RANK = {SEVERITY_HIGH: 0, SEVERITY_MEDIUM: 1, SEVERITY_LOW: 2}


@dataclass
class InsightResult:
    type: str
    severity: str
    title: str
    detail: str
    product_id: object
    product_name: str
    sku: str


def _units_between(daily_units: dict[date, int], start: date, end: date) -> int:
    return sum(units for day, units in daily_units.items() if start <= day <= end)


def compute_insights(
    products: list[dict],
    daily_units: dict[date, int],
    loss_stats: dict[object, dict],
    today: date,
) -> list[InsightResult]:
    insights: list[InsightResult] = []

    recent7_start = today - timedelta(days=6)
    prior21_end = recent7_start - timedelta(days=1)
    prior21_start = prior21_end - timedelta(days=20)
    last14_start = today - timedelta(days=13)
    prior30_end = last14_start - timedelta(days=1)
    prior30_start = prior30_end - timedelta(days=29)

    for product in products:
        product_id = product["id"]
        scoped = daily_units.get(product_id, {})
        recent7_avg = _units_between(scoped, recent7_start, today) / 7
        prior21_avg = _units_between(scoped, prior21_start, prior21_end) / 21
        last14_units = _units_between(scoped, last14_start, today)
        prior30_units = _units_between(scoped, prior30_start, prior30_end)
        stock = int(product["stock_quantity"])

        if prior21_avg >= 1.0 and recent7_avg >= prior21_avg * 3 and (recent7_avg - prior21_avg) >= 2:
            insights.append(
                InsightResult(
                    type="sales_spike",
                    severity=SEVERITY_MEDIUM,
                    title=f"Sales spike: {product['name']}",
                    detail=(
                        f"Selling ~{recent7_avg:.1f} units/day this week vs "
                        f"{prior21_avg:.1f} units/day the month before "
                        f"({recent7_avg / prior21_avg:.1f}x faster). Stock is "
                        "draining sooner than planned — check the restock planner."
                    ),
                    product_id=product_id,
                    product_name=product["name"],
                    sku=product["sku"],
                )
            )
        elif prior21_avg >= 1.0 and recent7_avg <= prior21_avg * 0.4:
            insights.append(
                InsightResult(
                    type="demand_drop",
                    severity=SEVERITY_MEDIUM,
                    title=f"Demand drop: {product['name']}",
                    detail=(
                        f"Down to ~{recent7_avg:.1f} units/day this week from "
                        f"{prior21_avg:.1f} units/day before. Consider a promo "
                        "or review the price."
                    ),
                    product_id=product_id,
                    product_name=product["name"],
                    sku=product["sku"],
                )
            )

        if stock > 0 and last14_units == 0 and prior30_units >= 6:
            insights.append(
                InsightResult(
                    type="stale_stock",
                    severity=SEVERITY_LOW,
                    title=f"Stale stock: {product['name']}",
                    detail=(
                        f"{stock} units in stock but no sales in 14 days, after "
                        f"{prior30_units} units sold in the month before. "
                        "Consider bundling or discounting."
                    ),
                    product_id=product_id,
                    product_name=product["name"],
                    sku=product["sku"],
                )
            )

        loss = loss_stats.get(product_id)
        if loss and loss["loss_sales"] > 0:
            worst = loss["worst_loss"]
            insights.append(
                InsightResult(
                    type="below_cost_sale",
                    severity=SEVERITY_HIGH,
                    title=f"Sold below cost: {product['name']}",
                    detail=(
                        f"{loss['loss_sales']} sale{'s' if loss['loss_sales'] != 1 else ''} "
                        f"in the last 30 days were recorded below the buying price"
                        + (f" (worst: ₦{worst:,.2f} loss per unit)" if worst else "")
                        + ". Check the selling price."
                    ),
                    product_id=product_id,
                    product_name=product["name"],
                    sku=product["sku"],
                )
            )

    insights.sort(
        key=lambda item: (_SEVERITY_RANK.get(item.severity, 9), item.product_name.lower())
    )
    return insights[:12]
