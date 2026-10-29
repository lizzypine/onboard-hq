"""Extraction uses structured context without inferring unstated dates."""

import asyncio

import pytest
from pydantic_ai import capture_run_messages
from pydantic_ai.messages import ModelMessagesTypeAdapter
from pydantic_ai.models.test import TestModel

from app import agent as agent_module
from app.agent import AnalyzeUpdateRequest


def test_extracts_stated_components_without_inference(
    update_request: AnalyzeUpdateRequest,
) -> None:
    model = TestModel(
        custom_output_args={
            "suggestions": [
                {
                    "requirement": "Drug screening",
                    "proposed_status": "Scheduled",
                    "supporting_text": "scheduled on the 18th",
                    "date": {"text": "on the 18th", "day": 18},
                }
            ],
            "ambiguities": [],
        }
    )
    agent = agent_module.build_agent(model)
    result = asyncio.run(agent_module.extract_update(update_request, agent))
    assert result.suggestions[0].date is not None
    assert result.suggestions[0].date.day == 18
    assert result.suggestions[0].date.month is None
    assert result.suggestions[0].date.year is None


def test_empty_extraction(update_request: AnalyzeUpdateRequest) -> None:
    agent = agent_module.build_agent(TestModel(custom_output_args={"suggestions": []}))
    result = asyncio.run(agent_module.extract_update(update_request, agent))
    assert result.suggestions == []


@pytest.mark.parametrize("missing", ["LLM_API_TOKEN", "LLM_API_GATEWAY", "LLM_MODEL"])
def test_missing_configuration(missing: str, monkeypatch: pytest.MonkeyPatch) -> None:
    values = {
        "LLM_API_TOKEN": "synthetic-token",
        "LLM_API_GATEWAY": "https://gateway.example.invalid/v1",
        "LLM_MODEL": "synthetic-model",
    }
    for key, value in values.items():
        monkeypatch.setenv(key, value)
    monkeypatch.delenv(missing)
    with pytest.raises(agent_module.AgentConfigurationError) as exc:
        agent_module.build_agent()
    assert "synthetic-token" not in str(exc.value)


def test_injected_model_needs_no_configuration(
    monkeypatch: pytest.MonkeyPatch, update_request: AnalyzeUpdateRequest
) -> None:
    for key in ("LLM_API_TOKEN", "LLM_API_GATEWAY", "LLM_MODEL"):
        monkeypatch.delenv(key, raising=False)
    agent = agent_module.build_agent(TestModel(custom_output_args={"suggestions": []}))
    result = asyncio.run(agent_module.extract_update(update_request, agent))
    assert result.suggestions == []


def test_prompt_contains_context_without_credentials(
    monkeypatch: pytest.MonkeyPatch, update_request: AnalyzeUpdateRequest
) -> None:
    monkeypatch.setenv("LLM_API_TOKEN", "synthetic-secret-not-for-prompts")
    agent = agent_module.build_agent(TestModel(custom_output_args={"suggestions": []}))
    with capture_run_messages() as messages:
        asyncio.run(agent_module.extract_update(update_request, agent))
    captured = ModelMessagesTypeAdapter.dump_json(messages).decode()
    assert "Dr. Kekoa Ejemplo" in captured
    assert "Hawaii dental license" in captured
    assert "Outstanding" in captured
    assert update_request.update_text in captured
    assert "synthetic-secret-not-for-prompts" not in captured
