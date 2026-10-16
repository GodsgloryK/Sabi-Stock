from collections import defaultdict, deque
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import psycopg
from fastapi import APIRouter, HTTPException, Request, status
from psycopg.rows import dict_row

from app.api.dependencies import CurrentUser
from app.core.config import settings
from app.db.connection import get_connection
from app.schemas.ai import (
    AssistantRequest,
    AssistantResponse,
    ForecastResponse,
    HistoryPoint,
    Insight,
    InsightsResponse,
    ProductForecast,
)
from app.services import forecast as forecast_service
from app.services import insights as insights_service
from app.services import llm as llm_service
from app.services.assistant_rules import local_reply

router = APIRouter()

ASSISTANT_RATE_LIMIT = 20
ASSISTANT_RATE_WINDOW_SECONDS = 60
_assistant_attempts: dict[str, deque] = defaultdict(deque)

INSIGHTS_WINDOW_DAYS = forecast_service.HISTORY_WINDOW_DAYS


def _database_unavailable() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="AI analysis is temporarily unavailable. Please try again shortly.",
    )


def _business_settings(business_id) -> tuple[str, int]:
    try:
        with get_connection() as connection:
            with connection.cursor(row_factory=dict_row) as cursor:
                row = cursor.execute(
                    """
                    SELECT low_stock_threshold, timezone
                    FROM businesses
                    WHERE id = %s
                    """,
                    (business_id,),
                ).fetchone()
    except (psycopg.Error, RuntimeError) as exc:
        raise _database_unavailable() from exc
    if row is None:
        raise HTTPException(status_code=404, detail="Business not found.")
    return row["timezone"], row["low_stock_threshold"]


def _today_for(tz_name: str) -> date:
    try:
        zone = ZoneInfo(tz_name)
    except Exception:
        zone = ZoneInfo("Africa/Lagos")
    return datetime.now(zone).date()


def _load_products(business_id) -> list[dict]:
    try:
        with get_connection() as connection:
            with connection.cursor(row_factory=dict_row) as cursor:
                return cursor.execute(
                    """
                    SELECT id, sku, name, stock_quantity
                    FROM products
                    WHERE business_id = %s
                    ORDER BY lower(name), sku
                    """,
                    (business_id,),
                ).fetchall()
    except (psycopg.Error, RuntimeError) as exc:
        raise _database_unavailable() from exc


def _load_daily_units(business_id, tz_name: str, window_days: int) -> dict:
    """product_id -> {date: units_sold} for the trailing window."""
    try:
        with get_connection() as connection:
            with connection.cursor(row_factory=dict_row) as cursor:
                rows = cursor.execute(
                    """
                    SELECT product_id,
                           (created_at AT TIME ZONE %s)::date AS day,
                           sum(quantity)::integer AS units
                    FROM sales
                    WHERE business_id = %s
                      AND created_at >= now() - make_interval(days => %s)
                    GROUP BY product_id, day
                    """,
                    (tz_name, business_id, window_days),
                ).fetchall()
    except (psycopg.Error, RuntimeError) as exc:
        raise _database_unavailable() from exc

    daily: dict = defaultdict(dict)
    for row in rows:
        day = row["day"]
        if isinstance(day, datetime):
            day = day.date()
        daily[row["product_id"]][day] = row["units"]
    return daily


def _load_loss_stats(business_id) -> dict:
    try:
        with get_connection() as connection:
            with connection.cursor(row_factory=dict_row) as cursor:
                rows = cursor.execute(
                    """
                    SELECT product_id,
                           count(*) FILTER (WHERE selling_price < buying_price)::integer
                               AS loss_sales,
                           COALESCE(
                               max(buying_price - selling_price) FILTER (
                                   WHERE selling_price < buying_price
                               ),
                               0
                           ) AS worst_loss
                    FROM sales
                    WHERE business_id = %s
                      AND created_at >= now() - interval '30 days'
                    GROUP BY product_id
                    """,
                    (business_id,),
                ).fetchall()
    except (psycopg.Error, RuntimeError) as exc:
        raise _database_unavailable() from exc
    return {row["product_id"]: row for row in rows}


def _compute_forecasts(
    products: list[dict],
    daily_units: dict,
    today: date,
    lead_time_days: int,
) -> list[forecast_service.ProductForecastResult]:
    results = [
        forecast_service.compute_product_forecast(
            product_id=product["id"],
            sku=product["sku"],
            name=product["name"],
            stock_quantity=int(product["stock_quantity"]),
            daily_units=daily_units.get(product["id"], {}),
            today=today,
            lead_time_days=lead_time_days,
        )
        for product in products
    ]
    results.sort(
        key=lambda item: (
            forecast_service.urgency_rank(item.urgency),
            item.reorder_by_date or date.max,
            item.name.lower(),
        )
    )
    return results


def _briefing_facts(
    results: list[forecast_service.ProductForecastResult],
    lead_time_days: int,
    low_stock_count: int,
) -> dict:
    urgent = [
        item
        for item in results
        if item.urgency
        in (
            forecast_service.URGENCY_OUT,
            forecast_service.URGENCY_CRITICAL,
            forecast_service.URGENCY_SOON,
        )
    ]
    top = urgent[0] if urgent else None
    return {
        "total_products": len(results),
        "products_needing_reorder": len(urgent),
        "products_below_low_stock_threshold": low_stock_count,
        "restock_lead_time_days": lead_time_days,
        "total_suggested_reorder_units": sum(
            item.suggested_reorder_qty for item in urgent
        ),
        "most_urgent": (
            {
                "name": top.name,
                "stock": top.stock_quantity,
                "avg_units_per_day": top.avg_daily_sales,
                "trend_percent_vs_previous_month": top.trend_pct,
                "projected_stockout": top.predicted_stockout_date,
                "order_by": top.reorder_by_date,
                "suggested_order_quantity": top.suggested_reorder_qty,
            }
            if top
            else None
        ),
    }


@router.get("/forecast", response_model=ForecastResponse)
def get_forecast(current_user: CurrentUser) -> ForecastResponse:
    tz_name, low_stock_threshold = _business_settings(current_user.business_id)
    today = _today_for(tz_name)
    products = _load_products(current_user.business_id)
    daily_units = _load_daily_units(
        current_user.business_id, tz_name, forecast_service.HISTORY_WINDOW_DAYS
    )
    results = _compute_forecasts(
        products, daily_units, today, settings.restock_lead_time_days
    )

    facts = _briefing_facts(results, settings.restock_lead_time_days, low_stock_threshold)
    briefing = llm_service.narrate_forecast(facts)
    briefing_source = "gemini"
    if not briefing:
        briefing = forecast_service.build_briefing(results, settings.restock_lead_time_days)
        briefing_source = "rules"

    return ForecastResponse(
        briefing=briefing,
        briefing_source=briefing_source,
        lead_time_days=settings.restock_lead_time_days,
        generated_at=datetime.now(timezone.utc),
        products=[
            ProductForecast(
                product_id=item.product_id,
                sku=item.sku,
                name=item.name,
                stock_quantity=item.stock_quantity,
                avg_daily_sales=item.avg_daily_sales,
                trend_pct=item.trend_pct,
                days_of_stock=item.days_of_stock,
                predicted_stockout_date=item.predicted_stockout_date,
                reorder_by_date=item.reorder_by_date,
                suggested_reorder_qty=item.suggested_reorder_qty,
                urgency=item.urgency,
                history=[HistoryPoint(day=day, units=units) for day, units in item.history],
                forecast=[HistoryPoint(day=day, units=units) for day, units in item.forecast],
            )
            for item in results
        ],
    )


@router.get("/insights", response_model=InsightsResponse)
def get_insights(current_user: CurrentUser) -> InsightsResponse:
    tz_name, _threshold = _business_settings(current_user.business_id)
    today = _today_for(tz_name)
    products = _load_products(current_user.business_id)
    daily_units = _load_daily_units(
        current_user.business_id, tz_name, forecast_service.HISTORY_WINDOW_DAYS
    )
    loss_stats = _load_loss_stats(current_user.business_id)

    results = insights_service.compute_insights(products, daily_units, loss_stats, today)
    return InsightsResponse(
        generated_at=datetime.now(timezone.utc),
        insights=[
            Insight(
                type=item.type,
                severity=item.severity,
                title=item.title,
                detail=item.detail,
                product_id=item.product_id,
                product_name=item.product_name,
                sku=item.sku,
            )
            for item in results
        ],
    )


def _assistant_rate_key(user_id) -> str:
    return str(user_id)


def _assistant_rate_limited(key: str) -> bool:
    now = datetime.now(timezone.utc)
    window_start = now - timedelta(seconds=ASSISTANT_RATE_WINDOW_SECONDS)
    attempts = _assistant_attempts[key]
    while attempts and attempts[0] < window_start:
        attempts.popleft()
    return len(attempts) >= ASSISTANT_RATE_LIMIT


def _record_assistant_request(key: str) -> None:
    _assistant_attempts[key].append(datetime.now(timezone.utc))


def _build_snapshot(current_user: CurrentUser) -> dict:
    tz_name, threshold = _business_settings(current_user.business_id)
    today = _today_for(tz_name)

    try:
        with get_connection() as connection:
            with connection.cursor(row_factory=dict_row) as cursor:
                summary = cursor.execute(
                    """
                    SELECT
                        COALESCE((SELECT sum(stock_quantity) FROM products
                                  WHERE business_id = %s), 0)::bigint AS stock_units,
                        (SELECT count(*) FROM products WHERE business_id = %s)::integer
                            AS product_count,
                        COALESCE((
                            SELECT sum(total_amount) FROM sales
                            WHERE business_id = %s
                              AND created_at >= ((now() AT TIME ZONE %s)::date)::timestamptz
                              AND created_at < (((now() AT TIME ZONE %s)::date) + 1)::timestamptz
                        ), 0) AS today_sales,
                        COALESCE((
                            SELECT sum(profit) FROM sales
                            WHERE business_id = %s
                              AND created_at >= ((now() AT TIME ZONE %s)::date)::timestamptz
                              AND created_at < (((now() AT TIME ZONE %s)::date) + 1)::timestamptz
                        ), 0) AS today_profit,
                        COALESCE((
                            SELECT sum(quantity) FROM sales
                            WHERE business_id = %s
                              AND created_at >= now() - interval '30 days'
                        ), 0)::bigint AS units_30d
                    """,
                    (
                        current_user.business_id,
                        current_user.business_id,
                        current_user.business_id,
                        tz_name,
                        tz_name,
                        current_user.business_id,
                        tz_name,
                        tz_name,
                        current_user.business_id,
                    ),
                ).fetchone()
                low_rows = cursor.execute(
                    """
                    SELECT name, stock_quantity
                    FROM products
                    WHERE business_id = %s AND stock_quantity < %s
                    ORDER BY stock_quantity, lower(name)
                    LIMIT 8
                    """,
                    (current_user.business_id, threshold),
                ).fetchall()
                top_rows = cursor.execute(
                    """
                    SELECT p.name, sum(s.quantity)::bigint AS units
                    FROM sales AS s
                    JOIN products AS p ON p.id = s.product_id
                        AND p.business_id = s.business_id
                    WHERE s.business_id = %s
                      AND s.created_at >= now() - interval '30 days'
                    GROUP BY p.id, p.name
                    ORDER BY units DESC, lower(p.name)
                    LIMIT 5
                    """,
                    (current_user.business_id,),
                ).fetchall()
    except (psycopg.Error, RuntimeError) as exc:
        raise _database_unavailable() from exc

    products = _load_products(current_user.business_id)
    daily_units = _load_daily_units(
        current_user.business_id, tz_name, forecast_service.HISTORY_WINDOW_DAYS
    )
    results = _compute_forecasts(
        products, daily_units, today, settings.restock_lead_time_days
    )
    urgent = [
        item
        for item in results
        if item.urgency
        in (
            forecast_service.URGENCY_OUT,
            forecast_service.URGENCY_CRITICAL,
            forecast_service.URGENCY_SOON,
        )
    ][:6]

    return {
        "business_name": current_user.business_name,
        "date": today.isoformat(),
        "timezone": tz_name,
        "low_stock_threshold": threshold,
        "today": {
            "sales_amount": float(summary["today_sales"]),
            "profit": float(summary["today_profit"]),
        },
        "totals": {
            "products": summary["product_count"],
            "stock_units": summary["stock_units"],
            "units_sold_last_30_days": summary["units_30d"],
        },
        "low_stock": [
            {"name": row["name"], "stock": int(row["stock_quantity"])}
            for row in low_rows
        ],
        "top_sellers_30d": [
            {"name": row["name"], "units": int(row["units"])} for row in top_rows
        ],
        "urgent_reorders": [
            {
                "name": item.name,
                "stock": item.stock_quantity,
                "rate_per_day": item.avg_daily_sales,
                "order_by": item.reorder_by_date.isoformat()
                if item.reorder_by_date
                else None,
                "reorder_by": item.reorder_by_date.strftime("%b %d")
                if item.reorder_by_date
                else "as soon as possible",
                "suggested_qty": item.suggested_reorder_qty,
                "urgency": item.urgency,
            }
            for item in urgent
        ],
    }


@router.post("/assistant", response_model=AssistantResponse)
def assistant(
    request: AssistantRequest,
    http_request: Request,
    current_user: CurrentUser,
) -> AssistantResponse:
    rate_key = _assistant_rate_key(current_user.id)
    if _assistant_rate_limited(rate_key):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many assistant messages. Please wait a minute and try again.",
        )
    _record_assistant_request(rate_key)

    snapshot = _build_snapshot(current_user)
    history = [{"role": turn.role, "text": turn.text} for turn in request.history]

    reply = llm_service.assistant_reply(request.message, history, snapshot)
    if reply:
        return AssistantResponse(reply=reply, source="gemini")
    return AssistantResponse(
        reply=local_reply(request.message, snapshot),
        source="rules",
    )
