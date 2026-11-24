"""Shared synthetic inputs and a suite-wide real-model request guard."""

import asyncio
import os
from collections.abc import Iterator

import httpx
import psycopg
import pytest
from fastapi.testclient import TestClient
from pydantic_ai.models import override_allow_model_requests
from pydantic_ai.models.test import TestModel

from app import main
from app.agent import AnalyzeUpdateRequest, ProviderContext, Requirement, build_agent
from app.database import create_pool
from app.embeddings import get_embedding_client
from app.models import StoredProvider
from app.qa_agent import build_qa_agent, get_qa_agent_factory
from app.seed import seed_synthetic
from tests.database import ROOT, configured_test_url, migrate_test_database
from tests.knowledge_fixtures import SyntheticEmbeddings
from tests.local_postgres import stop_local_database

os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(ROOT / ".superpowers/browsers"))


@pytest.fixture(scope="session", autouse=True)
def local_database_lifecycle():
    try:
        yield
    finally:
        stop_local_database()


@pytest.fixture
def db_url() -> str:
    url = configured_test_url()
    migrate_test_database(url)
    with psycopg.connect(url) as conn:
        conn.execute(
            "TRUNCATE qa_citations,qa_claims,qa_retrieved_chunks,qa_corpus_versions,qa_runs,requirement_knowledge_links,knowledge_publications,knowledge_review_issues,knowledge_scopes,knowledge_embeddings,knowledge_chunks,knowledge_versions,checklist_edits,review_decisions,suggestions,update_ambiguities,update_requirement_snapshots,updates,requirements,providers,template_requirements,checklist_templates,requirement_definitions,provider_types"
        )
        conn.execute(
            "UPDATE knowledge_state SET revision=0,active_space_id=(SELECT id FROM embedding_spaces WHERE model='text-embedding-3-small' AND version='1' AND dimensions=1536)"
        )
    return url


@pytest.fixture
def seeded_provider(db_url: str) -> StoredProvider:
    async def prepare() -> StoredProvider:
        async with create_pool(db_url) as pool:
            return await seed_synthetic(pool)

    return asyncio.run(prepare())


@pytest.fixture(autouse=True)
def block_real_model_requests(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("DISABLE_EMBEDDING_REQUESTS", "1")
    monkeypatch.setenv("DISABLE_SOURCE_FETCH", "1")
    real_http = httpx.AsyncHTTPTransport.handle_async_request

    async def local_http_only(transport, request):
        if request.url.host not in {"localhost", "127.0.0.1", "::1"}:
            raise AssertionError(
                "Automated tests cannot contact external HTTP services."
            )
        return await real_http(transport, request)

    monkeypatch.setattr(
        httpx.AsyncHTTPTransport, "handle_async_request", local_http_only
    )
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
    main.app.dependency_overrides[get_embedding_client] = SyntheticEmbeddings
    main.app.dependency_overrides[main.get_agent_factory] = lambda: (
        lambda: build_agent(extraction_model)
    )
    main.app.dependency_overrides[get_qa_agent_factory] = lambda: (
        lambda: build_qa_agent(
            TestModel(custom_output_args={"outcome": "cannot_answer"})
        )
    )
    try:
        with TestClient(main.app) as test_client:
            yield test_client
    finally:
        main.app.dependency_overrides.clear()
        main.app.dependency_overrides.update(previous)
