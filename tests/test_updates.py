"""Endpoint behavior with deterministic model output and real validation."""

import asyncio
import importlib

import pytest
from fastapi.testclient import TestClient
from pydantic_ai.exceptions import (
    ModelConnectionError,
    ModelHTTPError,
    ModelTimeoutError,
    UnexpectedModelBehavior,
)
from pydantic_ai.models.test import TestModel

from app import main
from app.agent import AnalyzeUpdateRequest, build_agent


def test_mixed_scope_response(
    client: TestClient,
    extraction_model: TestModel,
    update_request: AnalyzeUpdateRequest,
) -> None:
    extraction_model.custom_output_args = {
        "suggestions": [
            {
                "requirement": "Hawaii dental license",
                "proposed_status": "Received",
                "supporting_text": "License received.",
            },
            {
                "requirement": "State NED license",
                "proposed_status": "Outstanding",
                "supporting_text": "Still waiting.",
            },
        ],
        "ambiguities": ["Original model warning."],
    }
    response = client.post(
        "/updates/analyze", json=update_request.model_dump(mode="json")
    )
    assert response.status_code == 200
    data = response.json()
    assert [s["requirement"] for s in data["suggestions"]] == ["Hawaii dental license"]
    assert any("State NED license" in warning for warning in data["ambiguities"])
    assert "Original model warning." in data["ambiguities"]


@pytest.mark.parametrize("unmatched", [False, True])
def test_no_actionable_suggestions(
    client: TestClient,
    extraction_model: TestModel,
    update_request: AnalyzeUpdateRequest,
    unmatched: bool,
) -> None:
    extraction_model.custom_output_args = {
        "suggestions": [
            {
                "requirement": "State NED license",
                "proposed_status": "Outstanding",
                "supporting_text": "Waiting on NED license.",
            }
        ]
        if unmatched
        else []
    }
    response = client.post(
        "/updates/analyze", json=update_request.model_dump(mode="json")
    )
    assert response.status_code == 200
    assert response.json()["suggestions"] == []
    assert "insufficient information" in response.json()["message"].lower()


def test_inferred_date_metadata(
    client: TestClient,
    extraction_model: TestModel,
    update_request: AnalyzeUpdateRequest,
) -> None:
    extraction_model.custom_output_args = {
        "suggestions": [
            {
                "requirement": "Drug screening",
                "proposed_status": "Scheduled",
                "supporting_text": "scheduled on the 18th",
                "date": {"text": "on the 18th", "day": 18},
            }
        ]
    }
    response = client.post(
        "/updates/analyze", json=update_request.model_dump(mode="json")
    )
    assert response.status_code == 200
    change = response.json()["suggestions"][0]
    assert change["proposed_date"] == "2026-12-18"
    assert change["date_text"] == "on the 18th"
    assert change["date_inferred"] is True
    assert change["date_requires_confirmation"] is True
    assert "2027-01-15" in change["date_explanation"]


@pytest.mark.parametrize("explicit", [False, True])
def test_dates_without_start(
    client: TestClient,
    extraction_model: TestModel,
    update_request: AnalyzeUpdateRequest,
    explicit: bool,
) -> None:
    update_request.provider.proposed_start_date = None
    mentioned = {"text": "October 22", "month": 10, "day": 22}
    if explicit:
        mentioned.update(text="October 22, 2026", year=2026)
    extraction_model.custom_output_args = {
        "suggestions": [
            {
                "requirement": "Drug screening",
                "proposed_status": "Scheduled",
                "supporting_text": "Scheduled",
                "date": mentioned,
            }
        ]
    }
    response = client.post(
        "/updates/analyze", json=update_request.model_dump(mode="json")
    )
    assert response.status_code == 200
    data = response.json()
    assert data["suggestions"][0]["proposed_date"] == (
        "2026-10-22" if explicit else None
    )
    assert data["suggestions"][0]["date_requires_confirmation"] is False
    assert bool(data["ambiguities"]) is not explicit


@pytest.mark.parametrize("scheduled", [False, True])
def test_missing_date_warning(
    client: TestClient,
    extraction_model: TestModel,
    update_request: AnalyzeUpdateRequest,
    scheduled: bool,
) -> None:
    extraction_model.custom_output_args = {
        "suggestions": [
            {
                "requirement": "Drug screening"
                if scheduled
                else "Hawaii dental license",
                "proposed_status": "Scheduled" if scheduled else "Received",
                "supporting_text": "Synthetic update.",
            }
        ]
    }
    response = client.post(
        "/updates/analyze", json=update_request.model_dump(mode="json")
    )
    assert response.status_code == 200
    assert len(response.json()["suggestions"]) == 1
    assert bool(response.json()["ambiguities"]) is scheduled


@pytest.mark.parametrize(
    "error,status",
    [
        (ModelHTTPError(503, "synthetic-model", body="synthetic-secret"), 502),
        (UnexpectedModelBehavior("synthetic-secret"), 502),
        (TimeoutError("synthetic-secret"), 504),
        (ModelTimeoutError("synthetic-model", "synthetic-secret"), 504),
        (ModelConnectionError("synthetic-model", "synthetic-secret"), 502),
    ],
)
def test_model_errors(
    client: TestClient,
    update_request: AnalyzeUpdateRequest,
    monkeypatch: pytest.MonkeyPatch,
    error: Exception,
    status: int,
) -> None:
    updates = importlib.import_module("app.updates")

    async def fail(*args: object, **kwargs: object) -> None:
        raise error

    monkeypatch.setattr(updates, "extract_update", fail)
    response = client.post(
        "/updates/analyze", json=update_request.model_dump(mode="json")
    )
    assert response.status_code == status
    assert "synthetic-secret" not in response.text
    assert "suggestions" not in response.json()


def test_missing_configuration(
    monkeypatch: pytest.MonkeyPatch,
    update_request: AnalyzeUpdateRequest,
) -> None:
    for name in ("LLM_API_TOKEN", "LLM_API_GATEWAY", "LLM_MODEL"):
        monkeypatch.delenv(name, raising=False)
    with TestClient(main.app) as client:
        assert client.get("/").status_code == 200
        response = client.post(
            "/updates/analyze", json=update_request.model_dump(mode="json")
        )
    assert response.status_code == 503
    assert "suggestions" not in response.json()


def test_context_unchanged(update_request: AnalyzeUpdateRequest) -> None:
    updates = importlib.import_module("app.updates")
    before = update_request.model_dump()
    agent = build_agent(
        TestModel(
            custom_output_args={
                "suggestions": [
                    {
                        "requirement": "Hawaii dental license",
                        "proposed_status": "Received",
                        "supporting_text": "License received.",
                    }
                ]
            }
        )
    )
    result = asyncio.run(updates.process_update(update_request, agent))
    assert result.suggestions[0].proposed_status == "Received"
    assert update_request.model_dump() == before


def test_invalid_model_date_keeps_suggestion_with_warning(
    client: TestClient,
    extraction_model: TestModel,
    update_request: AnalyzeUpdateRequest,
) -> None:
    extraction_model.custom_output_args = {
        "suggestions": [
            {
                "requirement": "Drug screening",
                "proposed_status": "Scheduled",
                "supporting_text": "Scheduled for January 1 in an invalid year.",
                "date": {
                    "text": "January 1 in an invalid year",
                    "year": 10**40,
                    "month": 1,
                    "day": 1,
                },
            }
        ]
    }
    response = client.post(
        "/updates/analyze", json=update_request.model_dump(mode="json")
    )
    assert response.status_code == 200
    assert len(response.json()["suggestions"]) == 1
    assert response.json()["suggestions"][0]["proposed_date"] is None
    assert response.json()["ambiguities"]


def test_invalid_gateway_returns_safe_configuration_error(
    monkeypatch: pytest.MonkeyPatch, update_request: AnalyzeUpdateRequest
) -> None:
    monkeypatch.setenv("LLM_API_TOKEN", "synthetic-secret")
    monkeypatch.setenv("LLM_API_GATEWAY", "https://example.invalid:abc/v1")
    monkeypatch.setenv("LLM_MODEL", "synthetic-model")
    with TestClient(main.app, raise_server_exceptions=False) as client:
        response = client.post(
            "/updates/analyze", json=update_request.model_dump(mode="json")
        )
    assert response.status_code == 503
    assert "synthetic-secret" not in response.text
    assert "example.invalid" not in response.text
