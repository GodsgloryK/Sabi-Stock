from datetime import datetime, timedelta, timezone

import jwt
import psycopg
from fastapi import APIRouter, HTTPException, status
from psycopg.rows import dict_row

from app.api.dependencies import BusinessOwner, CurrentUser
from app.core.config import settings
from app.core.security import (
    create_access_token,
    create_invitation_code,
    hash_invitation_code,
    hash_password,
    verify_password,
)
from app.db.connection import get_connection
from app.schemas.auth import (
    AuthResponse,
    CurrentUserResponse,
    InvitationResponse,
    LoginRequest,
    ManagerRegistration,
    OwnerRegistration,
    UserResponse,
)

router = APIRouter()


def _ensure_jwt_configured() -> None:
    if not settings.jwt_secret_key or len(settings.jwt_secret_key) < 32:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication is not configured. Set JWT_SECRET_KEY to a random secret of at least 32 characters.",
        )


def _duplicate_email_error() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail="An account with this email address already exists.",
    )


def _create_auth_response(user: UserResponse) -> AuthResponse:
    _ensure_jwt_configured()
    token = create_access_token(user.id, user.business_id, user.role)
    return AuthResponse(access_token=token, user=user)


@router.post(
    "/register/owner",
    response_model=AuthResponse,
    status_code=status.HTTP_201_CREATED,
)
def register_owner(request: OwnerRegistration) -> AuthResponse:
    _ensure_jwt_configured()
    hashed_password = hash_password(request.password)

    try:
        with get_connection() as connection:
            with connection.cursor(row_factory=dict_row) as cursor:
                user = cursor.execute(
                    """
                    INSERT INTO users (full_name, email, password_hash)
                    VALUES (%s, %s, %s)
                    RETURNING id, full_name, email
                    """,
                    (request.full_name, request.email, hashed_password),
                ).fetchone()
                business = cursor.execute(
                    """
                    INSERT INTO businesses (name, owner_user_id)
                    VALUES (%s, %s)
                    RETURNING id, name
                    """,
                    (request.business_name, user["id"]),
                ).fetchone()
                cursor.execute(
                    """
                    INSERT INTO business_memberships (user_id, business_id, role)
                    VALUES (%s, %s, 'owner')
                    """,
                    (user["id"], business["id"]),
                )
    except psycopg.errors.UniqueViolation as exc:
        if exc.diag.constraint_name != "users_email_lower_unique":
            raise
        raise _duplicate_email_error() from exc
    except psycopg.Error as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database is unavailable.",
        ) from exc
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc

    response_user = UserResponse(
        id=user["id"],
        full_name=user["full_name"],
        email=user["email"],
        business_id=business["id"],
        business_name=business["name"],
        role="owner",
    )
    return _create_auth_response(response_user)


@router.post(
    "/register/manager",
    response_model=AuthResponse,
    status_code=status.HTTP_201_CREATED,
)
def register_manager(request: ManagerRegistration) -> AuthResponse:
    _ensure_jwt_configured()
    hashed_password = hash_password(request.password)
    invitation_hash = hash_invitation_code(request.invitation_code)

    try:
        with get_connection() as connection:
            with connection.cursor(row_factory=dict_row) as cursor:
                invitation = cursor.execute(
                    """
                    SELECT id, business_id
                    FROM business_invitations
                    WHERE token_hash = %s
                      AND used_at IS NULL
                      AND expires_at > now()
                    FOR UPDATE
                    """,
                    (invitation_hash,),
                ).fetchone()
                if invitation is None:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="The invitation code is invalid, expired, or already used.",
                    )

                user = cursor.execute(
                    """
                    INSERT INTO users (full_name, email, password_hash)
                    VALUES (%s, %s, %s)
                    RETURNING id, full_name, email
                    """,
                    (request.full_name, request.email, hashed_password),
                ).fetchone()
                cursor.execute(
                    """
                    INSERT INTO business_memberships (user_id, business_id, role)
                    VALUES (%s, %s, 'stock_manager')
                    """,
                    (user["id"], invitation["business_id"]),
                )
                cursor.execute(
                    """
                    UPDATE business_invitations
                    SET used_at = now()
                    WHERE id = %s
                    """,
                    (invitation["id"],),
                )
                business = cursor.execute(
                    "SELECT id, name FROM businesses WHERE id = %s",
                    (invitation["business_id"],),
                ).fetchone()
    except psycopg.errors.UniqueViolation as exc:
        if exc.diag.constraint_name != "users_email_lower_unique":
            raise
        raise _duplicate_email_error() from exc
    except psycopg.Error as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database is unavailable.",
        ) from exc
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc

    response_user = UserResponse(
        id=user["id"],
        full_name=user["full_name"],
        email=user["email"],
        business_id=business["id"],
        business_name=business["name"],
        role="stock_manager",
    )
    return _create_auth_response(response_user)


@router.post(
    "/login",
    response_model=AuthResponse,
)
def login(request: LoginRequest) -> AuthResponse:
    _ensure_jwt_configured()

    try:
        with get_connection() as connection:
            with connection.cursor(row_factory=dict_row) as cursor:
                result = cursor.execute(
                    """
                    SELECT u.id, u.full_name, u.email, u.password_hash,
                           b.id AS business_id, b.name AS business_name, m.role
                    FROM users AS u
                    JOIN business_memberships AS m ON m.user_id = u.id
                    JOIN businesses AS b ON b.id = m.business_id
                    WHERE lower(u.email) = %s
                    """,
                    (request.email,),
                ).fetchone()
    except (psycopg.Error, RuntimeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database is unavailable.",
        ) from exc

    if result is None or not verify_password(request.password, result["password_hash"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    response_user = UserResponse(
        id=result["id"],
        full_name=result["full_name"],
        email=result["email"],
        business_id=result["business_id"],
        business_name=result["business_name"],
        role=result["role"],
    )
    return _create_auth_response(response_user)


@router.get("/me", response_model=CurrentUserResponse)
def get_me(current_user: CurrentUser) -> CurrentUserResponse:
    return CurrentUserResponse.model_validate(current_user.model_dump())


@router.post(
    "/invitations",
    response_model=InvitationResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_invitation(owner: BusinessOwner) -> InvitationResponse:
    invitation_code = create_invitation_code()
    expires_at = datetime.now(timezone.utc) + timedelta(hours=24)

    try:
        with get_connection() as connection:
            connection.execute(
                """
                INSERT INTO business_invitations
                    (business_id, created_by_user_id, token_hash, expires_at)
                VALUES (%s, %s, %s, %s)
                """,
                (
                    owner.business_id,
                    owner.id,
                    hash_invitation_code(invitation_code),
                    expires_at,
                ),
            )
    except (psycopg.Error, RuntimeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database is unavailable.",
        ) from exc

    return InvitationResponse(
        invitation_code=invitation_code,
        expires_at=expires_at,
    )
