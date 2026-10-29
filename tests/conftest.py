"""Shared synthetic inputs and a suite-wide real-model request guard."""

from collections.abc import Iterator

import pytest
from pydantic_ai.models import override_allow_model_requests

from app.agent import AnalyzeUpdateRequest, ProviderContext, Requirement


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
