import unittest
from decimal import Decimal
from unittest.mock import MagicMock, patch
from uuid import uuid4

from fastapi import HTTPException

from app.api.dependencies import get_current_user
from app.api.routes import dashboard as dashboard_route
from app.main import app
from app.schemas.auth import UserResponse

BUSINESS_ID = uuid4()
USER = UserResponse(
    id=uuid4(),
    full_name="Dashboard Owner",
    email="owner@example.com",
    business_id=BUSINESS_ID,
    business_name="Dashboard Business",
    role="owner",
)


class DashboardApiTests(unittest.TestCase):
    def database_mocks(self) -> tuple[MagicMock, MagicMock]:
        cursor = MagicMock()
        cursor.__enter__.return_value = cursor
        cursor.__exit__.return_value = None
        cursor.execute.return_value = cursor
        connection = MagicMock()
        connection.cursor.return_value = cursor
        connection.__enter__.return_value = connection
        context = MagicMock()
        context.__enter__.return_value = connection
        return cursor, context

    def test_dashboard_route_requires_authentication(self) -> None:
        with self.assertRaises(HTTPException) as raised:
            get_current_user(None)

        self.assertEqual(raised.exception.status_code, 401)
        self.assertTrue(app.openapi()["paths"]["/api/dashboard"]["get"].get("security"))

    def test_dashboard_metrics_are_calculated_in_database_and_business_scoped(self) -> None:
        cursor, context = self.database_mocks()
        cursor.fetchone.return_value = {
            "total_products": 12,
            "total_stock_quantity": 84,
            "today_total_sales": Decimal("420.00"),
            "today_total_profit": Decimal("96.50"),
        }
        cursor.fetchall.side_effect = [
            [
                {
                    "id": uuid4(),
                    "name": "Low Item",
                    "category": "General",
                    "stock_quantity": 4,
                }
            ],
            [
                {
                    "product_id": uuid4(),
                    "product_name": "Best Item",
                    "quantity_sold": 25,
                }
            ],
        ]

        with patch.object(dashboard_route, "get_connection", return_value=context):
            response = dashboard_route.get_dashboard(USER)

        self.assertEqual(response.total_products, 12)
        self.assertEqual(response.total_stock_quantity, 84)
        self.assertEqual(response.today_total_sales, Decimal("420.00"))
        self.assertEqual(response.today_total_profit, Decimal("96.50"))
        self.assertEqual(response.low_stock_products[0].stock_quantity, 4)
        self.assertEqual(response.top_selling_products[0].quantity_sold, 25)

        calls = cursor.execute.call_args_list
        summary_query, summary_parameters = calls[0].args
        self.assertIn("CURRENT_DATE", summary_query)
        self.assertIn("sum(profit)", summary_query)
        self.assertEqual(summary_parameters, (BUSINESS_ID,) * 4)
        low_stock_query, low_stock_parameters = calls[1].args
        self.assertIn("stock_quantity < 5", low_stock_query)
        self.assertIn("business_id = %s", low_stock_query)
        self.assertEqual(low_stock_parameters, (BUSINESS_ID,))
        top_query, top_parameters = calls[2].args
        self.assertIn("sum(s.quantity)", top_query)
        self.assertIn("ORDER BY quantity_sold DESC", top_query)
        self.assertIn("LIMIT 5", top_query)
        self.assertEqual(top_parameters, (BUSINESS_ID,))

    def test_dashboard_returns_empty_data_when_business_has_no_records(self) -> None:
        cursor, context = self.database_mocks()
        cursor.fetchone.return_value = {
            "total_products": 0,
            "total_stock_quantity": 0,
            "today_total_sales": Decimal("0"),
            "today_total_profit": Decimal("0"),
        }
        cursor.fetchall.side_effect = [[], []]

        with patch.object(dashboard_route, "get_connection", return_value=context):
            response = dashboard_route.get_dashboard(USER)

        self.assertEqual(response.total_products, 0)
        self.assertEqual(response.low_stock_products, [])
        self.assertEqual(response.top_selling_products, [])


if __name__ == "__main__":
    unittest.main()
