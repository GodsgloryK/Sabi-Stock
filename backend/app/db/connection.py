from collections.abc import Iterator
from contextlib import contextmanager

import psycopg
from psycopg import Connection

from app.core.config import settings


@contextmanager
def get_connection() -> Iterator[Connection]:
    if not settings.database_url:
        raise RuntimeError("DATABASE_URL is not configured.")

    with psycopg.connect(settings.database_url) as connection:
        yield connection
