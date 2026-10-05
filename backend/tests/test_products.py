import unittest
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock, patch
from uuid import uuid4

from fastapi import HTTPException

from app.api.dependencies import get_current_user
from app.api.routes import products as products_route
from app.main import app
from app.schemas.auth import UserResponse
from app.schemas.products import ProductWrite

BUSINESS_ID = uuid4()
USER = UserResponse(
    id=uuid4(),
    full_name="Product Owner",
    email="owner@example.com",
    business_id=BUSINESS_ID,
    business_name="Product Business",
    role="owner",
)
PRODUCT_ID = uuid4()
PRODUCT = {
    "id": PRODUCT_ID,
    "business_id": BUSINESS_ID,
    "name": "Desk Lamp",
    "category": "Lighting",
    "buying_price": Decimal("12.50"),
    "selling_price": Decimal("24.99"),
    "stock_quantity": 8,
    "created_at": datetime.now(timezone.utc),
    "updated_at": datetime.now(timezone.utc),
}
PRODUCT_INPUT = {
    "name": "Desk Lamp",
    "category": "Lighting",
    "buying_price": "12.50",
    "selling_price": "24.99",
    "stock_quantity": 8,
}


class ProductApiTests(unittest.TestCase):
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

    def test_products_routes_require_authentication(self) -> None:
        with self.assertRaises(HTTPException) as raised:
            get_current_user(None)

        self.assertEqual(raised.exception.status_code, 401)
        paths = app.openapi()["paths"]
        secured_operations = [
            paths["/api/products"]["get"],
            paths["/api/products"]["post"],
            paths["/api/products/{product_id}"]["get"],
            paths["/api/products/{product_id}"]["put"],
            paths["/api/products/{product_id}"]["delete"],
        ]
        self.assertTrue(all(operation.get("security") for operation in secured_operations))

    def test_create_product_uses_authenticated_business(self) -> None:
        cursor, context = self.database_mocks()
        cursor.fetchone.return_value = PRODUCT

        with patch.object(products_route, "get_connection", return_value=context):
            response = products_route.create_product(
                ProductWrite.model_validate(PRODUCT_INPUT),
                USER,
            )

        self.assertEqual(response.business_id, BUSINESS_ID)
        self.assertEqual(cursor.execute.call_args.args[1][0], BUSINESS_ID)

    def test_list_products_is_scoped_to_authenticated_business(self) -> None:
        cursor, context = self.database_mocks()
        cursor.fetchall.return_value = [PRODUCT]

        with patch.object(products_route, "get_connection", return_value=context):
            response = products_route.list_products(
                USER,
                search="lamp",
                category="Lighting",
            )

        self.assertEqual(len(response), 1)
        query, parameters = cursor.execute.call_args.args
        self.assertIn("WHERE business_id = %s", query)
        self.assertEqual(parameters, [BUSINESS_ID, "%lamp%", "Lighting"])

    def test_other_business_product_is_not_found(self) -> None:
        cursor, context = self.database_mocks()
        cursor.fetchone.return_value = None

        with patch.object(products_route, "get_connection", return_value=context):
            with self.assertRaises(HTTPException) as raised:
                products_route.get_product(PRODUCT_ID, USER)

        self.assertEqual(raised.exception.status_code, 404)
        query, parameters = cursor.execute.call_args.args
        self.assertIn("WHERE id = %s AND business_id = %s", query)
        self.assertEqual(parameters, (PRODUCT_ID, BUSINESS_ID))

    def test_update_scopes_by_product_and_business(self) -> None:
        cursor, context = self.database_mocks()
        cursor.fetchone.return_value = PRODUCT

        with patch.object(products_route, "get_connection", return_value=context):
            response = products_route.update_product(
                PRODUCT_ID,
                ProductWrite.model_validate(PRODUCT_INPUT),
                USER,
            )

        self.assertEqual(response.business_id, BUSINESS_ID)
        self.assertEqual(cursor.execute.call_args.args[1][-2:], (PRODUCT_ID, BUSINESS_ID))

    def test_delete_does_not_delete_another_business_product(self) -> None:
        cursor, context = self.database_mocks()
        cursor.rowcount = 0

        with patch.object(products_route, "get_connection", return_value=context):
            with self.assertRaises(HTTPException) as raised:
                products_route.delete_product(PRODUCT_ID, USER)

        self.assertEqual(raised.exception.status_code, 404)
        query, parameters = cursor.execute.call_args.args
        self.assertIn("WHERE id = %s AND business_id = %s", query)
        self.assertEqual(parameters, (PRODUCT_ID, BUSINESS_ID))

    def test_negative_values_are_rejected(self) -> None:
        invalid_product = {**PRODUCT_INPUT, "buying_price": -1}

        with self.assertRaises(ValueError):
            ProductWrite.model_validate(invalid_product)

    def test_product_delete_returns_no_content_for_own_business(self) -> None:
        cursor, context = self.database_mocks()
        cursor.rowcount = 1

        with patch.object(products_route, "get_connection", return_value=context):
            response = products_route.delete_product(PRODUCT_ID, USER)

        self.assertEqual(response.status_code, 204)


if __name__ == "__main__":
    unittest.main()
