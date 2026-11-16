"""Stored provider read and idempotent template-based seed behavior."""

import asyncio
from uuid import uuid4

from fastapi.testclient import TestClient

from app import main
from app.database import create_pool
from app.repository.catalog import CatalogRepository
from tests.database import disposable_database


def test_seed_preserves_progress_and_does_not_backfill_templates(db_url):
    from app.seed import seed_synthetic

    async def exercise():
        async with create_pool(db_url) as pool:
            before = await seed_synthetic(pool)
            async with pool.connection() as conn:
                await conn.execute(
                    "UPDATE requirements SET status='Completed' WHERE provider_id=%s AND requirement_definition_id IN (SELECT id FROM requirement_definitions WHERE name='Drug screening')",
                    (before.id,),
                )
            await CatalogRepository(pool).ensure_version(
                "Dentist",
                [
                    "Renamed template" if r.name == "Offer letter" else r.name
                    for r in before.requirements
                ]
                + ["Later template"],
                template_version=2,
            )
            after = await seed_synthetic(pool)
            assert len(before.requirements) == len(after.requirements) == 5
            assert (
                next(r for r in after.requirements if r.name == "Drug screening").status
                == "Completed"
            )
            assert "Offer letter" in {r.name for r in after.requirements}
            assert "Later template" not in {r.name for r in after.requirements}

    asyncio.run(exercise())


def test_provider_read_route_returns_typed_database_records(db_url, monkeypatch):
    from app.seed import seed_synthetic

    async def prepare():
        async with create_pool(db_url) as pool:
            return await seed_synthetic(pool)

    saved = asyncio.run(prepare())
    monkeypatch.setenv("DATABASE_URL", db_url)
    with TestClient(main.app) as client:
        listing = client.get("/providers")
        assert listing.status_code == 200
        response = client.get(f"/providers/{saved.id}")
        assert response.status_code == 200
        data = response.json()
        assert data["provider_type"] == "Dentist"
        assert data["proposed_start_date"] == "2026-12-01"
        assert len(data["requirements"]) == 5
        assert client.get("/providers/999999999").status_code == 404


def test_provider_routes_report_missing_configuration_without_breaking_html(
    monkeypatch,
):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with TestClient(main.app) as client:
        assert client.get("/").status_code == 200
        assert client.get("/providers").status_code == 503


def test_provider_routes_report_missing_schema_safely(monkeypatch):
    with disposable_database() as url:
        monkeypatch.setenv("DATABASE_URL", url)
        with TestClient(main.app) as client:
            response = client.get("/providers")
            assert response.status_code == 503
            assert "postgresql://" not in response.text
            assert "undefined" not in response.text.lower()


def test_different_types_initialize_distinct_synthetic_checklists(db_url):
    from app.models import Requirement
    from app.provider_models import CreateProviderRequest
    from app.repository.providers import ProviderRepository

    async def exercise():
        async with create_pool(db_url) as pool:
            repository = ProviderRepository(pool)
            for name in ("Type A", "Type B"):
                template = await CatalogRepository(pool).ensure_version(
                    name, [name + " requirement"], template_version=1
                )
                initial = {
                    name + " requirement": Requirement(
                        name=name + " requirement", status="Outstanding"
                    )
                }
                saved = await repository.initialize_provider(
                    CreateProviderRequest(
                        creation_request_id=uuid4(),
                        name="Synthetic",
                        provider_type_id=template.id,
                    ),
                    initial,
                )
                assert [r.name for r in saved.requirements] == [name + " requirement"]

    asyncio.run(exercise())
