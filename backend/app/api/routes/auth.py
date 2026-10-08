from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
from uuid import UUID

import jwt
import psycopg
from fastapi import APIRouter, HTTPException, Request, status
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
    InvitationStatusResponse,
    LoginRequest,
    ManagerRegistration,
    OwnerRegistration,
    TeamMemberResponse,
    UserResponse,
)

router = APIRouter()

LOGIN_RATE_LIMIT = 5
LOGIN_RATE_WINDOW_SECONDS = 900
_login_attempts: dict[str, deque] = defaultdict(deque)


def _client_key(request: Request, email: str) -> str:
    client_host = request.client.host if request.client else "unknown"
    return f"{client_host}:{email.lower()}"


def _is_login_rate_limited(key: str) -> bool:
    now = datetime.now(timezone.utc)
    window_start = now - timedelta(seconds=LOGIN_RATE_WINDOW_SECONDS)
    attempts = _login_attempts[key]
    while attempts and attempts[0] < window_start:
        attempts.popleft()
    return len(attempts) >= LOGIN_RATE_LIMIT


def _record_login_failure(key: str) -> None:
    _login_attempts[key].append(datetime.now(timezone.utc))


def _clear_login_failures(key: str) -> None:
    _login_attempts.pop(key, None)


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
def login(request: LoginRequest, http_request: Request) -> AuthResponse:
    _ensure_jwt_configured()
    rate_key = _client_key(http_request, request.email)

    if _is_login_rate_limited(rate_key):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many login attempts. Please wait a few minutes and try again.",
        )

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
        _record_login_failure(rate_key)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    _clear_login_failures(rate_key)
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


@router.get("/members", response_model=list[TeamMemberResponse])
def list_members(owner: BusinessOwner) -> list[TeamMemberResponse]:
    try:
        with get_connection() as connection:
            with connection.cursor(row_factory=dict_row) as cursor:
                members = cursor.execute(
                    """
                    SELECT u.id, u.full_name, u.email, m.role, m.created_at
                    FROM business_memberships AS m
                    JOIN users AS u ON u.id = m.user_id
                    WHERE m.business_id = %s
                    ORDER BY
                        CASE m.role WHEN 'owner' THEN 0 ELSE 1 END,
                        lower(u.full_name),
                        u.id
                    """,
                    (owner.business_id,),
                ).fetchall()
    except (psycopg.Error, RuntimeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database is unavailable.",
        ) from exc

    return [
        TeamMemberResponse(
            id=member["id"],
            full_name=member["full_name"],
            email=member["email"],
            role=member["role"],
            joined_at=member["created_at"],
        )
        for member in members
    ]


@router.delete("/members/{member_user_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_member(member_user_id: UUID, owner: BusinessOwner) -> None:
    if member_user_id == owner.id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="You cannot remove your own owner account.",
        )

    try:
        with get_connection() as connection:
            with connection.cursor(row_factory=dict_row) as cursor:
                membership = cursor.execute(
                    """
                    SELECT user_id, role
                    FROM business_memberships
                    WHERE user_id = %s AND business_id = %s
                    FOR UPDATE
                    """,
                    (member_user_id, owner.business_id),
                ).fetchone()
                if membership is None:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail="Team member not found.",
                    )
                if membership["role"] == "owner":
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail="Owners cannot be removed. Transfer ownership first.",
                    )
                cursor.execute(
                    """
                    DELETE FROM business_memberships
                    WHERE user_id = %s AND business_id = %s
                    """,
                    (member_user_id, owner.business_id),
                )
    except HTTPException:
        raise
    except (psycopg.Error, RuntimeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database is unavailable.",
        ) from exc


@router.get("/invitations/list", response_model=list[InvitationStatusResponse])
def list_invitations(owner: BusinessOwner) -> list[InvitationStatusResponse]:
    try:
        with get_connection() as connection:
            with connection.cursor(row_factory=dict_row) as cursor:
                rows = cursor.execute(
                    """
                    SELECT id, expires_at, used_at, created_at
                    FROM business_invitations
                    WHERE business_id = %s
                    ORDER BY created_at DESC
                    LIMIT 50
                    """,
                    (owner.business_id,),
                ).fetchall()
    except (psycopg.Error, RuntimeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database is unavailable.",
        ) from exc

    now = datetime.now(timezone.utc)
    invitations = []
    for row in rows:
        if row["used_at"] is not None:
            invitation_status = "used"
        elif row["expires_at"] <= now:
            invitation_status = "expired"
        else:
            invitation_status = "pending"
        invitations.append(
            InvitationStatusResponse(
                id=row["id"],
                status=invitation_status,
                expires_at=row["expires_at"],
                used_at=row["used_at"],
                created_at=row["created_at"],
            )
        )
    return invitations


@router.delete("/invitations/{invitation_id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_invitation(invitation_id: UUID, owner: BusinessOwner) -> None:
    try:
        with get_connection() as connection:
            with connection.cursor(row_factory=dict_row) as cursor:
                invitation = cursor.execute(
                    """
                    SELECT id, used_at
                    FROM business_invitations
                    WHERE id = %s AND business_id = %s
                    FOR UPDATE
                    """,
                    (invitation_id, owner.business_id),
                ).fetchone()
                if invitation is None:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail="Invitation not found.",
                    )
                if invitation["used_at"] is not None:
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail="This invitation has already been used.",
                    )
                cursor.execute(
                    """
                    UPDATE business_invitations
                    SET used_at = now()
                    WHERE id = %s
                    """,
                    (invitation_id,),
                )
    except HTTPException:
        raise
    except (psycopg.Error, RuntimeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database is unavailable.",
        ) from exc
