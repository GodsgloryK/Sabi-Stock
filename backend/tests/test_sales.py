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
from app.schemas.sales import SaleBatchCreate, SaleBatchItemCreate, SaleCreate

BUSINESS_ID = uuid4()
PRODUCT_ID = uuid4()
PRODUCT_TWO_ID = uuid4()
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
    "sku": "LAMP-1",
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
    "product_sku": "LAMP-1",
    "recorded_by_user_id": USER.id,
    "recorded_by_name": "Sale Owner",
    "quantity": 3,
    "selling_price": Decimal("24.99"),
    "buying_price": Decimal("12.50"),
    "profit": Decimal("37.47"),
    "total_amount": Decimal("74.97"),
    "created_at": datetime.now(timezone.utc),
}
PRODUCT_TWO = {
    "id": PRODUCT_TWO_ID,
    "sku": "CHAIR-2",
    "name": "Office Chair",
    "stock_quantity": 5,
    "buying_price": Decimal("40.00"),
    "selling_price": Decimal("75.00"),
}
SALE_TWO = {
    "id": uuid4(),
    "business_id": BUSINESS_ID,
    "product_id": PRODUCT_TWO_ID,
    "product_name": "Office Chair",
    "product_sku": "CHAIR-2",
    "recorded_by_user_id": USER.id,
    "recorded_by_name": "Sale Owner",
    "quantity": 1,
    "selling_price": Decimal("75.00"),
    "buying_price": Decimal("40.00"),
    "profit": Decimal("35.00"),
    "total_amount": Decimal("75.00"),
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
            paths["/api/sales/batch"]["post"],
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
                USER.id,
                3,
                Decimal("24.99"),
                Decimal("12.50"),
                Decimal("37.47"),
                Decimal("74.97"),
            ),
        )
        self.assertEqual(response.recorded_by_user_id, USER.id)
        self.assertEqual(response.recorded_by_name, USER.full_name)

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

    def test_record_sales_batch_records_each_item_and_decrements_stock(self) -> None:
        cursor, context = self.database_mocks()
        cursor.fetchall.return_value = [PRODUCT, PRODUCT_TWO]
        cursor.fetchone.side_effect = [SALE, SALE_TWO]

        with patch.object(sales_route, "get_connection", return_value=context):
            response = sales_route.record_sales_batch(
                SaleBatchCreate(
                    items=[
                        SaleBatchItemCreate(product_id=PRODUCT_ID, quantity=3),
                        SaleBatchItemCreate(product_id=PRODUCT_TWO_ID, quantity=1),
                    ]
                ),
                USER,
            )

        self.assertEqual(len(response), 2)
        self.assertEqual(response[0].total_amount, Decimal("74.97"))
        self.assertEqual(response[1].total_amount, Decimal("75.00"))
        calls = cursor.execute.call_args_list
        select_query, select_parameters = calls[0].args
        self.assertIn("FOR UPDATE", select_query)
        self.assertEqual(select_parameters, (BUSINESS_ID, [PRODUCT_ID, PRODUCT_TWO_ID]))
        self.assertIn("UPDATE products", calls[1].args[0])
        self.assertEqual(calls[1].args[1], (3, PRODUCT_ID, BUSINESS_ID))
        self.assertIn("INSERT INTO sales", calls[2].args[0])
        self.assertIn("UPDATE products", calls[3].args[0])
        self.assertEqual(calls[3].args[1], (1, PRODUCT_TWO_ID, BUSINESS_ID))
        self.assertIn("INSERT INTO sales", calls[4].args[0])

    def test_record_sales_batch_aggregates_duplicate_items_before_stock_check(self) -> None:
        cursor, context = self.database_mocks()
        cursor.fetchall.return_value = [PRODUCT]

        with patch.object(sales_route, "get_connection", return_value=context):
            with self.assertRaises(HTTPException) as raised:
                sales_route.record_sales_batch(
                    SaleBatchCreate(
                        items=[
                            SaleBatchItemCreate(product_id=PRODUCT_ID, quantity=5),
                            SaleBatchItemCreate(product_id=PRODUCT_ID, quantity=5),
                        ]
                    ),
                    USER,
                )

        self.assertEqual(raised.exception.status_code, 409)
        self.assertIn("Desk Lamp", raised.exception.detail)
        self.assertEqual(cursor.execute.call_count, 1)

    def test_record_sales_batch_rejects_product_from_another_business(self) -> None:
        cursor, context = self.database_mocks()
        cursor.fetchall.return_value = [PRODUCT]

        with patch.object(sales_route, "get_connection", return_value=context):
            with self.assertRaises(HTTPException) as raised:
                sales_route.record_sales_batch(
                    SaleBatchCreate(
                        items=[
                            SaleBatchItemCreate(product_id=PRODUCT_ID, quantity=1),
                            SaleBatchItemCreate(product_id=uuid4(), quantity=1),
                        ]
                    ),
                    USER,
                )

        self.assertEqual(raised.exception.status_code, 404)
        self.assertEqual(cursor.execute.call_count, 1)

    def test_record_sales_batch_rejects_quantity_above_stock_without_mutation(self) -> None:
        cursor, context = self.database_mocks()
        cursor.fetchall.return_value = [PRODUCT]

        with patch.object(sales_route, "get_connection", return_value=context):
            with self.assertRaises(HTTPException) as raised:
                sales_route.record_sales_batch(
                    SaleBatchCreate(
                        items=[SaleBatchItemCreate(product_id=PRODUCT_ID, quantity=9)]
                    ),
                    USER,
                )

        self.assertEqual(raised.exception.status_code, 409)
        self.assertIn("only 8 available", raised.exception.detail)
        self.assertEqual(cursor.execute.call_count, 1)

    def test_record_sales_batch_attaches_recording_member(self) -> None:
        cursor, context = self.database_mocks()
        cursor.fetchall.return_value = [PRODUCT]
        cursor.fetchone.return_value = SALE

        with patch.object(sales_route, "get_connection", return_value=context):
            response = sales_route.record_sales_batch(
                SaleBatchCreate(
                    items=[SaleBatchItemCreate(product_id=PRODUCT_ID, quantity=3)]
                ),
                USER,
            )

        self.assertEqual(response[0].recorded_by_user_id, USER.id)
        self.assertEqual(response[0].recorded_by_name, USER.full_name)
        insert_parameters = cursor.execute.call_args_list[2].args[1]
        self.assertEqual(insert_parameters[2], USER.id)

    def test_list_sales_returns_recording_member(self) -> None:
        cursor, context = self.database_mocks()
        cursor.fetchone.return_value = {"total": 1}
        cursor.fetchall.return_value = [SALE]
        http_response = Response()

        with patch.object(sales_route, "get_connection", return_value=context):
            sales = sales_route.list_sales(USER, http_response, limit=20, offset=0)

        list_query = cursor.execute.call_args_list[1].args[0]
        self.assertIn("LEFT JOIN users AS u ON u.id = s.recorded_by_user_id", list_query)
        self.assertIn("u.full_name AS recorded_by_name", list_query)
        self.assertEqual(sales[0].recorded_by_name, "Sale Owner")

    def test_batch_create_validates_item_count(self) -> None:
        with self.assertRaises(ValueError):
            SaleBatchCreate(items=[])

        with self.assertRaises(ValueError):
            SaleBatchCreate(
                items=[
                    SaleBatchItemCreate(product_id=uuid4(), quantity=1)
                    for _ in range(51)
                ]
            )


if __name__ == "__main__":
    unittest.main()
