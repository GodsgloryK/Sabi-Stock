import psycopg
from fastapi import APIRouter, HTTPException, status
from psycopg.rows import dict_row

from app.api.dependencies import BusinessOwner, CurrentUser
from app.db.connection import get_connection
from app.schemas.business import BusinessSettingsResponse, BusinessSettingsUpdate

router = APIRouter()


def _database_unavailable() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="Database is unavailable.",
    )


def _fetch_settings(business_id) -> BusinessSettingsResponse:
    try:
        with get_connection() as connection:
            with connection.cursor(row_factory=dict_row) as cursor:
                row = cursor.execute(
                    """
                    SELECT id, name, low_stock_threshold, timezone
                    FROM businesses
                    WHERE id = %s
                    """,
                    (business_id,),
                ).fetchone()
    except (psycopg.Error, RuntimeError) as exc:
        raise _database_unavailable() from exc

    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Business not found.",
        )
    return BusinessSettingsResponse(
        business_id=row["id"],
        business_name=row["name"],
        low_stock_threshold=row["low_stock_threshold"],
        timezone=row["timezone"],
    )


@router.get("/settings", response_model=BusinessSettingsResponse)
def get_business_settings(current_user: CurrentUser) -> BusinessSettingsResponse:
    return _fetch_settings(current_user.business_id)


@router.put("/settings", response_model=BusinessSettingsResponse)
def update_business_settings(
    update: BusinessSettingsUpdate,
    owner: BusinessOwner,
) -> BusinessSettingsResponse:
    try:
        with get_connection() as connection:
            with connection.cursor(row_factory=dict_row) as cursor:
                row = cursor.execute(
                    """
                    UPDATE businesses
                    SET low_stock_threshold = %s, timezone = %s
                    WHERE id = %s
                    RETURNING id, name, low_stock_threshold, timezone
                    """,
                    (update.low_stock_threshold, update.timezone, owner.business_id),
                ).fetchone()
    except (psycopg.Error, RuntimeError) as exc:
        raise _database_unavailable() from exc

    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Business not found.",
        )
    return BusinessSettingsResponse(
        business_id=row["id"],
        business_name=row["name"],
        low_stock_threshold=row["low_stock_threshold"],
        timezone=row["timezone"],
    )
