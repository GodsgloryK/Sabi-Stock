import psycopg
from fastapi import APIRouter, HTTPException

from app.db.connection import get_connection

router = APIRouter()


@router.get("/health", tags=["health"])
def health_check() -> dict[str, str]:
    try:
        with get_connection() as connection:
            connection.execute("SELECT 1")
    except (psycopg.Error, RuntimeError) as exc:
        raise HTTPException(
            status_code=503,
            detail="Database is unavailable.",
        ) from exc

    return {"status": "ok", "database": "connected"}
