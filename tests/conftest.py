"""Shared synthetic inputs and a suite-wide real-model request guard."""

import asyncio
from collections.abc import Iterator

import psycopg
import pytest
from fastapi.testclient import TestClient
from pydantic_ai.models import override_allow_model_requests
from pydantic_ai.models.test import TestModel

from app import main
from app.agent import AnalyzeUpdateRequest, ProviderContext, Requirement, build_agent
from app.database import create_pool
from app.models import StoredProvider
from app.repository.providers import ProviderRepository
from app.seed import KEKOA_ID, seed_synthetic
from tests.database import configured_test_url, migrate_test_database


@pytest.fixture
def db_url() -> str:
    url = configured_test_url()
    migrate_test_database(url)
    with psycopg.connect(url) as conn:
        conn.execute(
            "TRUNCATE review_decisions,suggestions,updates,requirements,providers,requirement_templates,provider_types"
        )
    return url


@pytest.fixture
def seeded_provider(db_url: str) -> StoredProvider:
    async def prepare() -> StoredProvider:
        async with create_pool(db_url) as pool:
            await seed_synthetic(pool)
            return await ProviderRepository(pool).get_provider(KEKOA_ID)

    return asyncio.run(prepare())


@pytest.fixture(autouse=True)
def block_real_model_requests() -> Iterator[None]:
    with override_allow_model_requests(False):
        yield


@pytest.fixture
def update_request() -> AnalyzeUpdateRequest:
    return AnalyzeUpdateRequest(
        provider=ProviderContext(
            provider_id="kekoa-ejemplo",
            name="Dr. Kekoa Ejemplo",
            provider_type="Dentist",
            proposed_start_date="2027-01-15",
            requirements=[
                Requirement(name="Hawaii dental license", status="Outstanding"),
                Requirement(name="Drug screening", status="Outstanding"),
            ],
        ),
        update_text="Drug screening scheduled on the 18th.",
    )


@pytest.fixture
def extraction_model() -> TestModel:
    return TestModel(custom_output_args={"suggestions": [], "ambiguities": []})


@pytest.fixture
def client(
    extraction_model: TestModel,
    db_url: str,
    seeded_provider: StoredProvider,
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[TestClient]:
    monkeypatch.setenv("DATABASE_URL", db_url)
    previous = main.app.dependency_overrides.copy()
    main.app.dependency_overrides[main.get_agent_factory] = lambda: (
        lambda: build_agent(extraction_model)
    )
    try:
        with TestClient(main.app) as test_client:
            yield test_client
    finally:
        main.app.dependency_overrides.clear()
        main.app.dependency_overrides.update(previous)
