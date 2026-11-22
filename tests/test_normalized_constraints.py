"""Target ownership, uniqueness, and required-value constraints reject invalid writes."""

import asyncio
from uuid import uuid4

import pytest
from psycopg.errors import CheckViolation, ForeignKeyViolation, UniqueViolation

from app.database import create_pool
from app.models import SubmitUpdateRequest
from app.repository.catalog import CatalogRepository
from app.repository.updates import UpdateRepository
from tests.database import disposable_database, migrate_test_database
from tests.test_normalized_workflows import provider_fixture


def test_target_rejects_wrong_owners_versions_duplicates_and_invalid_values():
    async def scenario(url):
        async with create_pool(url) as pool:
            first, second = await provider_fixture(pool), await provider_fixture(pool)
            future = await CatalogRepository(pool).ensure_version(
                "Dentist", ["Drug screening", "Offer letter"], template_version=2
            )
            update = await UpdateRepository(pool).claim(
                SubmitUpdateRequest(
                    provider_id=first.id, request_id=uuid4(), update_text="Synthetic"
                )
            )
            a, b = first.requirements[0], second.requirements[0]
            cases = [
                (
                    ForeignKeyViolation,
                    "INSERT INTO requirements(provider_id,checklist_template_id,requirement_definition_id,status) SELECT %s,%s,id,'Outstanding' FROM requirement_definitions WHERE name='Offer letter'",
                    (first.id, future.checklist_template_id),
                ),
                (
                    ForeignKeyViolation,
                    "INSERT INTO suggestions(update_id,requirement_id,provider_id,requirement_version,proposed_status,supporting_text) VALUES (%s,%s,%s,0,'Completed','Synthetic')",
                    (update.update.id, b.id, first.id),
                ),
                (
                    ForeignKeyViolation,
                    "INSERT INTO update_requirement_snapshots(update_id,requirement_id,provider_id,status,requirement_version) VALUES (%s,%s,%s,'Outstanding',0)",
                    (update.update.id, b.id, first.id),
                ),
                (
                    UniqueViolation,
                    "INSERT INTO template_requirements VALUES (%s,%s)",
                    (future.checklist_template_id, a.requirement_definition_id),
                ),
                (
                    UniqueViolation,
                    "INSERT INTO provider_types(name) VALUES (' dentist ')",
                    (),
                ),
                (
                    UniqueViolation,
                    "INSERT INTO requirement_definitions(name) VALUES (' DRUG SCREENING ')",
                    (),
                ),
                (
                    CheckViolation,
                    "UPDATE requirements SET status=' ' WHERE id=%s",
                    (a.id,),
                ),
                (
                    CheckViolation,
                    "UPDATE requirements SET version=-1 WHERE id=%s",
                    (a.id,),
                ),
                (
                    CheckViolation,
                    "INSERT INTO checklist_templates(provider_type_id,template_version) VALUES (%s,0)",
                    (future.id,),
                ),
            ]
            async with pool.connection() as conn:
                for expected, query, values in cases:
                    with pytest.raises(expected):
                        async with conn.transaction():
                            await conn.execute(query, values)
                policies = await (
                    await conn.execute(
                        "SELECT confdeltype,count(*) AS n FROM pg_constraint WHERE contype='f' AND connamespace='public'::regnamespace GROUP BY confdeltype"
                    )
                ).fetchall()
                assert {row["confdeltype"]: row["n"] for row in policies} == {
                    "c": 11,
                    "r": 5,
                }
                collections = await (
                    await conn.execute(
                        "SELECT table_name,column_name FROM information_schema.columns WHERE table_schema='public' AND (data_type IN ('json','jsonb','ARRAY'))"
                    )
                ).fetchall()
                assert collections == []
                ids = await (
                    await conn.execute(
                        "SELECT table_name,data_type,identity_generation FROM information_schema.columns WHERE table_schema='public' AND column_name='id'"
                    )
                ).fetchall()
                assert len(ids) == 10
                assert all(
                    row["data_type"] == "integer"
                    and row["identity_generation"] == "ALWAYS"
                    for row in ids
                )

    with disposable_database() as url:
        migrate_test_database(url)
        asyncio.run(scenario(url))
