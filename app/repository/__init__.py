"""Short, guarded PostgreSQL transactions; no model or HTTP dependencies."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any
from uuid import UUID

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


async def lock_retry(conn: AsyncConnection[dict[str, Any]], key: UUID) -> None:
    """Serialize a retry identity before acquiring any resource row locks."""
    await conn.execute(
        "SELECT pg_advisory_xact_lock(%s)",
        (int.from_bytes(key.bytes[:8], "big", signed=True),),
    )


async def lock_provider(
    conn: AsyncConnection[dict[str, Any]], provider_id: int
) -> None:
    """All provider-owned mutations take the provider lock before child locks."""
    row = await (
        await conn.execute(
            "SELECT id FROM providers WHERE id=%s FOR UPDATE", (provider_id,)
        )
    ).fetchone()
    if row is None:
        raise RecordNotFound("Provider not found.")
