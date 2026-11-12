"""Dashboard reads use real saved records without writing monitoring state."""

from datetime import date
from uuid import uuid4

import psycopg
import pytest
from fastapi.testclient import TestClient
from psycopg import sql

from app import main
from app.monitoring import get_monitoring_date
from app.repository.providers import ProviderRepository
from tests.database import configured_test_url, disposable_database

AS_OF = date(2026, 11, 11)
MANAGER = {"X-Demo-Role": "manager"}


@pytest.fixture(autouse=True)
def fixed_monitoring_date(monkeypatch):
    monkeypatch.setitem(
        main.app.dependency_overrides, get_monitoring_date, lambda: AS_OF
    )


def dashboard(client, provider):
    response = client.get(f"/providers/{provider.id}/dashboard")
    assert response.status_code == 200
    return response.json()


def row_and_indicator(data, name):
    row = next(r for r in data["provider"]["requirements"] if r["name"] == name)
    indicator = next(
        r
        for r in data["monitoring"]["requirements"]
        if r["requirement_id"] == row["id"]
    )
    return row, indicator


def application_rows():
    tables = (
        "provider_types",
        "requirement_templates",
        "providers",
        "requirements",
        "updates",
        "suggestions",
        "review_decisions",
    )
    with psycopg.connect(configured_test_url()) as conn:
        return {
            name: conn.execute(
                sql.SQL("SELECT to_jsonb(t) FROM {} t ORDER BY id").format(
                    sql.Identifier(name)
                )
            ).fetchall()
            for name in tables
        }


def submit_change(client, provider, extraction_model):
    extraction_model.custom_output_args = {
        "suggestions": [
            {
                "requirement": "Drug screening",
                "proposed_status": "Completed",
                "supporting_text": "Drug screening completed.",
            }
        ]
    }
    response = client.post(
        "/updates/analyze",
        json={
            "provider_id": str(provider.id),
            "request_id": str(uuid4()),
            "update_text": "Drug screening completed.",
        },
    )
    assert response.status_code == 200
    return response.json()["suggestions"][0]


def test_dashboard_returns_saved_provider_and_seed_monitoring(client, seeded_provider):
    result = dashboard(client, seeded_provider)
    raw = client.get(f"/providers/{seeded_provider.id}").json()
    assert result["provider"] == raw
    assert "monitoring" not in raw
    assert "as_of_date" not in raw
    assert result["monitoring"]["as_of_date"] == "2026-11-11"
    assert result["monitoring"]["time_zone"] == "Pacific/Honolulu"
    assert [r["requirement_id"] for r in result["monitoring"]["requirements"]] == [
        r["id"] for r in raw["requirements"]
    ]
    assert result["monitoring"]["counts"] == {
        "total": 5,
        "finished": 2,
        "remaining": 3,
        "overdue": 0,
        "needs_review": 0,
    }


def test_browser_query_values_do_not_override_saved_monitoring(client, seeded_provider):
    response = client.get(
        f"/providers/{seeded_provider.id}/dashboard?as_of_date=1900-01-01&status=Completed"
    )
    assert response.status_code == 200
    result = response.json()
    row, indicator = row_and_indicator(result, "Drug screening")
    assert row["status"] == "Scheduled"
    assert indicator["completion"] == "outstanding"
    assert result["monitoring"]["as_of_date"] == "2026-11-11"
    assert result["monitoring"]["counts"]["finished"] == 2


def test_dashboard_uses_one_provider_and_date_snapshot(
    client, seeded_provider, monkeypatch
):
    original = ProviderRepository.get_provider
    reads = []
    clocks = []

    async def read_then_commit(repository, provider_id):
        captured = await original(repository, provider_id)
        reads.append(provider_id)
        if len(reads) == 1:
            async with repository.pool.connection() as conn:
                await conn.execute(
                    "UPDATE requirements SET status='Completed' WHERE provider_id=%s AND name='Drug screening'",
                    (provider_id,),
                )
        return captured

    def clock():
        clocks.append(True)
        return AS_OF if len(clocks) == 1 else date(2026, 11, 12)

    monkeypatch.setattr(ProviderRepository, "get_provider", read_then_commit)
    monkeypatch.setitem(main.app.dependency_overrides, get_monitoring_date, clock)
    first = dashboard(client, seeded_provider)
    row, indicator = row_and_indicator(first, "Drug screening")
    assert row["status"] == "Scheduled"
    assert indicator["completion"] == "outstanding"
    assert first["monitoring"]["counts"]["finished"] == 2
    assert first["monitoring"]["as_of_date"] == "2026-11-11"
    assert len(reads) == len(clocks) == 1
    second = dashboard(client, seeded_provider)
    row, indicator = row_and_indicator(second, "Drug screening")
    assert row["status"] == "Completed"
    assert indicator["completion"] == "finished"
    assert second["monitoring"]["counts"]["finished"] == 3
    assert second["monitoring"]["as_of_date"] == "2026-11-12"
    assert len(reads) == len(clocks) == 2


def test_dashboard_reads_do_not_modify_records_or_snapshots(
    client, seeded_provider, extraction_model
):
    submit_change(client, seeded_provider, extraction_model)
    before = application_rows()
    first = dashboard(client, seeded_provider)
    second = dashboard(client, seeded_provider)
    assert second == first
    assert application_rows() == before
    saved = client.get(f"/providers/{seeded_provider.id}/updates").json()[0]
    assert "monitoring" not in saved["provider_snapshot"]
    assert "as_of_date" not in saved["provider_snapshot"]


def test_unknown_type_does_not_adopt_dentist_rules(client):
    type_id, provider_id, requirement_id = uuid4(), uuid4(), uuid4()
    with psycopg.connect(configured_test_url()) as conn:
        conn.execute(
            "INSERT INTO provider_types(id,name) VALUES (%s,'Synthetic Other Type')",
            (type_id,),
        )
        conn.execute(
            "INSERT INTO providers(id,provider_type_id,name) VALUES (%s,%s,'Synthetic Other Provider')",
            (provider_id, type_id),
        )
        conn.execute(
            "INSERT INTO requirements(id,provider_id,provider_type_id,name,status,deadline) VALUES (%s,%s,%s,'Drug screening','Completed','2026-11-10')",
            (requirement_id, provider_id, type_id),
        )
    response = client.get(f"/providers/{provider_id}/dashboard")
    assert response.status_code == 200
    data = response.json()
    assert data["monitoring"]["requirements"][0]["completion"] == "needs_review"
    assert data["monitoring"]["requirements"][0]["deadline_state"] == "past"
    assert data["monitoring"]["counts"] == {
        "total": 1,
        "finished": 0,
        "remaining": 1,
        "overdue": 0,
        "needs_review": 1,
    }


def test_empty_checklist_returns_zero_counts(client, seeded_provider):
    with psycopg.connect(configured_test_url()) as conn:
        conn.execute(
            "DELETE FROM requirements WHERE provider_id=%s", (seeded_provider.id,)
        )
    result = dashboard(client, seeded_provider)
    assert result["provider"]["requirements"] == []
    assert result["monitoring"]["requirements"] == []
    assert result["monitoring"]["counts"] == {
        "total": 0,
        "finished": 0,
        "remaining": 0,
        "overdue": 0,
        "needs_review": 0,
    }


def test_dashboard_reports_missing_and_malformed_provider_ids(client):
    assert client.get(f"/providers/{uuid4()}/dashboard").status_code == 404
    assert client.get("/providers/not-a-uuid/dashboard").status_code == 422


def test_dashboard_reports_missing_configuration_safely(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with TestClient(main.create_app()) as test_client:
        assert test_client.get("/").status_code == 200
        result = test_client.get(f"/providers/{uuid4()}/dashboard")
        assert result.status_code == 503
        assert "postgresql://" not in result.text


def test_dashboard_reports_missing_schema_safely(monkeypatch):
    with disposable_database() as url:
        monkeypatch.setenv("DATABASE_URL", url)
        with TestClient(main.create_app()) as test_client:
            result = test_client.get(f"/providers/{uuid4()}/dashboard")
            assert result.status_code == 503
            assert "postgresql://" not in result.text
            assert "UndefinedTable" not in result.text


@pytest.mark.parametrize(
    "name,status,deadline,completion,deadline_state,finished,overdue,uncertain",
    [
        ("Offer letter", "Signed", "2026-11-10", "finished", "past", 2, 0, 0),
        (
            "Drug screening",
            "Scheduled",
            "2026-11-18",
            "outstanding",
            "upcoming",
            2,
            0,
            0,
        ),
        ("Drug screening", "Completed", "2026-11-10", "finished", "past", 3, 0, 0),
        (
            "Insurance credentialing",
            "Incomplete",
            "2026-11-10",
            "outstanding",
            "past",
            2,
            1,
            0,
        ),
        (
            "Drug screening",
            "Results being checked",
            "2026-11-10",
            "needs_review",
            "past",
            2,
            0,
            1,
        ),
        (
            "Drug screening",
            "Scheduled",
            "2026-11-11",
            "outstanding",
            "due_today",
            2,
            0,
            0,
        ),
        ("Drug screening", "Scheduled", None, "outstanding", "not_set", 2, 0, 0),
    ],
)
def test_dashboard_monitors_saved_status_and_deadline_cases(
    client,
    seeded_provider,
    name,
    status,
    deadline,
    completion,
    deadline_state,
    finished,
    overdue,
    uncertain,
):
    with psycopg.connect(configured_test_url()) as conn:
        conn.execute(
            "UPDATE requirements SET status=%s,deadline=%s WHERE provider_id=%s AND name=%s",
            (status, deadline, seeded_provider.id, name),
        )
    result = dashboard(client, seeded_provider)
    row, indicator = row_and_indicator(result, name)
    assert row["status"] == status
    assert row["deadline"] == deadline
    assert indicator["completion"] == completion
    assert indicator["deadline_state"] == deadline_state
    assert result["monitoring"]["counts"] == {
        "total": 5,
        "finished": finished,
        "remaining": 5 - finished,
        "overdue": overdue,
        "needs_review": uncertain,
    }


def test_monitoring_changes_only_after_approved_status_updates(
    client, seeded_provider, extraction_model
):
    with psycopg.connect(configured_test_url()) as conn:
        conn.execute(
            "UPDATE requirements SET deadline='2026-11-10' WHERE provider_id=%s AND name='Drug screening'",
            (seeded_provider.id,),
        )
    initial = dashboard(client, seeded_provider)["monitoring"]
    assert initial["counts"]["overdue"] == 1
    first = submit_change(client, seeded_provider, extraction_model)
    assert dashboard(client, seeded_provider)["monitoring"] == initial
    rejected = client.post(
        f"/suggestions/{first['id']}/review", json={"action": "reject"}, headers=MANAGER
    )
    assert rejected.status_code == 200
    assert dashboard(client, seeded_provider)["monitoring"] == initial
    second = submit_change(client, seeded_provider, extraction_model)
    approved = client.post(
        f"/suggestions/{second['id']}/review",
        json={"action": "approve"},
        headers=MANAGER,
    )
    assert approved.status_code == 200
    result = dashboard(client, seeded_provider)
    assert row_and_indicator(result, "Drug screening")[1]["completion"] == "finished"
    assert result["monitoring"]["counts"]["finished"] == 3
    assert result["monitoring"]["counts"]["overdue"] == 0
    third = submit_change(client, seeded_provider, extraction_model)
    corrected = client.post(
        f"/suggestions/{third['id']}/review",
        json={"action": "correct", "corrected_status": "Incomplete"},
        headers=MANAGER,
    )
    assert corrected.status_code == 200
    result = dashboard(client, seeded_provider)
    row, indicator = row_and_indicator(result, "Drug screening")
    assert row["status"] == "Incomplete"
    assert row["deadline"] == "2026-11-10"
    assert row["version"] == 2
    assert indicator["completion"] == "outstanding"
    assert result["monitoring"]["counts"]["finished"] == 2
    assert result["monitoring"]["counts"]["remaining"] == 3
    assert result["monitoring"]["counts"]["overdue"] == 1
    saved = client.get(f"/providers/{seeded_provider.id}/updates").json()
    assert len(saved) == 3
    assert all(
        update["suggestions"][0]["proposed_status"] == "Completed" for update in saved
    )
    assert "monitoring" not in saved[0]["provider_snapshot"]
