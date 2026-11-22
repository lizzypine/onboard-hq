"""The synthetic seed must recover its saved provider without resetting progress."""

import asyncio
from datetime import date

from app.database import create_pool
from app.repository import connection
from db.seed import seed_synthetic
from tests.database import disposable_database, migrate_test_database


def test_seed_returns_generated_identity_and_preserves_progress_archive_and_version():
    async def scenario(url):
        async with create_pool(url) as pool:
            first = await seed_synthetic(pool)
            assert type(first.id) is int and first.id > 0
            assert first.template_version == 1
            assert {r.name: r.status for r in first.requirements} == {
                "Offer letter": "Signed",
                "Hawaii dental license": "Received",
                "Drug screening": "Scheduled",
                "State NED license": "Outstanding",
                "Insurance credentialing": "Pending",
            }
            drug = next(r for r in first.requirements if r.name == "Drug screening")
            async with connection(pool) as conn:
                await conn.execute(
                    "UPDATE requirements SET status='Completed',scheduled_date='2026-11-21',version=version+1 WHERE id=%s",
                    (drug.id,),
                )
                await conn.execute(
                    "UPDATE providers SET archived_at=now() WHERE id=%s", (first.id,)
                )
            second = await seed_synthetic(pool)
            assert second.id == first.id
            assert second.archived_at is not None
            same = next(r for r in second.requirements if r.id == drug.id)
            assert (same.status, same.scheduled_date, same.version) == (
                "Completed",
                date(2026, 11, 21),
                1,
            )

    with disposable_database() as url:
        migrate_test_database(url)
        asyncio.run(scenario(url))


def test_seed_reuses_case_normalized_catalog_labels():
    from app.repository.catalog import CatalogRepository

    async def scenario(url):
        async with create_pool(url) as pool:
            await CatalogRepository(pool).ensure_version(
                "dentist",
                [
                    "offer letter",
                    "hawaii dental license",
                    "drug screening",
                    "state ned license",
                    "insurance credentialing",
                ],
                template_version=1,
            )
            saved = await seed_synthetic(pool)
            assert saved.provider_type == "dentist"
            assert (
                next(r.status for r in saved.requirements if r.name == "drug screening")
                == "Scheduled"
            )

    with disposable_database() as url:
        migrate_test_database(url)
        asyncio.run(scenario(url))
