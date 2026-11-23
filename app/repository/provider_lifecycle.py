"""Serialized provider lifecycle changes preserve all checklist and audit rows."""

from app.database import DatabasePool
from app.models import StoredProvider
from app.repository import connection, lock_provider
from db.queries import fetch_provider


class ProviderLifecycleRepository:
    def __init__(self, pool: DatabasePool) -> None:
        self.pool = pool

    async def set_archived(self, provider_id: int, archived: bool) -> StoredProvider:
        async with connection(self.pool) as conn:
            await lock_provider(conn, provider_id)
            await conn.execute(
                """UPDATE providers SET archived_at=
                CASE WHEN %s THEN COALESCE(archived_at,now()) ELSE NULL END
                WHERE id=%s""",
                (archived, provider_id),
            )
            return await fetch_provider(conn, provider_id)
