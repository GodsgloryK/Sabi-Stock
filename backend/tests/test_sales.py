import unittest
from datetime import date, datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock, patch
from uuid import uuid4

from fastapi import HTTPException, Response

from app.api.dependencies import get_current_user
from app.api.routes import sales as sales_route
from app.main import app
from app.schemas.auth import UserResponse
from app.schemas.sales import SaleCreate

BUSINESS_ID = uuid4()
PRODUCT_ID = uuid4()
SALE_ID = uuid4()
USER = UserResponse(
    id=uuid4(),
    full_name="Sale Owner",
    email="owner@example.com",
    business_id=BUSINESS_ID,
    business_name="Sale Business",
    role="owner",
)
PRODUCT = {
    "id": PRODUCT_ID,
    "name": "Desk Lamp",
    "stock_quantity": 8,
    "buying_price": Decimal("12.50"),
    "selling_price": Decimal("24.99"),
}
SALE = {
    "id": SALE_ID,
    "business_id": BUSINESS_ID,
    "product_id": PRODUCT_ID,
    "product_name": "Desk Lamp",
    "quantity": 3,
    "selling_price": Decimal("24.99"),
    "buying_price": Decimal("12.50"),
    "profit": Decimal("37.47"),
    "total_amount": Decimal("74.97"),
    "created_at": datetime.now(timezone.utc),
}


class SalesApiTests(unittest.TestCase):
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

    def test_sales_routes_require_authentication(self) -> None:
        with self.assertRaises(HTTPException) as raised:
            get_current_user(None)

        self.assertEqual(raised.exception.status_code, 401)
        paths = app.openapi()["paths"]
        operations = [
            paths["/api/sales"]["post"],
            paths["/api/sales"]["get"],
            paths["/api/sales/{sale_id}"]["get"],
            paths["/api/sales/{sale_id}"]["delete"],
        ]
        self.assertTrue(all(operation.get("security") for operation in operations))

    def test_record_sale_locks_business_product_and_saves_price_snapshot(self) -> None:
        cursor, context = self.database_mocks()
        cursor.fetchone.side_effect = [PRODUCT, SALE]

        with patch.object(sales_route, "get_connection", return_value=context):
            response = sales_route.record_sale(
                SaleCreate(product_id=PRODUCT_ID, quantity=3),
                USER,
            )

        self.assertEqual(response.total_amount, Decimal("74.97"))
        self.assertEqual(response.profit, Decimal("37.47"))
        calls = cursor.execute.call_args_list
        self.assertIn("FOR UPDATE", calls[0].args[0])
        self.assertEqual(calls[0].args[1], (PRODUCT_ID, BUSINESS_ID))
        self.assertIn("UPDATE products", calls[1].args[0])
        self.assertEqual(calls[1].args[1], (3, PRODUCT_ID, BUSINESS_ID))
        self.assertIn("INSERT INTO sales", calls[2].args[0])
        self.assertEqual(
            calls[2].args[1],
            (
                BUSINESS_ID,
                PRODUCT_ID,
                3,
                Decimal("24.99"),
                Decimal("12.50"),
                Decimal("37.47"),
                Decimal("74.97"),
            ),
        )

    def test_record_sale_rejects_product_from_another_business(self) -> None:
        cursor, context = self.database_mocks()
        cursor.fetchone.return_value = None

        with patch.object(sales_route, "get_connection", return_value=context):
            with self.assertRaises(HTTPException) as raised:
                sales_route.record_sale(
                    SaleCreate(product_id=PRODUCT_ID, quantity=1),
                    USER,
                )

        self.assertEqual(raised.exception.status_code, 404)
        self.assertEqual(cursor.execute.call_count, 1)
        self.assertEqual(cursor.execute.call_args.args[1], (PRODUCT_ID, BUSINESS_ID))

    def test_record_sale_rejects_quantity_above_stock_without_mutation(self) -> None:
        cursor, context = self.database_mocks()
        cursor.fetchone.return_value = PRODUCT

        with patch.object(sales_route, "get_connection", return_value=context):
            with self.assertRaises(HTTPException) as raised:
                sales_route.record_sale(
                    SaleCreate(product_id=PRODUCT_ID, quantity=9),
                    USER,
                )

        self.assertEqual(raised.exception.status_code, 409)
        self.assertIn("Only 8 units", raised.exception.detail)
        self.assertEqual(cursor.execute.call_count, 1)

    def test_zero_quantity_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            SaleCreate(product_id=PRODUCT_ID, quantity=0)

    def test_list_sales_is_business_scoped(self) -> None:
        cursor, context = self.database_mocks()
        cursor.fetchone.return_value = {"total": 1}
        cursor.fetchall.return_value = [SALE]
        http_response = Response()

        with patch.object(sales_route, "get_connection", return_value=context):
            sales = sales_route.list_sales(USER, http_response, limit=20, offset=10)

        self.assertEqual(len(sales), 1)
        self.assertEqual(http_response.headers["X-Total-Count"], "1")
        count_query, count_parameters = cursor.execute.call_args_list[0].args
        self.assertIn("WHERE s.business_id = %s", count_query)
        self.assertEqual(count_parameters, (BUSINESS_ID,))
        list_query, list_parameters = cursor.execute.call_args_list[1].args
        self.assertIn("WHERE s.business_id = %s", list_query)
        self.assertEqual(list_parameters, (BUSINESS_ID, 20, 10))

    def test_list_sales_applies_date_and_product_filters(self) -> None:
        cursor, context = self.database_mocks()
        cursor.fetchone.return_value = {"total": 0}
        cursor.fetchall.return_value = []
        http_response = Response()

        with patch.object(sales_route, "get_connection", return_value=context):
            sales_route.list_sales(
                USER,
                http_response,
                limit=100,
                offset=0,
                date_from=date(2026, 1, 1),
                date_to=date(2026, 1, 31),
                product_id=PRODUCT_ID,
            )

        list_query, list_parameters = cursor.execute.call_args_list[1].args
        self.assertIn("s.created_at >= %s::timestamptz", list_query)
        self.assertIn("s.created_at < %s::timestamptz", list_query)
        self.assertIn("s.product_id = %s", list_query)
        self.assertEqual(
            list_parameters,
            (BUSINESS_ID, "2026-01-01", "2026-02-01", PRODUCT_ID, 100, 0),
        )

    def test_sales_summary_aggregates_within_filters(self) -> None:
        cursor, context = self.database_mocks()
        cursor.fetchone.return_value = {
            "total_amount": Decimal("150.00"),
            "total_profit": Decimal("60.00"),
            "total_units": 10,
            "sale_count": 4,
        }

        with patch.object(sales_route, "get_connection", return_value=context):
            summary = sales_route.get_sales_summary(USER, date_from=date(2026, 3, 1))

        self.assertEqual(summary.total_units, 10)
        self.assertEqual(summary.sale_count, 4)
        query, parameters = cursor.execute.call_args.args
        self.assertIn("WHERE s.business_id = %s AND s.created_at >= %s::timestamptz", query)
        self.assertEqual(parameters, (BUSINESS_ID, "2026-03-01"))

    def test_get_sale_is_business_scoped(self) -> None:
        cursor, context = self.database_mocks()
        cursor.fetchone.return_value = SALE

        with patch.object(sales_route, "get_connection", return_value=context):
            response = sales_route.get_sale(SALE_ID, USER)

        self.assertEqual(response.id, SALE_ID)
        query, parameters = cursor.execute.call_args.args
        self.assertIn("WHERE s.id = %s AND s.business_id = %s", query)
        self.assertEqual(parameters, (SALE_ID, BUSINESS_ID))

    def test_delete_sale_restores_stock_and_deletes_within_transaction(self) -> None:
        cursor, context = self.database_mocks()
        cursor.fetchone.side_effect = [
            {"id": SALE_ID, "product_id": PRODUCT_ID, "quantity": 3},
            {"id": PRODUCT_ID},
        ]

        with patch.object(sales_route, "get_connection", return_value=context):
            response = sales_route.delete_sale(SALE_ID, USER)

        self.assertEqual(response.status_code, 204)
        calls = cursor.execute.call_args_list
        self.assertIn("FOR UPDATE", calls[0].args[0])
        self.assertEqual(calls[0].args[1], (SALE_ID, BUSINESS_ID))
        self.assertIn("UPDATE products", calls[1].args[0])
        self.assertEqual(calls[1].args[1], (3, PRODUCT_ID, BUSINESS_ID))
        self.assertIn("DELETE FROM sales", calls[2].args[0])
        self.assertEqual(calls[2].args[1], (SALE_ID, BUSINESS_ID))

    def test_delete_other_business_sale_is_not_found_and_does_not_restore_stock(self) -> None:
        cursor, context = self.database_mocks()
        cursor.fetchone.return_value = None

        with patch.object(sales_route, "get_connection", return_value=context):
            with self.assertRaises(HTTPException) as raised:
                sales_route.delete_sale(SALE_ID, USER)

        self.assertEqual(raised.exception.status_code, 404)
        self.assertEqual(cursor.execute.call_count, 1)


if __name__ == "__main__":
    unittest.main()
