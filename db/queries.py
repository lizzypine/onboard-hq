"""Read one provider and its own checklist using a parameterized query."""

from typing import Any

from psycopg import AsyncConnection

from app.models import StoredProvider
from app.repository import RecordNotFound

PROVIDER_QUERY = """
SELECT p.*, t.name AS provider_type, c.template_version,
 COALESCE((SELECT jsonb_agg(to_jsonb(r) || jsonb_build_object('name',d.name) ORDER BY d.name,r.id)
 FROM requirements r JOIN requirement_definitions d ON d.id=r.requirement_definition_id
 WHERE r.provider_id=p.id), '[]') AS requirements
FROM providers p JOIN checklist_templates c ON c.id=p.checklist_template_id
JOIN provider_types t ON t.id=c.provider_type_id WHERE p.id=%s
"""


async def fetch_provider(
    conn: AsyncConnection[dict[str, Any]], provider_id: int
) -> StoredProvider:
    row = await (await conn.execute(PROVIDER_QUERY, (provider_id,))).fetchone()
    if row is None:
        raise RecordNotFound("Provider not found.")
    return StoredProvider.model_validate(row)
