"""Short, guarded PostgreSQL transactions; no model or HTTP dependencies."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from psycopg import AsyncConnection, Error
from psycopg_pool import PoolClosed, PoolTimeout
from pydantic import ValidationError

from app.database import DatabasePool, DatabaseUnavailable


class RecordNotFound(ValueError):
    """The requested saved record does not exist."""


@asynccontextmanager
async def connection(
    pool: DatabasePool,
) -> AsyncIterator[AsyncConnection[dict[str, Any]]]:
    try:
        async with pool.connection() as conn:
            yield conn
    except (Error, PoolClosed, PoolTimeout, ValidationError):
        raise DatabaseUnavailable(
            "Database is unavailable. Check configuration and migrations."
        ) from None
