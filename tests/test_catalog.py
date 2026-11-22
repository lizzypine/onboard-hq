"""Whole-checklist assignment, normalized catalogs, and retry isolation."""

import asyncio
from uuid import uuid4

import pytest

from app.database import create_pool
from app.provider_models import CreateProviderRequest
from app.repository import connection
from app.repository.providers import ProviderRepository
from tests.database import disposable_database, migrate_test_database


def test_catalog_normalization_and_assigned_versions_survive_retry_and_archive():
    async def scenario(url):
        from app.repository.catalog import CatalogRepository

        async with create_pool(url) as pool:
            catalog = CatalogRepository(pool)
            first = await catalog.ensure_version(
                "Dentist", ["Drug screening"], template_version=1
            )
            same = await catalog.ensure_version(
                " dentist ", [" drug screening "], template_version=1
            )
            assert same.id == first.id
            assert same.requirements == ["Drug screening"]
            repo = ProviderRepository(pool)
            request = CreateProviderRequest(
                creation_request_id=uuid4(),
                name="Same display name",
                provider_type_id=first.id,
            )
            saved = await repo.create_from_template(
                request, initial_status="Outstanding"
            )
            assert saved.template_version == 1
            await catalog.ensure_version(
                "Dentist", ["Drug screening", "Offer letter"], template_version=2
            )
            retry = await repo.create_from_template(
                request, initial_status="Outstanding"
            )
            assert retry.id == saved.id
            assert retry.template_version == 1
            assert [r.name for r in retry.requirements] == ["Drug screening"]
            another = await repo.create_from_template(
                request.model_copy(update={"creation_request_id": uuid4()}),
                initial_status="Outstanding",
            )
            assert another.id != saved.id
            assert another.template_version == 2
            assert len(another.requirements) == 2
            with pytest.raises(ValueError):
                await catalog.ensure_version(
                    "Dentist", ["Offer letter"], template_version=1
                )
            async with connection(pool) as conn:
                await conn.execute(
                    "UPDATE providers SET archived_at=now() WHERE id=%s", (saved.id,)
                )
            retry = await repo.create_from_template(
                request, initial_status="Outstanding"
            )
            assert retry.archived_at is not None
            assert retry.template_version == 1
            assert [p.id for p in await repo.list_providers()] == [another.id]
            assert [p.id for p in await repo.list_providers("archived")] == [saved.id]

    with disposable_database() as url:
        migrate_test_database(url)
        asyncio.run(scenario(url))
