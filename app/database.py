"""Database configuration and connection lifecycle, without HTTP or model calls."""

import os
from typing import Any
from urllib.parse import urlsplit

from psycopg import AsyncConnection, ProgrammingError
from psycopg.conninfo import conninfo_to_dict
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

DatabasePool = AsyncConnectionPool[AsyncConnection[dict[str, Any]]]


class DatabaseConfigurationError(ValueError):
    """Database settings are absent or invalid."""


class DatabaseUnavailable(RuntimeError):
    """A database operation could not complete safely."""


def database_url() -> str:
    """Validate settings without including connection details in errors."""
    value = os.environ.get("DATABASE_URL", "").strip()
    try:
        parsed = urlsplit(value)
        if parsed.scheme not in {"postgres", "postgresql"} or not parsed.hostname:
            raise ValueError
        options = conninfo_to_dict(value)
        if not options.get("dbname"):
            raise ValueError
    except (ValueError, ProgrammingError):
        # Driver parse errors may contain the original URI; discard them.
        raise DatabaseConfigurationError(
            "Database configuration is missing or invalid."
        ) from None
    return value


def create_pool(url: str) -> DatabasePool:
    """Create a bounded pool; opening it does not eagerly connect."""
    return AsyncConnectionPool(
        conninfo=url,
        kwargs={"row_factory": dict_row, "connect_timeout": 10},
        min_size=0,
        max_size=4,
        timeout=10,
        open=False,
    )
