"""Minimal checks for the page and update endpoint contracts."""

import re
from uuid import uuid4

from fastapi.testclient import TestClient
from pydantic_ai.models import override_allow_model_requests

from app.main import app


def test_page_loads_with_a_form() -> None:
    with override_allow_model_requests(False), TestClient(app) as client:
        response = client.get("/")

    assert response.status_code == 200
    assert re.search(r"<form\b", response.text, re.IGNORECASE) is not None


def test_update_endpoint_returns_declared_top_level_fields(
    client: TestClient, seeded_provider
) -> None:
    request = {
        "provider_id": str(seeded_provider.id),
        "request_id": str(uuid4()),
        "update_text": "Hawaii dental license received.",
    }

    response = client.post("/updates/analyze", json=request)

    assert response.status_code == 200
    saved = response.json()
    assert saved["provider_id"] == str(seeded_provider.id)
    assert saved["processing_state"] == "completed"
    assert saved["update_text"] == request["update_text"]
    assert client.get(f"/updates/{saved['id']}").json() == saved
