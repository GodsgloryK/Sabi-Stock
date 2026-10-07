from uuid import UUID

import psycopg
from fastapi import APIRouter, HTTPException, Query, Response, status
from psycopg.rows import dict_row

from app.api.dependencies import CurrentUser
from app.db.connection import get_connection
from app.schemas.products import ProductResponse, ProductWrite

router = APIRouter()


def _database_unavailable(exc: Exception) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="Database is unavailable.",
    )


def _not_found() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Product not found.",
    )


@router.post(
    "",
    response_model=ProductResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_product(request: ProductWrite, current_user: CurrentUser) -> ProductResponse:
    try:
        with get_connection() as connection:
            with connection.cursor(row_factory=dict_row) as cursor:
                product = cursor.execute(
                    """
                    INSERT INTO products (
                        business_id, name, category, buying_price,
                        selling_price, stock_quantity
                    )
                    VALUES (%s, %s, %s, %s, %s, %s)
                    RETURNING id, business_id, name, category, buying_price,
                              selling_price, stock_quantity, created_at, updated_at
                    """,
                    (
                        current_user.business_id,
                        request.name,
                        request.category,
                        request.buying_price,
                        request.selling_price,
                        request.stock_quantity,
                    ),
                ).fetchone()
    except (psycopg.Error, RuntimeError) as exc:
        raise _database_unavailable(exc) from exc

    return ProductResponse.model_validate(product)


@router.get("", response_model=list[ProductResponse])
def list_products(
    current_user: CurrentUser,
    search: str | None = Query(default=None, max_length=160),
    category: str | None = Query(default=None, max_length=80),
) -> list[ProductResponse]:
    conditions = ["business_id = %s"]
    parameters: list[object] = [current_user.business_id]

    if search and search.strip():
        conditions.append("name ILIKE %s")
        parameters.append(f"%{search.strip()}%")
    if category and category.strip():
        conditions.append("category = %s")
        parameters.append(category.strip())

    try:
        with get_connection() as connection:
            with connection.cursor(row_factory=dict_row) as cursor:
                products = cursor.execute(
                    f"""
                    SELECT id, business_id, name, category, buying_price,
                           selling_price, stock_quantity, created_at, updated_at
                    FROM products
                    WHERE {" AND ".join(conditions)}
                    ORDER BY lower(name), id
                    """,
                    parameters,
                ).fetchall()
    except (psycopg.Error, RuntimeError) as exc:
        raise _database_unavailable(exc) from exc

    return [ProductResponse.model_validate(product) for product in products]


@router.get("/{product_id}", response_model=ProductResponse)
def get_product(product_id: UUID, current_user: CurrentUser) -> ProductResponse:
    try:
        with get_connection() as connection:
            with connection.cursor(row_factory=dict_row) as cursor:
                product = cursor.execute(
                    """
                    SELECT id, business_id, name, category, buying_price,
                           selling_price, stock_quantity, created_at, updated_at
                    FROM products
                    WHERE id = %s AND business_id = %s
                    """,
                    (product_id, current_user.business_id),
                ).fetchone()
    except (psycopg.Error, RuntimeError) as exc:
        raise _database_unavailable(exc) from exc

    if product is None:
        raise _not_found()
    return ProductResponse.model_validate(product)


@router.put("/{product_id}", response_model=ProductResponse)
def update_product(
    product_id: UUID,
    request: ProductWrite,
    current_user: CurrentUser,
) -> ProductResponse:
    try:
        with get_connection() as connection:
            with connection.cursor(row_factory=dict_row) as cursor:
                product = cursor.execute(
                    """
                    UPDATE products
                    SET name = %s,
                        category = %s,
                        buying_price = %s,
                        selling_price = %s,
                        stock_quantity = %s,
                        updated_at = now()
                    WHERE id = %s AND business_id = %s
                    RETURNING id, business_id, name, category, buying_price,
                              selling_price, stock_quantity, created_at, updated_at
                    """,
                    (
                        request.name,
                        request.category,
                        request.buying_price,
                        request.selling_price,
                        request.stock_quantity,
                        product_id,
                        current_user.business_id,
                    ),
                ).fetchone()
    except (psycopg.Error, RuntimeError) as exc:
        raise _database_unavailable(exc) from exc

    if product is None:
        raise _not_found()
    return ProductResponse.model_validate(product)


@router.delete("/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_product(product_id: UUID, current_user: CurrentUser) -> Response:
    try:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "DELETE FROM products WHERE id = %s AND business_id = %s",
                    (product_id, current_user.business_id),
                )
                deleted = cursor.rowcount
    except psycopg.errors.IntegrityError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This product has sales recorded and cannot be deleted.",
        ) from exc
    except (psycopg.Error, RuntimeError) as exc:
        raise _database_unavailable(exc) from exc

    if deleted == 0:
        raise _not_found()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
