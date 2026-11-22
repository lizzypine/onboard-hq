"""Observe real PostgreSQL blocking before releasing competing catalog/lifecycle writes."""

import asyncio
from uuid import uuid4

import pytest

from app.checklist_models import ChecklistEditRequest
from app.database import create_pool
from app.models import AnalyzeUpdateResponse, SubmitUpdateRequest
from app.provider_models import CreateProviderRequest
from app.repository import RecordNotFound
from app.repository.catalog import CatalogRepository
from app.repository.checklist import ChecklistRepository
from app.repository.providers import ProviderRepository
from app.repository.updates import UpdateRepository
from app.rules.provider_state import ProviderArchivedConflict
from tests.database import disposable_database, migrate_test_database
from tests.test_normalized_workflows import provider_fixture


async def wait_until_row_lock_blocks(conn):
    for _ in range(200):
        await conn.execute("SELECT pg_stat_clear_snapshot()")
        row = await (
            await conn.execute(
                "SELECT EXISTS(SELECT 1 FROM pg_stat_activity WHERE datname=current_database() AND pid<>pg_backend_pid() AND wait_event_type='Lock' AND query LIKE '%FOR UPDATE%') AS waiting"
            )
        ).fetchone()
        if row["waiting"]:
            return
        await asyncio.sleep(0.01)
    raise AssertionError(
        "Competing operation never reached the expected PostgreSQL row lock"
    )


def test_new_provider_sees_membership_committed_while_waiting_for_template_lock():
    async def scenario(url):
        async with create_pool(url) as pool:
            template = await CatalogRepository(pool).ensure_version(
                "Dentist", ["Drug screening"], template_version=1
            )
            async with pool.connection() as blocker:
                await blocker.execute(
                    "SELECT id FROM checklist_templates WHERE id=%s FOR UPDATE",
                    (template.checklist_template_id,),
                )
                pending = asyncio.create_task(
                    ProviderRepository(pool).create_from_template(
                        CreateProviderRequest(
                            creation_request_id=uuid4(),
                            name="Synthetic race",
                            provider_type_id=template.id,
                        ),
                        initial_status="Outstanding",
                    )
                )
                try:
                    await wait_until_row_lock_blocks(blocker)
                    definition = await (
                        await blocker.execute(
                            "INSERT INTO requirement_definitions(name) VALUES ('Offer letter') RETURNING id"
                        )
                    ).fetchone()
                    await blocker.execute(
                        "INSERT INTO template_requirements VALUES (%s,%s)",
                        (template.checklist_template_id, definition["id"]),
                    )
                    await blocker.commit()
                    saved = await asyncio.wait_for(pending, 5)
                finally:
                    await blocker.rollback()
                    if not pending.done():
                        pending.cancel()
                        await asyncio.gather(pending, return_exceptions=True)
            assert [r.name for r in saved.requirements] == [
                "Drug screening",
                "Offer letter",
            ]

    with disposable_database() as url:
        migrate_test_database(url)
        asyncio.run(scenario(url))


@pytest.mark.parametrize(
    "operation", ["manual_archive", "complete_archive", "complete_delete"]
)
def test_provider_lock_serializes_inflight_work_with_archive_or_delete(operation):
    async def scenario(url):
        async with create_pool(url) as pool:
            provider = await provider_fixture(pool)
            updates = UpdateRepository(pool)
            claim = await updates.claim(
                SubmitUpdateRequest(
                    provider_id=provider.id,
                    request_id=uuid4(),
                    update_text="Synthetic pending update",
                )
            )
            async with pool.connection() as blocker:
                if operation == "complete_delete":
                    await blocker.execute(
                        "DELETE FROM providers WHERE id=%s", (provider.id,)
                    )
                else:
                    await blocker.execute(
                        "UPDATE providers SET archived_at=now() WHERE id=%s",
                        (provider.id,),
                    )
                action = (
                    ChecklistRepository(pool).edit(
                        provider.id,
                        provider.requirements[0].id,
                        ChecklistEditRequest(
                            operation_id=uuid4(),
                            expected_version=0,
                            status="Scheduled",
                            scheduled_date=None,
                            deadline=None,
                        ),
                    )
                    if operation == "manual_archive"
                    else updates.complete(
                        claim.update.id, AnalyzeUpdateResponse(message="Evidence saved")
                    )
                )
                pending = asyncio.create_task(action)
                try:
                    await wait_until_row_lock_blocks(blocker)
                    await blocker.commit()
                    if operation == "manual_archive":
                        with pytest.raises(ProviderArchivedConflict):
                            await asyncio.wait_for(pending, 5)
                    elif operation == "complete_delete":
                        with pytest.raises(RecordNotFound):
                            await asyncio.wait_for(pending, 5)
                    else:
                        assert (
                            await asyncio.wait_for(pending, 5)
                        ).processing_state == "completed"
                finally:
                    await blocker.rollback()
                    if not pending.done():
                        pending.cancel()
                        await asyncio.gather(pending, return_exceptions=True)
            if operation != "complete_delete":
                current = await ProviderRepository(pool).get_provider(provider.id)
                assert current.archived_at is not None
                assert (
                    current.requirements[0].status,
                    current.requirements[0].version,
                ) == ("Outstanding", 0)

    with disposable_database() as url:
        migrate_test_database(url)
        asyncio.run(scenario(url))
