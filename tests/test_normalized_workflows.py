"""Existing workflows share integer identities, captured versions, and archived write locks."""

import asyncio
from datetime import date
from uuid import uuid4

import pytest

from app.checklist_models import ChecklistEditRequest
from app.database import create_pool
from app.models import (
    AnalyzeUpdateResponse,
    ReviewRequest,
    SubmitUpdateRequest,
    SuggestedChange,
)
from app.provider_models import CreateProviderRequest
from app.repository import RecordNotFound, connection
from app.repository.catalog import CatalogRepository
from app.repository.checklist import ChecklistRepository
from app.repository.providers import ProviderRepository
from app.repository.reviews import ReviewRepository
from app.repository.updates import UpdateRepository
from app.rules.provider_state import ProviderArchivedConflict
from app.rules.review import ReviewConflict
from tests.database import disposable_database, migrate_test_database


async def provider_fixture(pool):
    template = await CatalogRepository(pool).ensure_version(
        "Dentist", ["Drug screening"], template_version=1
    )
    return await ProviderRepository(pool).create_from_template(
        CreateProviderRequest(
            creation_request_id=uuid4(),
            name="Synthetic",
            provider_type_id=template.id,
            checklist_template_id=template.checklist_template_id,
            template_fingerprint=template.template_fingerprint,
        ),
        initial_status="Outstanding",
    )


def test_captured_context_review_staleness_and_manual_retry_share_one_counter():
    async def scenario(url):
        async with create_pool(url) as pool:
            provider = await provider_fixture(pool)
            requirement = provider.requirements[0]
            updates, edits = UpdateRepository(pool), ChecklistRepository(pool)
            claim = await updates.claim(
                SubmitUpdateRequest(
                    provider_id=provider.id,
                    request_id=uuid4(),
                    update_text="Drug screening completed",
                )
            )
            edit_request = ChecklistEditRequest(
                operation_id=uuid4(),
                expected_version=0,
                status="Scheduled",
                scheduled_date=date(2026, 11, 20),
                deadline=date(2026, 11, 21),
            )
            event = await edits.edit(provider.id, requirement.id, edit_request)
            saved = await updates.complete(
                claim.update.id,
                AnalyzeUpdateResponse(
                    message="Review",
                    suggestions=[
                        SuggestedChange(
                            requirement="Drug screening",
                            proposed_status="Completed",
                            supporting_text="completed",
                        )
                    ],
                    ambiguities=["Confirm date"],
                ),
            )
            captured = saved.provider_snapshot.requirements[0]
            assert (captured.status, captured.version, captured.scheduled_date) == (
                "Outstanding",
                0,
                None,
            )
            assert saved.ambiguities == ["Confirm date"]
            with pytest.raises(ReviewConflict):
                await ReviewRepository(pool).decide(
                    saved.suggestions[0].id, ReviewRequest(action="approve")
                )
            second = await updates.claim(
                SubmitUpdateRequest(
                    provider_id=provider.id,
                    request_id=uuid4(),
                    update_text="Drug screening completed",
                )
            )
            completed = await updates.complete(
                second.update.id,
                AnalyzeUpdateResponse(
                    message="Review",
                    suggestions=[
                        SuggestedChange(
                            requirement="Drug screening",
                            proposed_status="Completed",
                            supporting_text="completed",
                        )
                    ],
                ),
            )
            await ReviewRepository(pool).decide(
                completed.suggestions[0].id, ReviewRequest(action="approve")
            )
            retry = await edits.edit(provider.id, requirement.id, edit_request)
            assert (
                retry.id == event.id and retry.operation_id == edit_request.operation_id
            )
            current = await ProviderRepository(pool).get_provider(provider.id)
            assert (
                current.requirements[0].status,
                current.requirements[0].version,
            ) == ("Completed", 2)
            assert current.requirements[0].deadline == date(2026, 11, 21)
            assert (await edits.list_for_provider(provider.id))[
                0
            ].requirement_name == "Drug screening"

    with disposable_database() as url:
        migrate_test_database(url)
        asyncio.run(scenario(url))


def test_archived_provider_blocks_new_progress_but_inflight_evidence_can_finish():
    async def scenario(url):
        async with create_pool(url) as pool:
            provider = await provider_fixture(pool)
            updates = UpdateRepository(pool)
            claim = await updates.claim(
                SubmitUpdateRequest(
                    provider_id=provider.id,
                    request_id=uuid4(),
                    update_text="Drug screening completed",
                )
            )
            async with connection(pool) as conn:
                await conn.execute(
                    "UPDATE providers SET archived_at=now() WHERE id=%s", (provider.id,)
                )
            saved = await updates.complete(
                claim.update.id,
                AnalyzeUpdateResponse(
                    message="Review",
                    suggestions=[
                        SuggestedChange(
                            requirement="Drug screening",
                            proposed_status="Completed",
                            supporting_text="completed",
                        )
                    ],
                ),
            )
            assert saved.processing_state == "completed"
            with pytest.raises(ProviderArchivedConflict):
                await updates.claim(
                    SubmitUpdateRequest(
                        provider_id=provider.id,
                        request_id=uuid4(),
                        update_text="New update",
                    )
                )
            with pytest.raises(ProviderArchivedConflict):
                await ReviewRepository(pool).decide(
                    saved.suggestions[0].id, ReviewRequest(action="reject")
                )
            with pytest.raises(ProviderArchivedConflict):
                await ChecklistRepository(pool).edit(
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
            async with connection(pool) as conn:
                await conn.execute("DELETE FROM providers WHERE id=%s", (provider.id,))
            with pytest.raises(RecordNotFound):
                await updates.complete(
                    claim.update.id, AnalyzeUpdateResponse(message="Must not recreate")
                )
            with pytest.raises(RecordNotFound):
                await updates.fail(claim.update.id, "model")

    with disposable_database() as url:
        migrate_test_database(url)
        asyncio.run(scenario(url))
