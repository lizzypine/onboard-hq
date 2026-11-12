"""Stored provider read and idempotent template-based seed behavior."""

import asyncio
from uuid import uuid4

from fastapi.testclient import TestClient

from app import main
from app.database import create_pool
from tests.database import disposable_database


def test_seed_preserves_progress_and_does_not_backfill_templates(db_url):
    from app.repository.providers import ProviderRepository
    from app.seed import KEKOA_ID, seed_synthetic

    async def exercise():
        async with create_pool(db_url) as pool:
            await seed_synthetic(pool)
            before = await ProviderRepository(pool).get_provider(KEKOA_ID)
            async with pool.connection() as conn:
                await conn.execute(
                    "UPDATE requirements SET status='Completed' WHERE provider_id=%s AND name='Drug screening'",
                    (KEKOA_ID,),
                )
                await conn.execute(
                    "INSERT INTO requirement_templates(id,provider_type_id,name) SELECT %s,provider_type_id,'Later template' FROM providers WHERE id=%s",
                    (uuid4(), KEKOA_ID),
                )
                await conn.execute(
                    "UPDATE requirement_templates SET name='Renamed template' WHERE name='Offer letter'"
                )
            await seed_synthetic(pool)
            after = await ProviderRepository(pool).get_provider(KEKOA_ID)
            assert len(before.requirements) == len(after.requirements) == 5
            assert (
                next(r for r in after.requirements if r.name == "Drug screening").status
                == "Completed"
            )
            assert "Offer letter" in {r.name for r in after.requirements}
            assert "Later template" not in {r.name for r in after.requirements}

    asyncio.run(exercise())


def test_provider_read_route_returns_typed_database_records(db_url, monkeypatch):
    from app.seed import KEKOA_ID, seed_synthetic

    async def prepare():
        async with create_pool(db_url) as pool:
            await seed_synthetic(pool)

    asyncio.run(prepare())
    monkeypatch.setenv("DATABASE_URL", db_url)
    with TestClient(main.app) as client:
        listing = client.get("/providers")
        assert listing.status_code == 200
        response = client.get(f"/providers/{KEKOA_ID}")
        assert response.status_code == 200
        data = response.json()
        assert data["provider_type"] == "Dentist"
        assert data["proposed_start_date"] == "2026-12-01"
        assert len(data["requirements"]) == 5
        assert client.get(f"/providers/{uuid4()}").status_code == 404


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
    from app.models import ProviderSummary, Requirement
    from app.repository.providers import ProviderRepository

    async def exercise():
        async with create_pool(db_url) as pool:
            repository = ProviderRepository(pool)
            for name in ("Type A", "Type B"):
                type_id, template_id, provider_id = uuid4(), uuid4(), uuid4()
                async with pool.connection() as conn:
                    await conn.execute(
                        "INSERT INTO provider_types VALUES (%s,%s)", (type_id, name)
                    )
                    await conn.execute(
                        "INSERT INTO requirement_templates VALUES (%s,%s,%s)",
                        (template_id, type_id, name + " requirement"),
                    )
                provider = ProviderSummary(
                    id=provider_id,
                    name="Synthetic",
                    provider_type=name,
                    proposed_start_date=None,
                )
                initial = {
                    name + " requirement": Requirement(
                        name=name + " requirement", status="Outstanding"
                    )
                }
                assert await repository.initialize_provider(provider, type_id, initial)
                saved = await repository.get_provider(provider_id)
                assert [r.name for r in saved.requirements] == [name + " requirement"]

    asyncio.run(exercise())
