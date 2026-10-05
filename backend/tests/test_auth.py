import unittest
from unittest.mock import MagicMock, patch
from uuid import uuid4

import jwt
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from psycopg.rows import dict_row

from app.api import dependencies
from app.api.dependencies import get_current_user, require_owner
from app.core import security
from app.core.config import settings
from app.schemas.auth import UserResponse

TEST_SECRET = "unit-test-secret-that-is-at-least-32-characters"


class AuthenticationTests(unittest.TestCase):
    def test_password_hash_and_verification(self) -> None:
        hashed_password = security.hash_password("a-long-test-password")

        self.assertTrue(security.verify_password("a-long-test-password", hashed_password))
        self.assertFalse(security.verify_password("wrong-test-password", hashed_password))

    def test_access_token_contains_user_and_business(self) -> None:
        user_id = uuid4()
        business_id = uuid4()

        with patch.object(settings, "jwt_secret_key", TEST_SECRET):
            token = security.create_access_token(user_id, business_id, "owner")
            claims = security.decode_access_token(token)

        self.assertEqual(claims["sub"], str(user_id))
        self.assertEqual(claims["business_id"], str(business_id))
        self.assertEqual(claims["role"], "owner")

    def test_authenticated_user_lookup_is_scoped_to_token_business(self) -> None:
        user_id = uuid4()
        business_id = uuid4()
        user_record = {
            "id": user_id,
            "full_name": "Test Owner",
            "email": "owner@example.com",
            "business_id": business_id,
            "business_name": "Test Business",
            "role": "owner",
        }
        cursor = MagicMock()
        cursor.__enter__.return_value = cursor
        cursor.execute.return_value = cursor
        cursor.fetchone.return_value = user_record
        connection = MagicMock()
        connection.cursor.return_value = cursor
        connection_context = MagicMock()
        connection_context.__enter__.return_value = connection
        credentials = HTTPAuthorizationCredentials(
            scheme="Bearer",
            credentials="test-token",
        )

        with (
            patch.object(settings, "jwt_secret_key", TEST_SECRET),
            patch.object(dependencies, "decode_access_token", return_value={
                "sub": str(user_id),
                "business_id": str(business_id),
            }),
            patch.object(dependencies, "get_connection", return_value=connection_context),
        ):
            current_user = get_current_user(credentials)

        self.assertEqual(current_user.business_id, business_id)
        query, parameters = cursor.execute.call_args.args
        self.assertIn("WHERE u.id = %s AND b.id = %s", query)
        self.assertEqual(parameters, (user_id, business_id))
        connection.cursor.assert_called_once_with(row_factory=dict_row)

    def test_invalid_token_is_rejected(self) -> None:
        with patch.object(settings, "jwt_secret_key", TEST_SECRET):
            with self.assertRaises(jwt.InvalidTokenError):
                security.decode_access_token("not-a-jwt")

    def test_stock_manager_cannot_create_invitations(self) -> None:
        manager = UserResponse(
            id=uuid4(),
            full_name="Test Manager",
            email="manager@example.com",
            business_id=uuid4(),
            business_name="Test Business",
            role="stock_manager",
        )

        with self.assertRaises(HTTPException) as raised:
            require_owner(manager)

        self.assertEqual(raised.exception.status_code, 403)


if __name__ == "__main__":
    unittest.main()
