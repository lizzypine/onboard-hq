"""Provider reads and retry-safe whole-checklist initialization."""

from typing import Any, Literal

from psycopg import AsyncConnection

from app.database import DatabasePool
from app.models import ProviderSummary, Requirement, StoredProvider
from app.provider_models import CreateProviderRequest, ProviderTypeTemplate
from app.repository import RecordNotFound, connection, lock_retry
from app.repository.catalog import CATALOG_QUERY
from app.rules.providers import require_same_creation, require_templates
from db.queries import fetch_provider


async def existing_creation(
    conn: AsyncConnection[dict[str, Any]], request: CreateProviderRequest
) -> StoredProvider | None:
    row = await (
        await conn.execute(
            """SELECT p.id,p.creation_request_id,p.name,
        c.provider_type_id,p.proposed_start_date FROM providers p
        JOIN checklist_templates c ON c.id=p.checklist_template_id
        WHERE p.creation_request_id=%s""",
            (request.creation_request_id,),
        )
    ).fetchone()
    if row is None:
        return None
    require_same_creation(
        CreateProviderRequest.model_validate(
            {key: value for key, value in row.items() if key != "id"}
        ),
        request,
    )
    return await fetch_provider(conn, row["id"])


async def latest_template(
    conn: AsyncConnection[dict[str, Any]], type_id: int
) -> ProviderTypeTemplate:
    kind = await (
        await conn.execute(
            "SELECT id FROM provider_types WHERE id=%s FOR UPDATE", (type_id,)
        )
    ).fetchone()
    if kind is None:
        raise RecordNotFound("Provider type not found.")
    header = await (
        await conn.execute(
            "SELECT id FROM checklist_templates WHERE provider_type_id=%s ORDER BY template_version DESC LIMIT 1 FOR UPDATE",
            (type_id,),
        )
    ).fetchone()
    if header is None:
        require_templates([])
        raise RecordNotFound("Checklist version not found.")
    # Read membership in a new statement after the lock: a query that waited on
    # the header can otherwise return a subquery evaluated before the wait.
    row = await (
        await conn.execute(CATALOG_QUERY + " WHERE c.id=%s", (header["id"],))
    ).fetchone()
    result = ProviderTypeTemplate.model_validate(row)
    require_templates(result.requirements)
    return result


async def insert_provider(
    conn: AsyncConnection[dict[str, Any]],
    request: CreateProviderRequest,
    template: ProviderTypeTemplate,
) -> int:
    row = await (
        await conn.execute(
            """INSERT INTO providers
        (creation_request_id,name,checklist_template_id,proposed_start_date)
        VALUES (%s,%s,%s,%s) RETURNING id""",
            (
                request.creation_request_id,
                request.name,
                template.checklist_template_id,
                request.proposed_start_date,
            ),
        )
    ).fetchone()
    if row is None:
        raise RecordNotFound("Provider could not be created.")
    return int(row["id"])


async def initialize_checklist(
    conn: AsyncConnection[dict[str, Any]],
    provider_id: int,
    template: ProviderTypeTemplate,
    values: dict[str, Requirement],
) -> None:
    for name in template.requirements:
        value = values[name]
        await conn.execute(
            """INSERT INTO requirements
            (provider_id,checklist_template_id,requirement_definition_id,status,deadline)
            SELECT %s,%s,d.id,%s,%s FROM template_requirements m
            JOIN requirement_definitions d ON d.id=m.requirement_definition_id
            WHERE m.checklist_template_id=%s AND d.name=%s""",
            (
                provider_id,
                template.checklist_template_id,
                value.status,
                value.deadline,
                template.checklist_template_id,
                name,
            ),
        )


class ProviderRepository:
    def __init__(self, pool: DatabasePool) -> None:
        self.pool = pool

    async def list_providers(
        self, state: Literal["active", "archived", "all"] = "active"
    ) -> list[ProviderSummary]:
        async with connection(self.pool) as conn:
            rows = await (
                await conn.execute(
                    """SELECT p.*,t.name AS provider_type,c.template_version
                FROM providers p JOIN checklist_templates c ON c.id=p.checklist_template_id
                JOIN provider_types t ON t.id=c.provider_type_id
                WHERE %s='all' OR (%s='active' AND p.archived_at IS NULL)
                   OR (%s='archived' AND p.archived_at IS NOT NULL) ORDER BY p.name,p.id""",
                    (state, state, state),
                )
            ).fetchall()
            return [ProviderSummary.model_validate(row) for row in rows]

    async def get_provider(self, provider_id: int) -> StoredProvider:
        async with connection(self.pool) as conn:
            return await fetch_provider(conn, provider_id)

    async def list_provider_types(self) -> list[ProviderTypeTemplate]:
        async with connection(self.pool) as conn:
            rows = await (
                await conn.execute(
                    CATALOG_QUERY
                    + """ WHERE c.template_version=(
                SELECT max(v.template_version) FROM checklist_templates v WHERE v.provider_type_id=t.id)
                AND EXISTS (SELECT 1 FROM template_requirements m WHERE m.checklist_template_id=c.id)
                ORDER BY t.name,t.id"""
                )
            ).fetchall()
            return [ProviderTypeTemplate.model_validate(row) for row in rows]

    async def create_from_template(
        self, request: CreateProviderRequest, *, initial_status: str
    ) -> StoredProvider:
        return await self._initialize(
            request, initial_status=initial_status, initial_values=None
        )

    async def initialize_provider(
        self, request: CreateProviderRequest, initial_values: dict[str, Requirement]
    ) -> StoredProvider:
        return await self._initialize(
            request, initial_status="Outstanding", initial_values=initial_values
        )

    async def _initialize(
        self,
        request: CreateProviderRequest,
        *,
        initial_status: str,
        initial_values: dict[str, Requirement] | None,
    ) -> StoredProvider:
        async with connection(self.pool) as conn:
            await lock_retry(conn, request.creation_request_id)
            existing = await existing_creation(conn, request)
            if existing is not None:
                return existing
            template = await latest_template(conn, request.provider_type_id)
            values = (
                initial_values
                if initial_values is not None
                else {
                    name: Requirement(name=name, status=initial_status)
                    for name in template.requirements
                }
            )
            if set(values) != set(template.requirements):
                raise ValueError(
                    "Initial values must match the provider type's templates."
                )
            provider_id = await insert_provider(conn, request, template)
            await initialize_checklist(conn, provider_id, template, values)
            return await fetch_provider(conn, provider_id)
