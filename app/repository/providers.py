"""Provider/template reads and atomic checklist initialization."""

from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid5

from psycopg import AsyncConnection

from app.database import DatabasePool
from app.models import ProviderSummary, Requirement, StoredProvider
from app.repository import RecordNotFound, connection

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


class ProviderRepository:
    def __init__(self, pool: DatabasePool) -> None:
        self.pool = pool

    async def list_providers(self) -> list[ProviderSummary]:
        async with connection(self.pool) as conn:
            rows = await (
                await conn.execute(
                    "SELECT p.id,p.name,t.name AS provider_type,p.proposed_start_date FROM providers p JOIN provider_types t ON p.provider_type_id=t.id ORDER BY p.name,p.id"
                )
            ).fetchall()
            return [ProviderSummary.model_validate(row) for row in rows]

    async def get_provider(self, provider_id: UUID) -> StoredProvider:
        async with connection(self.pool) as conn:
            return await fetch_provider(conn, provider_id)

    async def initialize_provider(
        self,
        provider: ProviderSummary,
        provider_type_id: UUID,
        initial_values: dict[str, Requirement],
    ) -> bool:
        async with connection(self.pool) as conn:
            created = await (
                await conn.execute(
                    "INSERT INTO providers(id,provider_type_id,name,proposed_start_date) VALUES (%s,%s,%s,%s) ON CONFLICT(id) DO NOTHING RETURNING id",
                    (
                        provider.id,
                        provider_type_id,
                        provider.name,
                        provider.proposed_start_date,
                    ),
                )
            ).fetchone()
            if created is None:
                return False
            templates = await (
                await conn.execute(
                    "SELECT id,name FROM requirement_templates WHERE provider_type_id=%s",
                    (provider_type_id,),
                )
            ).fetchall()
            if {t["name"] for t in templates} != set(initial_values):
                raise ValueError(
                    "Initial values must match the provider type's templates."
                )
            for template in templates:
                value = initial_values[template["name"]]
                key = uuid5(
                    NAMESPACE_URL,
                    f"onboard-hq:requirement:{provider.id}:{template['name']}",
                )
                await conn.execute(
                    "INSERT INTO requirements(id,provider_id,provider_type_id,source_template_id,name,status,deadline) VALUES (%s,%s,%s,%s,%s,%s,%s)",
                    (
                        key,
                        provider.id,
                        provider_type_id,
                        template["id"],
                        template["name"],
                        value.status,
                        value.deadline,
                    ),
                )
            return True
