import psycopg
from fastapi import APIRouter, HTTPException, status
from psycopg.rows import dict_row

from app.api.dependencies import CurrentUser
from app.db.connection import get_connection
from app.schemas.dashboard import (
    BestSellingProduct,
    DashboardResponse,
    LowStockProduct,
)

router = APIRouter()


@router.get("", response_model=DashboardResponse)
def get_dashboard(current_user: CurrentUser) -> DashboardResponse:
    try:
        with get_connection() as connection:
            with connection.cursor(row_factory=dict_row) as cursor:
                summary = cursor.execute(
                    """
                    SELECT
                        (
                            SELECT count(*)::integer
                            FROM products
                            WHERE business_id = %s
                        ) AS total_products,
                        COALESCE(
                            (
                                SELECT sum(stock_quantity)
                                FROM products
                                WHERE business_id = %s
                            ),
                            0
                        )::bigint AS total_stock_quantity,
                        COALESCE(
                            (
                                SELECT sum(total_amount)
                                FROM sales
                                WHERE business_id = %s
                                  AND created_at >= CURRENT_DATE::timestamptz
                                  AND created_at < (CURRENT_DATE + 1)::timestamptz
                            ),
                            0
                        ) AS today_total_sales,
                        COALESCE(
                            (
                                SELECT sum(profit)
                                FROM sales
                                WHERE business_id = %s
                                  AND created_at >= CURRENT_DATE::timestamptz
                                  AND created_at < (CURRENT_DATE + 1)::timestamptz
                            ),
                            0
                        ) AS today_total_profit
                    """,
                    (
                        current_user.business_id,
                        current_user.business_id,
                        current_user.business_id,
                        current_user.business_id,
                    ),
                ).fetchone()
                low_stock_rows = cursor.execute(
                    """
                    SELECT id, name, category, stock_quantity
                    FROM products
                    WHERE business_id = %s AND stock_quantity < 5
                    ORDER BY stock_quantity, lower(name), id
                    """,
                    (current_user.business_id,),
                ).fetchall()
                top_selling_rows = cursor.execute(
                    """
                    SELECT p.id AS product_id, p.name AS product_name,
                           sum(s.quantity)::bigint AS quantity_sold
                    FROM sales AS s
                    JOIN products AS p
                      ON p.id = s.product_id
                     AND p.business_id = s.business_id
                    WHERE s.business_id = %s
                    GROUP BY p.id, p.name
                    ORDER BY quantity_sold DESC, lower(p.name), p.id
                    LIMIT 5
                    """,
                    (current_user.business_id,),
                ).fetchall()
    except (psycopg.Error, RuntimeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Dashboard data is temporarily unavailable.",
        ) from exc

    return DashboardResponse(
        **summary,
        low_stock_products=[
            LowStockProduct.model_validate(product) for product in low_stock_rows
        ],
        top_selling_products=[
            BestSellingProduct.model_validate(product) for product in top_selling_rows
        ],
    )
