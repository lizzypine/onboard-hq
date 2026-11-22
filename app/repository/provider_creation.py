"""Creation receipts and checklist insertions inside the caller's transaction."""

from collections.abc import Sequence
from typing import Any

from psycopg import AsyncConnection

from app.models import Requirement, StoredProvider
from app.provider_models import (
    AdditionalRequirementInput,
    CreateProviderRequest,
    ProviderTypeTemplate,
)
from app.repository import RecordNotFound
from app.repository.catalog import CATALOG_QUERY, resolve_definitions
from app.rules.catalog import normalize_name
from app.rules.providers import require_same_creation
from db.queries import fetch_provider


async def existing_creation(
    conn: AsyncConnection[dict[str, Any]], request: CreateProviderRequest
) -> StoredProvider | None:
    row = await (
        await conn.execute(
            """SELECT p.id,p.creation_request_id,p.name,p.checklist_template_id,
        c.provider_type_id,p.proposed_start_date FROM providers p
        JOIN checklist_templates c ON c.id=p.checklist_template_id
        WHERE p.creation_request_id=%s""",
            (request.creation_request_id,),
        )
    ).fetchone()
    if row is None:
        return None
    catalog = await (
        await conn.execute(
            CATALOG_QUERY + " WHERE c.id=%s", (row["checklist_template_id"],)
        )
    ).fetchone()
    template = ProviderTypeTemplate.model_validate(catalog)
    additions = await (
        await conn.execute(
            """SELECT d.name,r.initial_status AS status,r.initial_scheduled_date AS scheduled_date,
        r.initial_deadline AS deadline FROM requirements r JOIN requirement_definitions d
        ON d.id=r.requirement_definition_id WHERE r.provider_id=%s AND r.checklist_template_id IS NULL""",
            (row["id"],),
        )
    ).fetchall()
    original = {key: value for key, value in row.items() if key != "id"}
    require_same_creation(
        CreateProviderRequest.model_validate(
            {
                **original,
                "template_fingerprint": template.template_fingerprint,
                "additional_requirements": additions,
            }
        ),
        request,
    )
    return await fetch_provider(conn, row["id"])


async def insert_provider(
    conn: AsyncConnection[dict[str, Any]],
    request: CreateProviderRequest,
    template: ProviderTypeTemplate,
) -> int:
    row = await (
        await conn.execute(
            """INSERT INTO providers(creation_request_id,name,checklist_template_id,proposed_start_date)
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
            """INSERT INTO requirements(provider_id,checklist_template_id,requirement_definition_id,status,deadline)
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


async def initialize_additions(
    conn: AsyncConnection[dict[str, Any]],
    provider_id: int,
    template: ProviderTypeTemplate,
    additions: Sequence[AdditionalRequirementInput],
) -> None:
    definitions = await resolve_definitions(conn, [a.name for a in additions])
    for addition in additions:
        await conn.execute(
            """INSERT INTO requirements(provider_id,requirement_definition_id,status,scheduled_date,deadline,
            initial_status,initial_scheduled_date,initial_deadline) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
            (
                provider_id,
                definitions[normalize_name(addition.name)],
                addition.status,
                addition.scheduled_date,
                addition.deadline,
                addition.status,
                addition.scheduled_date,
                addition.deadline,
            ),
        )
