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


def _duplicate_sku() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail="This product ID is already in use. Choose a different one.",
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
                cursor.execute(
                    """
                    INSERT INTO product_sku_registry (business_id, sku)
                    VALUES (%s, %s)
                    """,
                    (current_user.business_id, request.sku),
                )
                product = cursor.execute(
                    """
                    INSERT INTO products (
                        business_id, sku, name, category, buying_price,
                        selling_price, stock_quantity
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    RETURNING id, business_id, sku, name, category, buying_price,
                              selling_price, stock_quantity, created_at, updated_at
                    """,
                    (
                        current_user.business_id,
                        request.sku,
                        request.name,
                        request.category,
                        request.buying_price,
                        request.selling_price,
                        request.stock_quantity,
                    ),
                ).fetchone()
    except psycopg.errors.UniqueViolation as exc:
        raise _duplicate_sku() from exc
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
        conditions.append("(name ILIKE %s OR sku ILIKE %s)")
        pattern = f"%{search.strip()}%"
        parameters.append(pattern)
        parameters.append(pattern)
    if category and category.strip():
        conditions.append("category = %s")
        parameters.append(category.strip())

    try:
        with get_connection() as connection:
            with connection.cursor(row_factory=dict_row) as cursor:
                products = cursor.execute(
                    f"""
                    SELECT id, business_id, sku, name, category, buying_price,
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
                    SELECT id, business_id, sku, name, category, buying_price,
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
                existing = cursor.execute(
                    """
                    SELECT sku
                    FROM products
                    WHERE id = %s AND business_id = %s
                    FOR UPDATE
                    """,
                    (product_id, current_user.business_id),
                ).fetchone()
                if existing is None:
                    raise _not_found()

                if existing["sku"].strip().casefold() != request.sku.strip().casefold():
                    cursor.execute(
                        """
                        INSERT INTO product_sku_registry (business_id, sku)
                        VALUES (%s, %s)
                        """,
                        (current_user.business_id, request.sku),
                    )

                product = cursor.execute(
                    """
                    UPDATE products
                    SET sku = %s,
                        name = %s,
                        category = %s,
                        buying_price = %s,
                        selling_price = %s,
                        stock_quantity = %s,
                        updated_at = now()
                    WHERE id = %s AND business_id = %s
                    RETURNING id, business_id, sku, name, category, buying_price,
                              selling_price, stock_quantity, created_at, updated_at
                    """,
                    (
                        request.sku,
                        request.name,
                        request.category,
                        request.buying_price,
                        request.selling_price,
                        request.stock_quantity,
                        product_id,
                        current_user.business_id,
                    ),
                ).fetchone()
    except HTTPException:
        raise
    except psycopg.errors.UniqueViolation as exc:
        raise _duplicate_sku() from exc
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
