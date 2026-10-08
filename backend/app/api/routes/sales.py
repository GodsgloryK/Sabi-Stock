from datetime import date, timedelta
from decimal import Decimal
from uuid import UUID

import psycopg
from fastapi import APIRouter, HTTPException, Query, Response, status
from psycopg.rows import dict_row

from app.api.dependencies import CurrentUser
from app.db.connection import get_connection
from app.schemas.sales import SaleCreate, SaleResponse, SalesSummaryResponse

router = APIRouter()


def _database_unavailable(exc: Exception) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="Database is unavailable.",
    )


def _sale_not_found() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Sale not found.",
    )


@router.post(
    "",
    response_model=SaleResponse,
    status_code=status.HTTP_201_CREATED,
)
def record_sale(request: SaleCreate, current_user: CurrentUser) -> SaleResponse:
    try:
        with get_connection() as connection:
            with connection.cursor(row_factory=dict_row) as cursor:
                product = cursor.execute(
                    """
                    SELECT id, name, stock_quantity, buying_price, selling_price
                    FROM products
                    WHERE id = %s AND business_id = %s
                    FOR UPDATE
                    """,
                    (request.product_id, current_user.business_id),
                ).fetchone()

                if product is None:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail="Product not found in your business.",
                    )

                if product["stock_quantity"] < request.quantity:
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail=(
                            f"Insufficient stock. Only {product['stock_quantity']} "
                            "units are available."
                        ),
                    )

                selling_price = Decimal(product["selling_price"])
                buying_price = Decimal(product["buying_price"])
                quantity = request.quantity
                total_amount = selling_price * quantity
                profit = (selling_price - buying_price) * quantity

                cursor.execute(
                    """
                    UPDATE products
                    SET stock_quantity = stock_quantity - %s,
                        updated_at = now()
                    WHERE id = %s AND business_id = %s
                    """,
                    (quantity, request.product_id, current_user.business_id),
                )
                sale = cursor.execute(
                    """
                    INSERT INTO sales (
                        business_id, product_id, quantity, selling_price,
                        buying_price, profit, total_amount
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    RETURNING id, business_id, product_id, quantity,
                              selling_price, buying_price, profit, total_amount,
                              created_at
                    """,
                    (
                        current_user.business_id,
                        product["id"],
                        quantity,
                        selling_price,
                        buying_price,
                        profit,
                        total_amount,
                    ),
                ).fetchone()
                sale["product_name"] = product["name"]
    except HTTPException:
        raise
    except (psycopg.Error, RuntimeError) as exc:
        raise _database_unavailable(exc) from exc

    return SaleResponse.model_validate(sale)


def _build_sales_filters(
    business_id: UUID,
    date_from: date | None,
    date_to: date | None,
    product_id: UUID | None,
) -> tuple[str, list]:
    conditions = ["s.business_id = %s"]
    parameters: list = [business_id]
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
    return " AND ".join(conditions), parameters


@router.get("", response_model=list[SaleResponse])
def list_sales(
    current_user: CurrentUser,
    response: Response,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    date_from: date | None = None,
    date_to: date | None = None,
    product_id: UUID | None = None,
) -> list[SaleResponse]:
    where_clause, parameters = _build_sales_filters(
        current_user.business_id, date_from, date_to, product_id
    )
    try:
        with get_connection() as connection:
            with connection.cursor(row_factory=dict_row) as cursor:
                total_row = cursor.execute(
                    f"""
                    SELECT count(*)::bigint AS total
                    FROM sales AS s
                    WHERE {where_clause}
                    """,
                    tuple(parameters),
                ).fetchone()
                sales = cursor.execute(
                    f"""
                    SELECT s.id, s.business_id, s.product_id, p.name AS product_name,
                           s.quantity, s.selling_price, s.buying_price, s.profit,
                           s.total_amount, s.created_at
                    FROM sales AS s
                    JOIN products AS p ON p.id = s.product_id
                    WHERE {where_clause}
                    ORDER BY s.created_at DESC, s.id DESC
                    LIMIT %s OFFSET %s
                    """,
                    (*parameters, limit, offset),
                ).fetchall()
    except (psycopg.Error, RuntimeError) as exc:
        raise _database_unavailable(exc) from exc

    response.headers["X-Total-Count"] = str(total_row["total"])
    return [SaleResponse.model_validate(sale) for sale in sales]


@router.get("/summary", response_model=SalesSummaryResponse)
def get_sales_summary(
    current_user: CurrentUser,
    date_from: date | None = None,
    date_to: date | None = None,
    product_id: UUID | None = None,
) -> SalesSummaryResponse:
    where_clause, parameters = _build_sales_filters(
        current_user.business_id, date_from, date_to, product_id
    )
    try:
        with get_connection() as connection:
            with connection.cursor(row_factory=dict_row) as cursor:
                summary = cursor.execute(
                    f"""
                    SELECT
                        COALESCE(sum(s.total_amount), 0) AS total_amount,
                        COALESCE(sum(s.profit), 0) AS total_profit,
                        COALESCE(sum(s.quantity), 0)::bigint AS total_units,
                        count(*)::integer AS sale_count
                    FROM sales AS s
                    WHERE {where_clause}
                    """,
                    tuple(parameters),
                ).fetchone()
    except (psycopg.Error, RuntimeError) as exc:
        raise _database_unavailable(exc) from exc

    return SalesSummaryResponse(**summary)


@router.get("/{sale_id}", response_model=SaleResponse)
def get_sale(sale_id: UUID, current_user: CurrentUser) -> SaleResponse:
    try:
        with get_connection() as connection:
            with connection.cursor(row_factory=dict_row) as cursor:
                sale = cursor.execute(
                    """
                    SELECT s.id, s.business_id, s.product_id, p.name AS product_name,
                           s.quantity, s.selling_price, s.buying_price, s.profit,
                           s.total_amount, s.created_at
                    FROM sales AS s
                    JOIN products AS p ON p.id = s.product_id
                    WHERE s.id = %s AND s.business_id = %s
                    """,
                    (sale_id, current_user.business_id),
                ).fetchone()
    except (psycopg.Error, RuntimeError) as exc:
        raise _database_unavailable(exc) from exc

    if sale is None:
        raise _sale_not_found()
    return SaleResponse.model_validate(sale)


@router.delete("/{sale_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_sale(sale_id: UUID, current_user: CurrentUser) -> Response:
    try:
        with get_connection() as connection:
            with connection.cursor(row_factory=dict_row) as cursor:
                sale = cursor.execute(
                    """
                    SELECT id, product_id, quantity
                    FROM sales
                    WHERE id = %s AND business_id = %s
                    FOR UPDATE
                    """,
                    (sale_id, current_user.business_id),
                ).fetchone()
                if sale is None:
                    raise _sale_not_found()

                product = cursor.execute(
                    """
                    UPDATE products
                    SET stock_quantity = stock_quantity + %s,
                        updated_at = now()
                    WHERE id = %s AND business_id = %s
                    RETURNING id
                    """,
                    (
                        sale["quantity"],
                        sale["product_id"],
                        current_user.business_id,
                    ),
                ).fetchone()
                if product is None:
                    raise _sale_not_found()

                cursor.execute(
                    "DELETE FROM sales WHERE id = %s AND business_id = %s",
                    (sale_id, current_user.business_id),
                )
    except HTTPException:
        raise
    except (psycopg.Error, RuntimeError) as exc:
        raise _database_unavailable(exc) from exc

    return Response(status_code=status.HTTP_204_NO_CONTENT)
