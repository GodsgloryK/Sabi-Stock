import unittest
from datetime import date, datetime, timedelta, timezone
from unittest.mock import MagicMock, patch
from uuid import uuid4

from fastapi import HTTPException

from app.api.routes import ai as ai_routes
from app.main import app
from app.schemas.ai import AssistantRequest
from app.schemas.auth import UserResponse
from app.services import forecast as forecast_service
from app.services import insights as insights_service
from app.services.assistant_rules import local_reply

TODAY = date(2026, 10, 16)
BUSINESS_ID = uuid4()
OWNER = UserResponse(
    id=uuid4(),
    full_name="AI Owner",
    email="owner@example.com",
    business_id=BUSINESS_ID,
    business_name="AI Business",
    role="owner",
)


def _daily_series(days: int, units_per_day: int, today: date = TODAY) -> dict[date, int]:
    return {
        today - timedelta(days=offset): units_per_day
        for offset in range(days)
    }


class ForecastMathTests(unittest.TestCase):
    def test_steady_seller_projects_stockout_and_reorder_date(self) -> None:
        product_id = uuid4()
        result = forecast_service.compute_product_forecast(
            product_id=product_id,
            sku="RICE-1",
            name="Golden Star Rice 5kg",
            stock_quantity=20,
            daily_units=_daily_series(60, 4),
            today=TODAY,
            lead_time_days=3,
        )

        self.assertEqual(result.avg_daily_sales, 4.0)
        self.assertEqual(result.urgency, forecast_service.URGENCY_SOON)
        self.assertEqual(result.predicted_stockout_date, TODAY + timedelta(days=5))
        self.assertEqual(result.reorder_by_date, TODAY + timedelta(days=2))
        self.assertEqual(result.trend_pct, 0.0)
        self.assertEqual(len(result.history), 30)
        self.assertEqual(len(result.forecast), 7)

    def test_stock_covering_only_lead_time_is_critical(self) -> None:
        result = forecast_service.compute_product_forecast(
            product_id=uuid4(),
            sku="NOODLES-1",
            name="Indomie Carton",
            stock_quantity=8,
            daily_units=_daily_series(60, 4),
            today=TODAY,
            lead_time_days=3,
        )

        self.assertEqual(result.urgency, forecast_service.URGENCY_CRITICAL)
        self.assertEqual(result.reorder_by_date, TODAY)
        self.assertGreaterEqual(result.suggested_reorder_qty, 1)

    def test_out_of_stock_product_is_flagged_out(self) -> None:
        result = forecast_service.compute_product_forecast(
            product_id=uuid4(),
            sku="MILK-1",
            name="Peak Milk",
            stock_quantity=0,
            daily_units=_daily_series(60, 2),
            today=TODAY,
            lead_time_days=3,
        )

        self.assertEqual(result.urgency, forecast_service.URGENCY_OUT)
        self.assertEqual(result.predicted_stockout_date, TODAY)

    def test_product_without_sales_is_not_predicted(self) -> None:
        result = forecast_service.compute_product_forecast(
            product_id=uuid4(),
            sku="SLOW-1",
            name="Slow Mover",
            stock_quantity=40,
            daily_units={},
            today=TODAY,
            lead_time_days=3,
        )

        self.assertEqual(result.urgency, forecast_service.URGENCY_NO_SALES)
        self.assertIsNone(result.predicted_stockout_date)
        self.assertIsNone(result.reorder_by_date)
        self.assertEqual(result.suggested_reorder_qty, 0)

    def test_growing_demand_produces_positive_trend(self) -> None:
        daily_units = _daily_series(60, 2)
        for offset in range(30):
            daily_units[TODAY - timedelta(days=offset)] = 6

        result = forecast_service.compute_product_forecast(
            product_id=uuid4(),
            sku="TREND-1",
            name="Trending Product",
            stock_quantity=100,
            daily_units=daily_units,
            today=TODAY,
            lead_time_days=3,
        )

        self.assertGreater(result.trend_pct, 0)

    def test_briefing_names_most_urgent_product(self) -> None:
        urgent = forecast_service.compute_product_forecast(
            product_id=uuid4(),
            sku="RICE-1",
            name="Golden Star Rice 5kg",
            stock_quantity=5,
            daily_units=_daily_series(60, 4),
            today=TODAY,
            lead_time_days=3,
        )
        healthy = forecast_service.compute_product_forecast(
            product_id=uuid4(),
            sku="SUGAR-1",
            name="Sugar",
            stock_quantity=90,
            daily_units=_daily_series(60, 1),
            today=TODAY,
            lead_time_days=3,
        )

        briefing = forecast_service.build_briefing([urgent, healthy], lead_time_days=3)

        self.assertIn("Golden Star Rice 5kg", briefing)
        self.assertIn("order", briefing.lower())

    def test_briefing_reports_healthy_state_when_nothing_urgent(self) -> None:
        healthy = forecast_service.compute_product_forecast(
            product_id=uuid4(),
            sku="SUGAR-1",
            name="Sugar",
            stock_quantity=90,
            daily_units=_daily_series(60, 1),
            today=TODAY,
            lead_time_days=3,
        )

        briefing = forecast_service.build_briefing([healthy], lead_time_days=3)

        self.assertIn("healthy", briefing)


class InsightMathTests(unittest.TestCase):
    def _product(self, stock: int = 20) -> dict:
        product_id = uuid4()
        return {
            "id": product_id,
            "sku": "SKU-1",
            "name": "Test Product",
            "stock_quantity": stock,
        }

    def test_sales_spike_is_detected(self) -> None:
        product = self._product()
        daily = {product["id"]: {}}
        for offset in range(1, 29):
            daily[product["id"]][TODAY - timedelta(days=offset)] = 1
        for offset in range(0, 7):
            daily[product["id"]][TODAY - timedelta(days=offset)] = 8

        results = insights_service.compute_insights([product], daily, {}, TODAY)
        types = [item.type for item in results]

        self.assertIn("sales_spike", types)

    def test_sales_drop_is_detected(self) -> None:
        product = self._product()
        daily = {product["id"]: {}}
        for offset in range(8, 29):
            daily[product["id"]][TODAY - timedelta(days=offset)] = 4
        for offset in range(0, 7):
            daily[product["id"]][TODAY - timedelta(days=offset)] = 0

        results = insights_service.compute_insights([product], daily, {}, TODAY)
        types = [item.type for item in results]

        self.assertIn("demand_drop", types)

    def test_below_cost_sales_are_high_severity(self) -> None:
        product = self._product()
        loss_stats = {
            product["id"]: {"loss_sales": 3, "worst_loss": 250.0},
        }

        results = insights_service.compute_insights(
            [product], {product["id"]: {}}, loss_stats, TODAY
        )

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].type, "below_cost_sale")
        self.assertEqual(results[0].severity, insights_service.SEVERITY_HIGH)
        self.assertIn("3 sales", results[0].detail)

    def test_stale_stock_is_detected(self) -> None:
        product = self._product(stock=15)
        daily = {product["id"]: {}}
        for offset in range(15, 45):
            daily[product["id"]][TODAY - timedelta(days=offset)] = 2

        results = insights_service.compute_insights([product], daily, {}, TODAY)
        types = [item.type for item in results]

        self.assertIn("stale_stock", types)


class AssistantRulesTests(unittest.TestCase):
    def setUp(self) -> None:
        self.snapshot = {
            "business_name": "Demo Shop",
            "date": "2026-10-16",
            "timezone": "Africa/Lagos",
            "low_stock_threshold": 5,
            "today": {"sales_amount": 45000.0, "profit": 12000.0},
            "totals": {"products": 20, "stock_units": 480},
            "low_stock": [{"name": "Peak Milk", "stock": 3}],
            "top_sellers_30d": [{"name": "Indomie Carton", "units": 140}],
            "urgent_reorders": [
                {
                    "name": "Golden Star Rice 5kg",
                    "stock": 5,
                    "rate_per_day": 4.0,
                    "reorder_by": "Oct 16",
                    "suggested_qty": 70,
                    "urgency": "critical",
                }
            ],
        }

    def test_restock_question_uses_computed_forecast(self) -> None:
        reply = local_reply("What should I restock?", self.snapshot)

        self.assertIn("Golden Star Rice 5kg", reply)
        self.assertIn("Oct 16", reply)

    def test_greeting_is_answered_with_capabilities(self) -> None:
        reply = local_reply("Hello", self.snapshot)

        self.assertIn("restock", reply)

    def test_today_sales_question_returns_snapshot_figures(self) -> None:
        reply = local_reply("How much did I make today?", self.snapshot)

        self.assertIn("₦45,000.00", reply)
        self.assertIn("₦12,000.00", reply)

    def test_unknown_question_points_to_supported_topics(self) -> None:
        reply = local_reply("Tell me a joke", self.snapshot)

        self.assertIn("snapshot", reply)


class AiApiTests(unittest.TestCase):
    def test_ai_routes_are_registered_and_secured(self) -> None:
        paths = app.openapi()["paths"]

        for path in ("/api/ai/forecast", "/api/ai/insights", "/api/ai/assistant"):
            self.assertIn(path, paths)
        self.assertTrue(paths["/api/ai/forecast"]["get"].get("security"))
        self.assertTrue(paths["/api/ai/insights"]["get"].get("security"))
        self.assertTrue(paths["/api/ai/assistant"]["post"].get("security"))

    def test_forecast_route_is_business_scoped_and_uses_rules_fallback(self) -> None:
        product_id = uuid4()
        settings_row = {"low_stock_threshold": 5, "timezone": "Africa/Lagos"}
        product_rows = [
            {
                "id": product_id,
                "sku": "RICE-1",
                "name": "Golden Star Rice 5kg",
                "stock_quantity": 20,
            }
        ]
        sales_rows = [
            {
                "product_id": product_id,
                "day": TODAY - timedelta(days=offset),
                "units": 4,
            }
            for offset in range(60)
        ]

        def execute(query, params=None):
            result = MagicMock()
            if "low_stock_threshold" in query:
                result.fetchone.return_value = settings_row
            elif "FROM products" in query:
                result.fetchall.return_value = product_rows
            else:
                result.fetchall.return_value = sales_rows
            return result

        cursor = MagicMock()
        cursor.execute.side_effect = execute
        cursor.__enter__.return_value = cursor
        cursor.__exit__.return_value = False

        connection = MagicMock()
        connection.cursor.return_value = cursor
        context = MagicMock()
        context.__enter__.return_value = connection

        with (
            patch.object(ai_routes, "get_connection", return_value=context),
            patch.object(
                ai_routes.llm_service, "narrate_forecast", return_value=None
            ),
        ):
            response = ai_routes.get_forecast(OWNER)

        self.assertEqual(response.briefing_source, "rules")
        self.assertIn("Golden Star Rice 5kg", response.briefing)
        self.assertEqual(response.products[0].sku, "RICE-1")
        self.assertEqual(len(response.products), 1)
        product_queries = [
            call.args
            for call in cursor.execute.call_args_list
            if "FROM products" in call.args[0]
        ]
        self.assertTrue(all(BUSINESS_ID in params for _, params in product_queries))

    def test_assistant_requires_valid_turn_roles(self) -> None:
        with self.assertRaises(Exception):
            AssistantRequest(message="hi", history=[{"role": "system", "text": "x"}])

    def test_assistant_rate_limit_window(self) -> None:
        key = str(uuid4())
        now = datetime.now(timezone.utc)
        for _ in range(ai_routes.ASSISTANT_RATE_LIMIT):
            ai_routes._assistant_attempts[key].append(now)

        self.assertTrue(ai_routes._assistant_rate_limited(key))
        ai_routes._assistant_attempts[key].clear()

    def test_assistant_rejects_over_limit_requests(self) -> None:
        key = str(uuid4())
        now = datetime.now(timezone.utc)
        for _ in range(ai_routes.ASSISTANT_RATE_LIMIT):
            ai_routes._assistant_attempts[key].append(now)

        with self.assertRaises(HTTPException) as raised:
            ai_routes.assistant(
                AssistantRequest(message="hello"),
                http_request=MagicMock(),
                current_user=UserResponse(
                    id=key,
                    full_name="AI Owner",
                    email="owner@example.com",
                    business_id=BUSINESS_ID,
                    business_name="AI Business",
                    role="owner",
                ),
            )
        ai_routes._assistant_attempts[key].clear()

        self.assertEqual(raised.exception.status_code, 429)


if __name__ == "__main__":
    unittest.main()
