"""Creation API uses atomic, independent saved checklists and retry identities."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import psycopg
import pytest
from fastapi.testclient import TestClient

from app import main
from app.database import DatabaseUnavailable, create_pool
from app.provider_models import CreateProviderRequest
from app.repository import providers as provider_repository
from app.repository.providers import ProviderRepository
from app.seed import DENTIST_ID, INITIAL_STATUSES
from tests.database import configured_test_url, disposable_database

MANAGER = {"X-Demo-Role": "manager"}


def body(**changes):
    return {
        "id": str(uuid4()),
        "name": "Dr. Avery Example",
        "provider_type_id": str(DENTIST_ID),
        "proposed_start_date": "2027-01-15",
        **changes,
    }


def create(client, payload=None):
    response = client.post("/providers", json=payload or body(), headers=MANAGER)
    assert response.status_code == 201, response.text
    return response.json()


def counts():
    with psycopg.connect(configured_test_url()) as conn:
        return tuple(
            conn.execute(f"SELECT count(*) FROM {name}").fetchone()[0]
            for name in (
                "providers",
                "requirements",
                "updates",
                "suggestions",
                "review_decisions",
            )
        )


def test_catalog_and_creation_copy_the_selected_template(client, seeded_provider):
    original = client.get(f"/providers/{seeded_provider.id}").json()
    catalog = client.get("/provider-types")
    assert catalog.status_code == 200
    assert catalog.json() == [
        {
            "id": str(DENTIST_ID),
            "name": "Dentist",
            "requirements": sorted(INITIAL_STATUSES),
        }
    ]
    result = create(client)
    assert result["name"] == "Dr. Avery Example"
    assert result["provider_type"] == "Dentist"
    assert result["proposed_start_date"] == "2027-01-15"
    assert [r["name"] for r in result["requirements"]] == sorted(INITIAL_STATUSES)
    assert all(
        r["status"] == "Outstanding"
        and r["scheduled_date"] is None
        and r["deadline"] is None
        and r["version"] == 0
        and r["source_template_id"]
        for r in result["requirements"]
    )
    assert len({r["id"] for r in result["requirements"]}) == 5
    assert all(r["provider_id"] == result["id"] for r in result["requirements"])
    assert client.get(f"/providers/{seeded_provider.id}").json() == original
    assert client.get(f"/providers/{result['id']}/updates").json() == []
    dashboard = client.get(f"/providers/{result['id']}/dashboard").json()
    assert dashboard["monitoring"]["counts"] == {
        "total": 5,
        "finished": 0,
        "remaining": 5,
        "overdue": 0,
        "needs_review": 0,
    }
    assert counts() == (2, 10, 0, 0, 0)


@pytest.mark.parametrize("headers", [{}, {"X-Demo-Role": "proposer"}])
def test_creation_rejects_unprivileged_roles_without_writes(client, headers):
    before = counts()
    assert client.post("/providers", json=body(), headers=headers).status_code == 403
    assert counts() == before


@pytest.mark.parametrize(
    "changes",
    [
        {"name": " "},
        {"id": "bad"},
        {"provider_type_id": "bad"},
        {"proposed_start_date": "2026-02-30"},
        {"requirements": []},
        {"status": "Signed"},
    ],
)
def test_creation_input_errors_make_no_records(client, changes):
    before = counts()
    assert (
        client.post("/providers", json=body(**changes), headers=MANAGER).status_code
        == 422
    )
    assert counts() == before


def test_missing_and_empty_types_do_not_create_partial_providers(client):
    empty_id = uuid4()
    with psycopg.connect(configured_test_url()) as conn:
        conn.execute(
            "INSERT INTO provider_types VALUES (%s,'Synthetic Empty')", (empty_id,)
        )
    before = counts()
    assert (
        client.post(
            "/providers", json=body(provider_type_id=str(uuid4())), headers=MANAGER
        ).status_code
        == 404
    )
    assert (
        client.post(
            "/providers", json=body(provider_type_id=str(empty_id)), headers=MANAGER
        ).status_code
        == 409
    )
    assert all(t["id"] != str(empty_id) for t in client.get("/provider-types").json())
    assert counts() == before


def test_other_synthetic_type_copies_only_its_own_requirements(client):
    type_id, template_id = uuid4(), uuid4()
    with psycopg.connect(configured_test_url()) as conn:
        conn.execute(
            "INSERT INTO provider_types VALUES (%s,'Synthetic Other')", (type_id,)
        )
        conn.execute(
            "INSERT INTO requirement_templates VALUES (%s,%s,'Synthetic requirement')",
            (template_id, type_id),
        )
    result = create(
        client, body(provider_type_id=str(type_id), proposed_start_date=None)
    )
    assert result["proposed_start_date"] is None
    assert len(result["requirements"]) == 1
    assert result["requirements"][0]["name"] == "Synthetic requirement"
    assert result["requirements"][0]["source_template_id"] == str(template_id)
    assert (
        client.get(f"/providers/{result['id']}/dashboard").json()["monitoring"][
            "counts"
        ]["needs_review"]
        == 1
    )


def test_identical_and_concurrent_retries_create_once(client):
    payload = body()
    with ThreadPoolExecutor(max_workers=2) as executor:
        responses = list(executor.map(lambda _: create(client, payload), range(2)))
    assert responses[0] == responses[1]
    assert create(client, payload) == responses[0]
    assert counts() == (2, 10, 0, 0, 0)


@pytest.mark.parametrize(
    "changes",
    [
        {"name": "Different Example"},
        {"provider_type_id": str(uuid4())},
        {"proposed_start_date": None},
    ],
)
def test_reused_creation_id_cannot_change_profile(client, changes):
    payload = body()
    original = create(client, payload)
    assert (
        client.post(
            "/providers", json={**payload, **changes}, headers=MANAGER
        ).status_code
        == 409
    )
    assert client.get(f"/providers/{original['id']}").json() == original
    assert counts() == (2, 10, 0, 0, 0)


def test_creation_retry_preserves_approved_progress_and_template_snapshot(
    client, extraction_model, seeded_provider
):
    payload = body()
    original = create(client, payload)
    extraction_model.custom_output_args = {
        "suggestions": [
            {
                "requirement": "Drug screening",
                "proposed_status": "Completed",
                "supporting_text": "Drug screening completed.",
            }
        ]
    }
    analysis = client.post(
        "/updates/analyze",
        json={
            "request_id": str(uuid4()),
            "provider_id": original["id"],
            "update_text": "Drug screening completed.",
        },
    )
    assert analysis.status_code == 200
    assert analysis.json()["provider_snapshot"]["id"] == original["id"]
    suggestion = analysis.json()["suggestions"][0]
    assert (
        client.post(
            f"/suggestions/{suggestion['id']}/review",
            json={"action": "approve"},
            headers=MANAGER,
        ).status_code
        == 200
    )
    saved = client.get(f"/providers/{original['id']}").json()
    with psycopg.connect(configured_test_url()) as conn:
        conn.execute(
            "INSERT INTO requirement_templates VALUES (%s,%s,'Later synthetic requirement')",
            (uuid4(), DENTIST_ID),
        )
        conn.execute(
            "UPDATE requirement_templates SET name='Renamed template' WHERE provider_type_id=%s AND name='Offer letter'",
            (DENTIST_ID,),
        )
    assert create(client, payload) == saved
    newer = create(client)
    assert len(newer["requirements"]) == 6
    assert "Renamed template" in {r["name"] for r in newer["requirements"]}
    assert "Offer letter" in {r["name"] for r in saved["requirements"]}
    assert (
        next(r for r in saved["requirements"] if r["name"] == "Drug screening")[
            "status"
        ]
        == "Completed"
    )
    assert client.get(f"/providers/{seeded_provider.id}/updates").json() == []
    assert (
        next(
            r
            for r in client.get(f"/providers/{seeded_provider.id}").json()[
                "requirements"
            ]
            if r["name"] == "Drug screening"
        )["status"]
        == "Scheduled"
    )


def test_creation_rolls_back_after_a_partial_checklist_insert(
    db_url, seeded_provider, monkeypatch
):
    collision = uuid4()
    monkeypatch.setattr(provider_repository, "uuid5", lambda *_: collision)
    request = CreateProviderRequest.model_validate(body())

    async def attempt():
        async with create_pool(db_url) as pool:
            with pytest.raises(DatabaseUnavailable):
                await ProviderRepository(pool).create_from_template(
                    request, initial_status="Outstanding"
                )

    before = counts()
    asyncio.run(attempt())
    assert counts() == before


@pytest.mark.parametrize("path", ["/provider-types", "/providers"])
def test_creation_endpoints_report_missing_configuration_safely(monkeypatch, path):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with TestClient(main.create_app()) as test_client:
        result = (
            test_client.get(path)
            if path == "/provider-types"
            else test_client.post(path, json=body(), headers=MANAGER)
        )
    assert result.status_code == 503
    assert "postgresql://" not in result.text


def test_creation_reports_missing_schema_safely(monkeypatch):
    with disposable_database() as url:
        monkeypatch.setenv("DATABASE_URL", url)
        with TestClient(main.create_app()) as test_client:
            result = test_client.post("/providers", json=body(), headers=MANAGER)
            assert result.status_code == 503
            assert "postgresql://" not in result.text
            assert "UndefinedTable" not in result.text
