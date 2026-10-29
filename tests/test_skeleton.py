"""Minimal checks for the page and update endpoint contracts."""

import re

from fastapi.testclient import TestClient
from pydantic_ai.models import override_allow_model_requests

from app.agent import AnalyzeUpdateResponse
from app.main import app


def test_page_loads_with_a_form() -> None:
    with override_allow_model_requests(False), TestClient(app) as client:
        response = client.get("/")

    assert response.status_code == 200
    assert re.search(r"<form\b", response.text, re.IGNORECASE) is not None


def test_update_endpoint_returns_declared_top_level_fields(client: TestClient) -> None:
    request = {
        "provider": {
            "provider_id": "kekoa-ejemplo",
            "name": "Dr. Kekoa Ejemplo",
            "provider_type": "Dentist",
            "proposed_start_date": "2026-12-01",
            "requirements": [
                {
                    "name": "Hawaii dental license",
                    "status": "Outstanding",
                    "deadline": None,
                }
            ],
        },
        "update_text": "Hawaii dental license received.",
    }

    response = client.post("/updates/analyze", json=request)

    assert response.status_code == 200
    assert set(response.json()) == set(AnalyzeUpdateResponse.model_fields)
