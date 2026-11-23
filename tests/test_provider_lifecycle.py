"""Archive/restore changes lifecycle only, preserving saved work and provenance."""

from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import psycopg
import pytest
from fastapi.testclient import TestClient

from app import main
from tests.database import configured_test_url, disposable_database
from tests.fixtures.current_database import configure_catalog
from tests.test_checklist_edits import analyze, edit_body, endpoint, save
from tests.test_provider_additions import MANAGER, create, extra, reviewed_body

TABLES = (
    "provider_types",
    "checklist_templates",
    "requirement_definitions",
    "template_requirements",
    "providers",
    "requirements",
    "updates",
    "update_requirement_snapshots",
    "update_ambiguities",
    "suggestions",
    "review_decisions",
    "checklist_edits",
)


def graph_snapshot():
    with psycopg.connect(configured_test_url()) as conn:
        return {
            table: conn.execute(
                f"SELECT to_jsonb(t)-'archived_at' FROM {table} t ORDER BY 1"
            ).fetchall()
            for table in TABLES
        }


def change(client, provider_id, action):
    response = client.post(f"/providers/{provider_id}/{action}", headers=MANAGER)
    assert response.status_code == 200, response.text
    return response.json()


@pytest.mark.parametrize("action", ["archive", "restore"])
@pytest.mark.parametrize("headers", [{}, {"X-Demo-Role": "proposer"}])
def test_lifecycle_requires_manager_without_writing(
    client, seeded_provider, action, headers
):
    before = client.get(f"/providers/{seeded_provider.id}").json()
    response = client.post(f"/providers/{seeded_provider.id}/{action}", headers=headers)
    assert response.status_code == 403
    assert "Manager" in response.json()["detail"]
    assert client.get(f"/providers/{seeded_provider.id}").json() == before


@pytest.mark.parametrize("action", ["archive", "restore"])
def test_invalid_or_missing_lifecycle_target_never_writes(
    client, seeded_provider, action
):
    before = client.get(f"/providers/{seeded_provider.id}").json()
    for identity, status in [(0, 422), (-1, 422), ("bad", 422), (999999999, 404)]:
        assert (
            client.post(f"/providers/{identity}/{action}", headers=MANAGER).status_code
            == status
        )
    assert (
        client.post(
            f"/providers/{seeded_provider.id}/{action}",
            headers={"X-Demo-Role": "admin"},
        ).status_code
        == 422
    )
    assert client.get(f"/providers/{seeded_provider.id}").json() == before


def test_archive_restore_preserves_entire_graph_and_original_checklist(
    client, seeded_provider, extraction_model
):
    saved = create(client, reviewed_body(client, [extra(deadline="2026-12-10")]))
    identity = saved["id"]
    suggestion = analyze(client, extraction_model, identity)
    assert (
        client.post(
            f"/suggestions/{suggestion['id']}/review",
            json={"action": "approve"},
            headers=MANAGER,
        ).status_code
        == 200
    )
    custom = next(r for r in saved["requirements"] if r["name"] == "Orientation")
    save(client, identity, custom, edit_body(custom, status="Scheduled"))
    pending = analyze(client, extraction_model, identity)
    configure_catalog("Dentist", ["Future standard"], version=2)
    before = client.get(f"/providers/{identity}").json()
    graph = graph_snapshot()
    archived = change(client, identity, "archive")
    assert archived["archived_at"] is not None
    assert {**archived, "archived_at": None} == before
    assert client.get("/providers").json()[0]["id"] == seeded_provider.id
    assert [p["id"] for p in client.get("/providers?state=archived").json()] == [
        identity
    ]
    assert len(client.get("/providers?state=all").json()) == 2
    assert graph_snapshot() == graph
    assert client.get(f"/providers/{identity}/dashboard").status_code == 200
    assert client.get(f"/providers/{identity}/updates").status_code == 200
    assert (
        client.post(
            "/updates/analyze",
            json={
                "provider_id": identity,
                "request_id": str(uuid4()),
                "update_text": "Synthetic change",
            },
        ).status_code
        == 409
    )
    assert (
        client.post(
            f"/suggestions/{pending['id']}/review",
            json={"action": "approve"},
            headers=MANAGER,
        ).status_code
        == 409
    )
    current = next(r for r in before["requirements"] if r["name"] == "Orientation")
    assert (
        client.post(
            endpoint(identity, current["id"]), json=edit_body(current), headers=MANAGER
        ).status_code
        == 409
    )
    assert graph_snapshot() == graph
    restored = change(client, identity, "restore")
    assert restored == before
    assert graph_snapshot() == graph
    assert client.get("/providers?state=archived").json() == []
    assert (
        client.post(
            f"/suggestions/{pending['id']}/review",
            json={"action": "approve"},
            headers=MANAGER,
        ).status_code
        == 200
    )
    assert client.get(f"/providers/{identity}").json()["template_version"] == 1


@pytest.mark.parametrize("action", ["archive", "restore"])
def test_repeated_and_concurrent_desired_states_do_not_reset_progress(
    client, seeded_provider, action
):
    if action == "restore":
        change(client, seeded_provider.id, "archive")
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(
            executor.map(lambda _: change(client, seeded_provider.id, action), range(2))
        )
    assert results[0] == results[1]
    assert change(client, seeded_provider.id, action) == results[0]
    assert (
        results[0]["requirements"]
        == seeded_provider.model_dump(mode="json")["requirements"]
    )


@pytest.mark.parametrize("action", ["archive", "restore"])
def test_lifecycle_errors_hide_database_details(monkeypatch, action):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with TestClient(main.create_app()) as client:
        response = client.post(f"/providers/1/{action}", headers=MANAGER)
        assert response.status_code == 503
        assert response.json()["detail"] == "Database is not configured."
    with disposable_database() as url:
        monkeypatch.setenv("DATABASE_URL", url)
        with TestClient(main.create_app()) as client:
            response = client.post(f"/providers/1/{action}", headers=MANAGER)
            assert response.status_code == 503
            assert (
                response.json()["detail"]
                == "Database is unavailable. Check configuration and migrations."
            )


def test_lifecycle_role_rule_is_pure():
    from app.rules.provider_state import (
        ProviderLifecycleForbidden,
        require_lifecycle_manager,
    )

    assert require_lifecycle_manager("manager") is None
    with pytest.raises(ProviderLifecycleForbidden):
        require_lifecycle_manager("proposer")
