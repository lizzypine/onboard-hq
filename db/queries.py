"""Read one provider and its own checklist using a parameterized query."""

from typing import Any
from uuid import UUID

from psycopg import AsyncConnection

from app.models import StoredProvider
from app.repository import RecordNotFound

PROVIDER_QUERY = """
SELECT p.id, p.name, t.name AS provider_type, p.proposed_start_date,
       COALESCE(jsonb_agg(to_jsonb(r) - 'provider_type_id' ORDER BY r.name)
                FILTER (WHERE r.id IS NOT NULL), '[]') AS requirements
FROM providers p JOIN provider_types t ON t.id=p.provider_type_id
LEFT JOIN requirements r ON r.provider_id=p.id
WHERE p.id=%s GROUP BY p.id, t.name
"""


async def fetch_provider(
    conn: AsyncConnection[dict[str, Any]], provider_id: UUID
) -> StoredProvider:
    row = await (await conn.execute(PROVIDER_QUERY, (provider_id,))).fetchone()
    if row is None:
        raise RecordNotFound("Provider not found.")
    return StoredProvider.model_validate(row)
