import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch
from uuid import uuid4

import jwt
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from psycopg.rows import dict_row

from app.api import dependencies
from app.api.dependencies import get_current_user, require_owner
from app.api.routes import auth as auth_routes
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


def _mock_owner() -> UserResponse:
    return UserResponse(
        id=uuid4(),
        full_name="Test Owner",
        email="owner@example.com",
        business_id=uuid4(),
        business_name="Test Business",
        role="owner",
    )


def _mock_connection_with_cursor(fetchone_result=None, fetchall_result=None):
    cursor = MagicMock()
    cursor.__enter__.return_value = cursor
    cursor.execute.return_value = cursor
    cursor.fetchone.return_value = fetchone_result
    cursor.fetchall.return_value = fetchall_result or []
    connection = MagicMock()
    connection.cursor.return_value = cursor
    connection_context = MagicMock()
    connection_context.__enter__.return_value = connection
    return connection_context, cursor


class TeamManagementTests(unittest.TestCase):
    def test_list_members_is_scoped_to_owner_business(self) -> None:
        owner = _mock_owner()
        member_row = {
            "id": owner.id,
            "full_name": owner.full_name,
            "email": owner.email,
            "role": "owner",
            "created_at": datetime.now(timezone.utc),
        }
        connection_context, cursor = _mock_connection_with_cursor(fetchall_result=[member_row])

        with patch.object(auth_routes, "get_connection", return_value=connection_context):
            members = auth_routes.list_members(owner)

        self.assertEqual(len(members), 1)
        self.assertEqual(members[0].role, "owner")
        query, parameters = cursor.execute.call_args.args
        self.assertIn("WHERE m.business_id = %s", query)
        self.assertEqual(parameters, (owner.business_id,))

    def test_owner_cannot_remove_self(self) -> None:
        owner = _mock_owner()

        with self.assertRaises(HTTPException) as raised:
            auth_routes.remove_member(owner.id, owner)

        self.assertEqual(raised.exception.status_code, 409)

    def test_remove_member_requires_existing_membership(self) -> None:
        owner = _mock_owner()
        member_id = uuid4()
        connection_context, cursor = _mock_connection_with_cursor(fetchone_result=None)

        with (
            patch.object(auth_routes, "get_connection", return_value=connection_context),
            self.assertRaises(HTTPException) as raised,
        ):
            auth_routes.remove_member(member_id, owner)

        self.assertEqual(raised.exception.status_code, 404)

    def test_remove_member_blocks_removing_other_owner(self) -> None:
        owner = _mock_owner()
        other_owner_id = uuid4()
        membership = {"user_id": other_owner_id, "role": "owner"}
        connection_context, _ = _mock_connection_with_cursor(fetchone_result=membership)

        with (
            patch.object(auth_routes, "get_connection", return_value=connection_context),
            self.assertRaises(HTTPException) as raised,
        ):
            auth_routes.remove_member(other_owner_id, owner)

        self.assertEqual(raised.exception.status_code, 409)

    def test_remove_member_deletes_stock_manager_membership(self) -> None:
        owner = _mock_owner()
        manager_id = uuid4()
        membership = {"user_id": manager_id, "role": "stock_manager"}
        connection_context, cursor = _mock_connection_with_cursor(fetchone_result=membership)

        with patch.object(auth_routes, "get_connection", return_value=connection_context):
            auth_routes.remove_member(manager_id, owner)

        delete_call = cursor.execute.call_args_list[-1]
        self.assertIn("DELETE FROM business_memberships", delete_call.args[0])

    def test_list_invitations_computes_status(self) -> None:
        owner = _mock_owner()
        now = datetime.now(timezone.utc)
        rows = [
            {"id": uuid4(), "expires_at": now + timedelta(hours=1), "used_at": None, "created_at": now},
            {"id": uuid4(), "expires_at": now + timedelta(hours=1), "used_at": now, "created_at": now},
            {"id": uuid4(), "expires_at": now - timedelta(hours=1), "used_at": None, "created_at": now},
        ]
        connection_context, _ = _mock_connection_with_cursor(fetchall_result=rows)

        with patch.object(auth_routes, "get_connection", return_value=connection_context):
            invitations = auth_routes.list_invitations(owner)

        self.assertEqual([item.status for item in invitations], ["pending", "used", "expired"])

    def test_revoke_invitation_rejects_already_used(self) -> None:
        owner = _mock_owner()
        invitation_id = uuid4()
        invitation = {"id": invitation_id, "used_at": datetime.now(timezone.utc)}
        connection_context, _ = _mock_connection_with_cursor(fetchone_result=invitation)

        with (
            patch.object(auth_routes, "get_connection", return_value=connection_context),
            self.assertRaises(HTTPException) as raised,
        ):
            auth_routes.revoke_invitation(invitation_id, owner)

        self.assertEqual(raised.exception.status_code, 409)

    def test_revoke_pending_invitation_marks_it_used(self) -> None:
        owner = _mock_owner()
        invitation_id = uuid4()
        invitation = {"id": invitation_id, "used_at": None}
        connection_context, cursor = _mock_connection_with_cursor(fetchone_result=invitation)

        with patch.object(auth_routes, "get_connection", return_value=connection_context):
            auth_routes.revoke_invitation(invitation_id, owner)

        update_call = cursor.execute.call_args_list[-1]
        self.assertIn("UPDATE business_invitations", update_call.args[0])
        self.assertIn("SET used_at = now()", update_call.args[0])


if __name__ == "__main__":
    unittest.main()
