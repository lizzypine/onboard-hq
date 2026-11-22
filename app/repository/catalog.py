"""Configure immutable whole-checklist versions; no catalog administration routes."""

from collections.abc import Sequence
from typing import Any

from psycopg import AsyncConnection

from app.database import DatabasePool
from app.provider_models import ProviderTypeTemplate
from app.repository import connection
from app.rules.catalog import normalize_name
from app.rules.providers import ProviderCreationConflict, require_templates

CATALOG_QUERY = """
SELECT t.id,t.name,c.id AS checklist_template_id,c.template_version,
 ARRAY(SELECT d.name FROM template_requirements m JOIN requirement_definitions d
 ON d.id=m.requirement_definition_id WHERE m.checklist_template_id=c.id ORDER BY d.name) AS requirements
FROM provider_types t JOIN checklist_templates c ON c.provider_type_id=t.id
"""


def normalized_names(names: Sequence[str]) -> set[str]:
    result = {name.strip(" ").lower() for name in names}
    if "" in result or len(result) != len(names):
        raise ProviderCreationConflict("Requirement names must be nonblank and unique.")
    return result


async def configure_membership(
    conn: AsyncConnection[dict[str, Any]], template_id: int, names: Sequence[str]
) -> None:
    definitions = await resolve_definitions(conn, names)
    for key in sorted(definitions):
        await conn.execute(
            "INSERT INTO template_requirements VALUES (%s,%s)",
            (template_id, definitions[key]),
        )


async def resolve_definitions(
    conn: AsyncConnection[dict[str, Any]], names: Sequence[str]
) -> dict[str, int]:
    definitions = {}
    for name in sorted(names, key=normalize_name):
        await conn.execute(
            "INSERT INTO requirement_definitions(name) VALUES (%s) ON CONFLICT DO NOTHING",
            (name.strip(" "),),
        )
        definition = await (
            await conn.execute(
                "SELECT id FROM requirement_definitions WHERE lower(btrim(name))=lower(btrim(%s))",
                (name,),
            )
        ).fetchone()
        if definition is None:
            raise ProviderCreationConflict(
                "Requirement definition changed concurrently."
            )
        definitions[normalize_name(name)] = int(definition["id"])
    return definitions


class CatalogRepository:
    def __init__(self, pool: DatabasePool) -> None:
        self.pool = pool

    async def ensure_version(
        self,
        provider_type_name: str,
        requirement_names: Sequence[str],
        *,
        template_version: int,
    ) -> ProviderTypeTemplate:
        name = provider_type_name.strip(" ")
        names = normalized_names(requirement_names)
        require_templates(requirement_names)
        if not name or isinstance(template_version, bool) or template_version < 1:
            raise ProviderCreationConflict(
                "A named type and positive version are required."
            )
        async with connection(self.pool) as conn:
            await conn.execute(
                "SELECT pg_advisory_xact_lock(hashtextextended(%s,0))",
                ("catalog:" + name.lower(),),
            )
            await conn.execute(
                "INSERT INTO provider_types(name) VALUES (%s) ON CONFLICT DO NOTHING",
                (name,),
            )
            kind = await (
                await conn.execute(
                    "SELECT id FROM provider_types WHERE lower(btrim(name))=lower(btrim(%s)) FOR UPDATE",
                    (name,),
                )
            ).fetchone()
            if kind is None:
                raise ProviderCreationConflict("Provider type changed concurrently.")
            row = await (
                await conn.execute(
                    CATALOG_QUERY + " WHERE t.id=%s AND c.template_version=%s",
                    (kind["id"], template_version),
                )
            ).fetchone()
            if row is not None:
                if normalized_names(row["requirements"]) != names:
                    raise ProviderCreationConflict(
                        "This checklist version already has different requirements."
                    )
                return ProviderTypeTemplate.model_validate(row)
            header = await (
                await conn.execute(
                    "INSERT INTO checklist_templates(provider_type_id,template_version) VALUES (%s,%s) RETURNING id",
                    (kind["id"], template_version),
                )
            ).fetchone()
            if header is None:
                raise ProviderCreationConflict(
                    "Checklist version could not be configured."
                )
            await configure_membership(conn, header["id"], requirement_names)
            row = await (
                await conn.execute(CATALOG_QUERY + " WHERE c.id=%s", (header["id"],))
            ).fetchone()
            return ProviderTypeTemplate.model_validate(row)
