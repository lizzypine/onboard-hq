"""Migration five preserves the complete version-four graph and repeatable seed."""

import asyncio
import json
import shutil
from datetime import date
from uuid import uuid4

import psycopg
from psycopg import sql

from app.checklist_models import ChecklistEditRequest
from app.database import create_pool
from app.models import (
    AnalyzeUpdateResponse,
    ReviewRequest,
    SubmitUpdateRequest,
    SuggestedChange,
)
from app.repository.checklist import ChecklistRepository
from app.repository.reviews import ReviewRepository
from app.repository.updates import UpdateRepository
from db.seed import seed_synthetic
from tests.database import ROOT, disposable_database, migrate_test_database
from tests.fixtures.legacy_database import dbmate


def stored_rows(url, historical=None):
    result = {}
    with psycopg.connect(url) as conn:
        tables = conn.execute(
            "SELECT tablename FROM pg_tables WHERE schemaname='public' AND tablename <> 'schema_migrations' ORDER BY tablename"
        ).fetchall()
        for (table,) in tables:
            if historical is not None and table not in historical:
                continue
            rows = [
                row[0]
                for row in conn.execute(
                    sql.SQL("SELECT to_jsonb(t) FROM {} t").format(
                        sql.Identifier(table)
                    )
                )
            ]
            if table == "requirements":
                for row in rows:
                    for field in [
                        "initial_status",
                        "initial_scheduled_date",
                        "initial_deadline",
                    ]:
                        row.pop(field, None)
            result[table] = sorted(json.dumps(row, sort_keys=True) for row in rows)
    return result


async def initialize_history(url):
    async with create_pool(url) as pool:
        provider = await seed_synthetic(pool)
        updates = UpdateRepository(pool)
        claim = await updates.claim(
            SubmitUpdateRequest(
                provider_id=provider.id,
                request_id=uuid4(),
                update_text="Drug screening completed.",
            )
        )
        saved = await updates.complete(
            claim.update.id,
            AnalyzeUpdateResponse(
                message="Review",
                suggestions=[
                    SuggestedChange(
                        requirement="Drug screening",
                        proposed_status="Completed",
                        supporting_text="Drug screening completed.",
                    )
                ],
            ),
        )
        await ReviewRepository(pool).decide(
            saved.suggestions[0].id, ReviewRequest(action="approve")
        )
        item = next(r for r in provider.requirements if r.name == "Drug screening")
        await ChecklistRepository(pool).edit(
            provider.id,
            item.id,
            ChecklistEditRequest(
                operation_id=uuid4(),
                expected_version=1,
                status="Pending",
                scheduled_date=date(2026, 12, 10),
                deadline=date(2026, 12, 20),
            ),
        )


def test_additions_upgrade_preserves_version_four_evidence_and_seed(tmp_path):
    four = tmp_path / "version-four"
    four.mkdir()
    for migration in sorted((ROOT / "db/migrations").glob("*.sql"))[:4]:
        shutil.copy(migration, four / migration.name)
    with disposable_database() as url:
        result = dbmate(url, "up", migrations=four)
        assert result.returncode == 0, result.stderr
        asyncio.run(initialize_history(url))
        before = stored_rows(url)
        assert len(before) == 12
        assert (
            len(before["updates"])
            == len(before["suggestions"])
            == len(before["review_decisions"])
            == len(before["checklist_edits"])
            == 1
        )
        migrate_test_database(url)
        assert stored_rows(url, historical=before) == before

        async def reseed():
            async with create_pool(url) as pool:
                return await seed_synthetic(pool)

        provider = asyncio.run(reseed())
        assert (
            next(r for r in provider.requirements if r.name == "Drug screening").status
            == "Pending"
        )
        assert stored_rows(url, historical=before) == before
        with psycopg.connect(url) as conn:
            assert conn.execute(
                "SELECT count(*) FROM schema_migrations"
            ).fetchone() == (6,)
            assert conn.execute(
                "SELECT count(*) FROM requirements WHERE checklist_template_id IS NULL OR initial_status IS NOT NULL OR initial_scheduled_date IS NOT NULL OR initial_deadline IS NOT NULL"
            ).fetchone() == (0,)
        status = dbmate(url, "status")
        assert status.returncode == 0 and "Pending: 0" in status.stdout
