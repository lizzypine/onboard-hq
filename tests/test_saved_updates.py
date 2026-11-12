"""Saved extraction must be idempotent, inspectable, and independent of review."""

import asyncio
import importlib
import threading
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import psycopg
import pytest
from fastapi.testclient import TestClient

from app import main
from tests.database import configured_test_url


def payload(provider):
    return {
        "provider_id": str(provider.id),
        "request_id": str(uuid4()),
        "update_text": "Drug screening completed.",
    }


@pytest.fixture
def completed_model(extraction_model):
    extraction_model.custom_output_args = {
        "suggestions": [
            {
                "requirement": "Drug screening",
                "proposed_status": "Completed",
                "supporting_text": "Drug screening completed.",
            }
        ],
        "ambiguities": [],
    }
    return extraction_model


def test_submission_persists_evidence_without_changing_checklist(
    client, seeded_provider, completed_model
):
    response = client.post("/updates/analyze", json=payload(seeded_provider))
    assert response.status_code == 200
    saved = response.json()
    assert saved["processing_state"] == "completed"
    assert saved["update_text"] == "Drug screening completed."
    assert saved["suggestions"][0]["proposed_status"] == "Completed"
    assert saved["suggestions"][0]["decision"] is None
    assert client.get(f"/updates/{saved['id']}").json() == saved
    requirements = client.get(f"/providers/{seeded_provider.id}").json()["requirements"]
    assert (
        next(r for r in requirements if r["name"] == "Drug screening")["status"]
        == "Scheduled"
    )


def test_identical_retry_returns_same_saved_result(
    client, seeded_provider, completed_model, monkeypatch
):
    updates = importlib.import_module("app.updates")
    original = updates.extract_update
    calls = []

    async def counted(*args, **kwargs):
        calls.append(1)
        return await original(*args, **kwargs)

    monkeypatch.setattr(updates, "extract_update", counted)
    body = payload(seeded_provider)
    first = client.post("/updates/analyze", json=body)
    second = client.post("/updates/analyze", json=body)
    assert first.status_code == second.status_code == 200
    assert second.json() == first.json()
    assert len(calls) == 1


@pytest.mark.parametrize(
    "field,value", [("update_text", "Different message"), ("provider_id", str(uuid4()))]
)
def test_request_id_cannot_be_reused_for_different_input(
    client, seeded_provider, field, value
):
    body = payload(seeded_provider)
    assert client.post("/updates/analyze", json=body).status_code == 200
    assert (
        client.post("/updates/analyze", json={**body, field: value}).status_code == 409
    )


def test_browser_cannot_supply_trusted_provider_context(client, seeded_provider):
    body = {**payload(seeded_provider), "provider": {"requirements": []}}
    assert client.post("/updates/analyze", json=body).status_code == 422


def test_processing_state_is_visible_and_no_database_transaction_spans_model_work(
    client, seeded_provider, completed_model, monkeypatch
):
    updates = importlib.import_module("app.updates")
    original = updates.extract_update
    started, release = threading.Event(), threading.Event()

    async def paused(*args, **kwargs):
        started.set()
        assert await asyncio.to_thread(release.wait, 10)
        return await original(*args, **kwargs)

    monkeypatch.setattr(updates, "extract_update", paused)
    body = payload(seeded_provider)
    with ThreadPoolExecutor(max_workers=1) as workers:
        future = workers.submit(client.post, "/updates/analyze", json=body)
        try:
            assert started.wait(10)
            retry = client.post("/updates/analyze", json=body)
            assert retry.status_code == 409
            saved = client.get(f"/providers/{seeded_provider.id}/updates").json()
            assert len(saved) == 1
            assert saved[0]["processing_state"] == "processing"
            assert saved[0]["suggestions"] == []
            with psycopg.connect(configured_test_url()) as conn:
                assert conn.execute(
                    "SELECT count(*) FROM pg_stat_activity WHERE datname=current_database() AND state='idle in transaction'"
                ).fetchone() == (0,)
                conn.execute("SELECT id FROM requirements FOR UPDATE NOWAIT")
        finally:
            release.set()
        assert future.result(timeout=10).status_code == 200


def test_model_failure_is_saved_and_not_retried_by_request_id(
    client, seeded_provider, monkeypatch
):
    updates = importlib.import_module("app.updates")
    calls = []

    async def fail(*args, **kwargs):
        calls.append(1)
        raise TimeoutError("sentinel-secret")

    monkeypatch.setattr(updates, "extract_update", fail)
    body = payload(seeded_provider)
    first = client.post("/updates/analyze", json=body)
    second = client.post("/updates/analyze", json=body)
    assert first.status_code == second.status_code == 504
    assert len(calls) == 1
    assert "sentinel-secret" not in first.text
    saved = client.get(f"/providers/{seeded_provider.id}/updates").json()[0]
    assert saved["processing_state"] == "failed"
    assert saved["failure_category"] == "timeout"
    assert saved["suggestions"] == []


def test_completed_history_survives_another_app_instance(
    client, seeded_provider, completed_model, db_url
):
    saved = client.post("/updates/analyze", json=payload(seeded_provider))
    assert saved.status_code == 200
    with TestClient(main.create_app()) as fresh:
        assert fresh.get(f"/updates/{saved.json()['id']}").json() == saved.json()


def test_invalid_structured_status_cannot_become_review_candidate(
    client, seeded_provider, extraction_model
):
    extraction_model.custom_output_args = {
        "suggestions": [
            {
                "requirement": "Drug screening",
                "proposed_status": "  ",
                "supporting_text": "Synthetic",
            }
        ]
    }
    assert (
        client.post("/updates/analyze", json=payload(seeded_provider)).status_code
        == 502
    )
    saved = client.get(f"/providers/{seeded_provider.id}/updates").json()[0]
    assert saved["processing_state"] == "failed"
    assert saved["suggestions"] == []


def test_failed_suggestion_insert_rolls_back_candidates_and_leaves_unfinished_update(
    client, seeded_provider, completed_model
):
    url = configured_test_url()
    with psycopg.connect(url) as conn:
        conn.execute(
            "CREATE FUNCTION onboard_test_block_suggestion() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'sentinel-secret'; END $$"
        )
        conn.execute(
            "CREATE TRIGGER onboard_test_fail BEFORE INSERT ON suggestions FOR EACH ROW EXECUTE FUNCTION onboard_test_block_suggestion()"
        )
    try:
        response = client.post("/updates/analyze", json=payload(seeded_provider))
        assert response.status_code == 503
        assert "sentinel-secret" not in response.text
        saved = client.get(f"/providers/{seeded_provider.id}/updates").json()[0]
        assert saved["processing_state"] == "processing"
        assert saved["suggestions"] == []
    finally:
        with psycopg.connect(url) as conn:
            conn.execute("DROP TRIGGER onboard_test_fail ON suggestions")
            conn.execute("DROP FUNCTION onboard_test_block_suggestion()")
