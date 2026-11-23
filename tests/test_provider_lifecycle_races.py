"""Observe provider-lock ordering for lifecycle and existing checklist mutations."""

import asyncio
from uuid import uuid4

import pytest

from app.checklist_models import ChecklistEditRequest
from app.database import create_pool
from app.repository.checklist import ChecklistRepository
from app.repository.providers import ProviderRepository
from app.rules.provider_state import ProviderArchivedConflict
from tests.database import disposable_database, migrate_test_database
from tests.test_catalog_races import wait_until_row_lock_blocks
from tests.test_normalized_workflows import provider_fixture


def test_archive_waits_for_existing_edit_then_blocks_new_edits():
    from app.repository.provider_lifecycle import ProviderLifecycleRepository

    async def scenario(url):
        async with create_pool(url) as pool:
            provider = await provider_fixture(pool)
            item = provider.requirements[0]
            async with pool.connection() as blocker:
                await blocker.execute(
                    "SELECT id FROM providers WHERE id=%s FOR UPDATE", (provider.id,)
                )
                pending = asyncio.create_task(
                    ProviderLifecycleRepository(pool).set_archived(provider.id, True)
                )
                try:
                    await wait_until_row_lock_blocks(blocker)
                    await blocker.execute(
                        "UPDATE requirements SET status='Scheduled',version=version+1 WHERE id=%s",
                        (item.id,),
                    )
                    await blocker.commit()
                    archived = await asyncio.wait_for(pending, 5)
                    assert archived.archived_at is not None
                    assert (
                        archived.requirements[0].status,
                        archived.requirements[0].version,
                    ) == ("Scheduled", 1)
                finally:
                    await blocker.rollback()
                    if not pending.done():
                        pending.cancel()
                        await asyncio.gather(pending, return_exceptions=True)
            with pytest.raises(ProviderArchivedConflict):
                await ChecklistRepository(pool).edit(
                    provider.id,
                    item.id,
                    ChecklistEditRequest(
                        operation_id=uuid4(),
                        expected_version=1,
                        status="Completed",
                        scheduled_date=None,
                        deadline=None,
                    ),
                )
            restored = await ProviderLifecycleRepository(pool).set_archived(
                provider.id, False
            )
            current = await ProviderRepository(pool).get_provider(provider.id)
            assert restored == current
            assert (
                current.requirements[0].status,
                current.requirements[0].version,
            ) == ("Scheduled", 1)

    with disposable_database() as url:
        migrate_test_database(url)
        asyncio.run(scenario(url))
