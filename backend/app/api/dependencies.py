from typing import Annotated
from uuid import UUID

import jwt
import psycopg
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from psycopg.rows import dict_row

from app.core.security import decode_access_token
from app.db.connection import get_connection
from app.schemas.auth import UserResponse

bearer_scheme = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None, Depends(bearer_scheme)
    ],
) -> UserResponse:
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="A valid access token is required.",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if credentials is None:
        raise unauthorized

    try:
        payload = decode_access_token(credentials.credentials)
        user_id = UUID(str(payload["sub"]))
        business_id = UUID(str(payload["business_id"]))
    except (jwt.InvalidTokenError, KeyError, TypeError, ValueError):
        raise unauthorized from None
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc

    try:
        with get_connection() as connection:
            with connection.cursor(row_factory=dict_row) as cursor:
                user = cursor.execute(
                    """
                    SELECT u.id, u.full_name, u.email, b.id AS business_id,
                           b.name AS business_name, m.role
                    FROM users AS u
                    JOIN business_memberships AS m ON m.user_id = u.id
                    JOIN businesses AS b ON b.id = m.business_id
                    WHERE u.id = %s AND b.id = %s
                    """,
                    (user_id, business_id),
                ).fetchone()
    except (psycopg.Error, RuntimeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database is unavailable.",
        ) from exc

    if user is None:
        raise unauthorized

    return UserResponse.model_validate(user)


CurrentUser = Annotated[UserResponse, Depends(get_current_user)]


def require_owner(current_user: CurrentUser) -> UserResponse:
    if current_user.role != "owner":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only business owners can create invitations.",
        )
    return current_user


BusinessOwner = Annotated[UserResponse, Depends(require_owner)]
