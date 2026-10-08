import csv
import io
from datetime import date, timedelta
from uuid import UUID

import psycopg
from fastapi import APIRouter, HTTPException, status
from fastapi.responses import StreamingResponse
from psycopg.rows import dict_row

from app.api.dependencies import CurrentUser
from app.db.connection import get_connection

router = APIRouter()


def _database_unavailable(exc: Exception) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="Database is unavailable.",
    )


def _streaming_csv(filename: str, header: list[str], rows: list[list]) -> StreamingResponse:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(header)
    writer.writerows(rows)
    buffer.seek(0)
    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
        },
    )


@router.get("/export/sales.csv")
def export_sales_csv(
    current_user: CurrentUser,
    date_from: date | None = None,
    date_to: date | None = None,
    product_id: UUID | None = None,
) -> StreamingResponse:
    conditions = ["s.business_id = %s"]
    parameters: list = [current_user.business_id]
    if date_from is not None:
        conditions.append("s.created_at >= %s::timestamptz")
        parameters.append(date_from.isoformat())
    if date_to is not None:
        day_after = date_to + timedelta(days=1)
        conditions.append("s.created_at < %s::timestamptz")
        parameters.append(day_after.isoformat())
    if product_id is not None:
        conditions.append("s.product_id = %s")
        parameters.append(product_id)
    where_clause = " AND ".join(conditions)

    try:
        with get_connection() as connection:
            with connection.cursor(row_factory=dict_row) as cursor:
                rows = cursor.execute(
                    f"""
                    SELECT p.name AS product_name, s.quantity,
                           s.selling_price, s.buying_price,
                           s.total_amount, s.profit, s.created_at
                    FROM sales AS s
                    JOIN products AS p ON p.id = s.product_id
                    WHERE {where_clause}
                    ORDER BY s.created_at DESC, s.id DESC
                    LIMIT 10000
                    """,
                    tuple(parameters),
                ).fetchall()
    except (psycopg.Error, RuntimeError) as exc:
        raise _database_unavailable(exc) from exc

    table_rows = [
        [
            row["product_name"],
            row["quantity"],
            str(row["selling_price"]),
            str(row["buying_price"]),
            str(row["total_amount"]),
            str(row["profit"]),
            row["created_at"].isoformat(),
        ]
        for row in rows
    ]
    return _streaming_csv(
        "smart-stock-sales.csv",
        ["Product", "Quantity", "Selling price", "Buying price", "Total amount", "Profit", "Date"],
        table_rows,
    )


@router.get("/export/products.csv")
def export_products_csv(current_user: CurrentUser) -> StreamingResponse:
    try:
        with get_connection() as connection:
            with connection.cursor(row_factory=dict_row) as cursor:
                rows = cursor.execute(
                    """
                    SELECT name, category, buying_price, selling_price, stock_quantity
                    FROM products
                    WHERE business_id = %s
                    ORDER BY lower(name), id
                    """,
                    (current_user.business_id,),
                ).fetchall()
    except (psycopg.Error, RuntimeError) as exc:
        raise _database_unavailable(exc) from exc

    table_rows = [
        [
            row["name"],
            row["category"],
            str(row["buying_price"]),
            str(row["selling_price"]),
            row["stock_quantity"],
        ]
        for row in rows
    ]
    return _streaming_csv(
        "smart-stock-products.csv",
        ["Product", "Category", "Buying price", "Selling price", "Stock quantity"],
        table_rows,
    )
