"""Shared synthetic inputs and a suite-wide real-model request guard."""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from pydantic_ai.models import override_allow_model_requests
from pydantic_ai.models.test import TestModel

from app import main
from app.agent import AnalyzeUpdateRequest, ProviderContext, Requirement, build_agent


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
def client(extraction_model: TestModel) -> Iterator[TestClient]:
    previous = main.app.dependency_overrides.copy()
    main.app.dependency_overrides[main.get_extraction_agent] = lambda: build_agent(
        extraction_model
    )
    try:
        with TestClient(main.app) as test_client:
            yield test_client
    finally:
        main.app.dependency_overrides.clear()
        main.app.dependency_overrides.update(previous)
