import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from uuid import UUID

import jwt
from pwdlib import PasswordHash

from app.core.config import settings

password_hash = PasswordHash.recommended()


def hash_password(password: str) -> str:
    return password_hash.hash(password)


def verify_password(password: str, hashed_password: str) -> bool:
    return password_hash.verify(password, hashed_password)


def create_access_token(user_id: UUID, business_id: UUID, role: str) -> str:
    secret_key = settings.jwt_secret_key
    if not secret_key or len(secret_key) < 32:
        raise RuntimeError("JWT_SECRET_KEY must be configured with at least 32 characters.")

    expires_at = datetime.now(timezone.utc) + timedelta(
        minutes=settings.jwt_expire_minutes
    )
    return jwt.encode(
        {
            "sub": str(user_id),
            "business_id": str(business_id),
            "role": role,
            "exp": expires_at,
        },
        secret_key,
        algorithm="HS256",
    )


def decode_access_token(token: str) -> dict[str, object]:
    secret_key = settings.jwt_secret_key
    if not secret_key or len(secret_key) < 32:
        raise RuntimeError("JWT_SECRET_KEY must be configured with at least 32 characters.")

    return jwt.decode(token, secret_key, algorithms=["HS256"])


def create_invitation_code() -> str:
    return secrets.token_urlsafe(32)


def hash_invitation_code(invitation_code: str) -> str:
    return hashlib.sha256(invitation_code.encode("utf-8")).hexdigest()
