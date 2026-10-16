import unittest
from unittest.mock import MagicMock, patch
from uuid import uuid4

from fastapi import HTTPException
from pydantic import ValidationError

from app.api.dependencies import require_owner
from app.api.routes import business as business_route
from app.main import app
from app.schemas.auth import UserResponse
from app.schemas.business import BusinessSettingsUpdate

BUSINESS_ID = uuid4()
OWNER = UserResponse(
    id=uuid4(),
    full_name="Settings Owner",
    email="owner@example.com",
    business_id=BUSINESS_ID,
    business_name="Settings Business",
    role="owner",
)
MANAGER = UserResponse(
    id=uuid4(),
    full_name="Settings Manager",
    email="manager@example.com",
    business_id=BUSINESS_ID,
    business_name="Settings Business",
    role="stock_manager",
)
SETTINGS_ROW = {
    "id": BUSINESS_ID,
    "name": "Settings Business",
    "low_stock_threshold": 7,
    "timezone": "Africa/Lagos",
}


class BusinessSettingsTests(unittest.TestCase):
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

    def test_settings_update_rejects_unknown_timezone(self) -> None:
        with self.assertRaises(ValidationError):
            BusinessSettingsUpdate(
                low_stock_threshold=5,
                timezone="Not/A_Real_Zone",
            )

    def test_settings_update_accepts_valid_timezone(self) -> None:
        update = BusinessSettingsUpdate(
            low_stock_threshold=12,
            timezone="Africa/Accra",
        )

        self.assertEqual(update.low_stock_threshold, 12)
        self.assertEqual(update.timezone, "Africa/Accra")

    def test_settings_update_rejects_negative_threshold(self) -> None:
        with self.assertRaises(ValidationError):
            BusinessSettingsUpdate(
                low_stock_threshold=-1,
                timezone="Africa/Lagos",
            )

    def test_get_settings_is_scoped_to_authenticated_business(self) -> None:
        cursor, context = self.database_mocks()
        cursor.fetchone.return_value = SETTINGS_ROW

        with patch.object(business_route, "get_connection", return_value=context):
            response = business_route.get_business_settings(OWNER)

        self.assertEqual(response.business_id, BUSINESS_ID)
        self.assertEqual(response.low_stock_threshold, 7)
        self.assertEqual(response.timezone, "Africa/Lagos")
        query, parameters = cursor.execute.call_args.args
        self.assertIn("WHERE id = %s", query)
        self.assertEqual(parameters, (BUSINESS_ID,))

    def test_update_settings_requires_owner(self) -> None:
        with self.assertRaises(HTTPException) as raised:
            require_owner(MANAGER)

        self.assertEqual(raised.exception.status_code, 403)

    def test_update_settings_writes_threshold_and_timezone(self) -> None:
        cursor, context = self.database_mocks()
        updated_row = {
            "id": BUSINESS_ID,
            "name": "Settings Business",
            "low_stock_threshold": 12,
            "timezone": "Africa/Accra",
        }
        cursor.fetchone.return_value = updated_row

        with patch.object(business_route, "get_connection", return_value=context):
            response = business_route.update_business_settings(
                BusinessSettingsUpdate(
                    low_stock_threshold=12,
                    timezone="Africa/Accra",
                ),
                OWNER,
            )

        self.assertEqual(response.low_stock_threshold, 12)
        self.assertEqual(response.timezone, "Africa/Accra")
        query, parameters = cursor.execute.call_args.args
        self.assertIn("SET low_stock_threshold = %s, timezone = %s", query)
        self.assertEqual(parameters, (12, "Africa/Accra", BUSINESS_ID))

    def test_business_settings_routes_are_registered(self) -> None:
        paths = app.openapi()["paths"]

        self.assertIn("/api/business/settings", paths)
        self.assertIn("get", paths["/api/business/settings"])
        self.assertIn("put", paths["/api/business/settings"])
        self.assertTrue(paths["/api/business/settings"]["get"].get("security"))
        self.assertTrue(paths["/api/business/settings"]["put"].get("security"))


if __name__ == "__main__":
    unittest.main()
