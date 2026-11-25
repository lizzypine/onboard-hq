"""Shared request-scoped database pool dependency."""

from fastapi import HTTPException, Request

from app.database import DatabasePool


def get_pool(request: Request) -> DatabasePool:
    pool: DatabasePool | None = getattr(request.app.state, "pool", None)
    if pool is None:
        raise HTTPException(503, "Database is not configured.")
    return pool
