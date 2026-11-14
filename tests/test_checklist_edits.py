"""Atomic manual edits, audit evidence, retry identities, and shared row versions."""

from concurrent.futures import ThreadPoolExecutor
from datetime import date
from uuid import uuid4

import psycopg
import pytest
from fastapi.testclient import TestClient

from app import main
from app.seed import DENTIST_ID
from tests.database import configured_test_url, disposable_database

MANAGER = {"X-Demo-Role": "manager"}


def requirement(client, provider_id, name="Drug screening"):
    return next(
        r
        for r in client.get(f"/providers/{provider_id}").json()["requirements"]
        if r["name"] == name
    )


def edit_body(row, **changes):
    return {
        "id": str(uuid4()),
        "expected_version": row["version"],
        "status": "Completed",
        "scheduled_date": "2026-11-12",
        "deadline": "2026-11-20",
        **changes,
    }


def endpoint(provider_id, row_id):
    return f"/providers/{provider_id}/requirements/{row_id}/edits"


def history(client, provider_id):
    result = client.get(f"/providers/{provider_id}/checklist-edits")
    assert result.status_code == 200, result.text
    return result.json()


def save(client, provider_id, row, body=None):
    result = client.post(
        endpoint(provider_id, row["id"]), json=body or edit_body(row), headers=MANAGER
    )
    assert result.status_code == 201, result.text
    return result.json()


def analyze(client, extraction_model, provider_id):
    extraction_model.custom_output_args = {
        "suggestions": [
            {
                "requirement": "Drug screening",
                "proposed_status": "Completed",
                "supporting_text": "Drug screening completed.",
            }
        ]
    }
    result = client.post(
        "/updates/analyze",
        json={
            "request_id": str(uuid4()),
            "provider_id": str(provider_id),
            "update_text": "Drug screening completed.",
        },
    )
    assert result.status_code == 200
    return result.json()["suggestions"][0]


def test_manual_save_records_before_after_and_independent_provider(
    client, seeded_provider
):
    original = client.get(f"/providers/{seeded_provider.id}").json()
    new = client.post(
        "/providers",
        headers=MANAGER,
        json={
            "id": str(uuid4()),
            "name": "Dr. Avery Example",
            "provider_type_id": str(DENTIST_ID),
        },
    ).json()
    row = requirement(client, new["id"])
    saved = save(client, new["id"], row)
    assert saved["previous_status"] == "Outstanding"
    assert (
        saved["previous_scheduled_date"] is None and saved["previous_deadline"] is None
    )
    assert saved["applied_status"] == "Completed"
    assert (
        saved["applied_scheduled_date"] == "2026-11-12"
        and saved["applied_deadline"] == "2026-11-20"
    )
    assert saved["expected_version"] == 0 and saved["resulting_version"] == 1
    assert (
        saved["reviewer_role"] == "manager"
        and saved["requirement_name"] == "Drug screening"
    )
    assert saved["provider_id"] == new["id"] and saved["requirement_id"] == row["id"]
    assert saved["created_at"]
    assert history(client, new["id"]) == [saved]
    assert client.get(f"/providers/{new['id']}/updates").json() == []
    assert client.get(f"/providers/{seeded_provider.id}").json() == original
    current = requirement(client, new["id"])
    assert current["status"] == "Completed" and current["version"] == 1


def test_deadline_only_edit_and_date_clearing_update_saved_monitoring(
    client, seeded_provider
):
    main.app.dependency_overrides[main.get_monitoring_date] = lambda: date(2026, 11, 11)
    row = requirement(client, seeded_provider.id)
    save(
        client,
        seeded_provider.id,
        row,
        edit_body(
            row, status=row["status"], scheduled_date=None, deadline="2026-11-10"
        ),
    )
    dashboard = client.get(f"/providers/{seeded_provider.id}/dashboard").json()
    indicator = next(
        r
        for r in dashboard["monitoring"]["requirements"]
        if r["requirement_id"] == row["id"]
    )
    assert indicator == {
        "requirement_id": row["id"],
        "completion": "outstanding",
        "deadline_state": "past",
    }
    current = requirement(client, seeded_provider.id)
    saved = save(
        client,
        seeded_provider.id,
        current,
        edit_body(
            current, status=current["status"], scheduled_date=None, deadline=None
        ),
    )
    assert (
        saved["previous_deadline"] == "2026-11-10" and saved["applied_deadline"] is None
    )
    assert saved["resulting_version"] == 2


@pytest.mark.parametrize("headers", [{}, {"X-Demo-Role": "proposer"}])
def test_direct_edit_requires_manager_without_writes(client, seeded_provider, headers):
    row = requirement(client, seeded_provider.id)
    response = client.post(
        endpoint(seeded_provider.id, row["id"]), headers=headers, json=edit_body(row)
    )
    assert response.status_code == 403
    assert requirement(client, seeded_provider.id) == row
    assert history(client, seeded_provider.id) == []


@pytest.mark.parametrize(
    "change",
    [
        {"status": "Signed"},
        {"status": " "},
        {"expected_version": -1},
        {"deadline": "2026-02-30"},
        {"name": "Another requirement"},
    ],
)
def test_invalid_direct_edit_does_not_write(client, seeded_provider, change):
    row = requirement(client, seeded_provider.id)
    response = client.post(
        endpoint(seeded_provider.id, row["id"]),
        headers=MANAGER,
        json=edit_body(row, **change),
    )
    assert response.status_code == 422
    assert requirement(client, seeded_provider.id) == row
    assert history(client, seeded_provider.id) == []


def test_noop_stale_and_wrong_provider_edits_do_not_write(client, seeded_provider):
    row = requirement(client, seeded_provider.id)
    path = endpoint(seeded_provider.id, row["id"])
    assert (
        client.post(
            path,
            headers=MANAGER,
            json=edit_body(
                row,
                status=row["status"],
                scheduled_date=row["scheduled_date"],
                deadline=row["deadline"],
            ),
        ).status_code
        == 422
    )
    assert (
        client.post(
            path, headers=MANAGER, json=edit_body(row, expected_version=5)
        ).status_code
        == 409
    )
    assert (
        client.post(
            endpoint(uuid4(), row["id"]), headers=MANAGER, json=edit_body(row)
        ).status_code
        == 404
    )
    assert client.get(f"/providers/{uuid4()}/checklist-edits").status_code == 404
    assert history(client, seeded_provider.id) == []


def test_retry_after_later_progress_returns_event_without_reset(
    client, seeded_provider
):
    row = requirement(client, seeded_provider.id)
    body = edit_body(row)
    first = save(client, seeded_provider.id, row, body)
    current = requirement(client, seeded_provider.id)
    second = save(
        client,
        seeded_provider.id,
        current,
        edit_body(current, status="Incomplete", scheduled_date=None, deadline=None),
    )
    assert save(client, seeded_provider.id, row, body) == first
    assert requirement(client, seeded_provider.id)["status"] == "Incomplete"
    assert history(client, seeded_provider.id) == [second, first]
    for changes in [{"status": "Pending"}, {"expected_version": 2}, {"deadline": None}]:
        assert (
            client.post(
                endpoint(seeded_provider.id, row["id"]),
                headers=MANAGER,
                json={**body, **changes},
            ).status_code
            == 409
        )
    other = requirement(client, seeded_provider.id, "Offer letter")
    assert (
        client.post(
            endpoint(seeded_provider.id, other["id"]), headers=MANAGER, json=body
        ).status_code
        == 409
    )
    assert len(history(client, seeded_provider.id)) == 2


@pytest.mark.parametrize("kind", ["same", "conflicting_id", "conflicting_version"])
def test_concurrent_edits_have_one_winning_mutation(client, seeded_provider, kind):
    row = requirement(client, seeded_provider.id)
    first = edit_body(row)
    second = {**first}
    if kind == "conflicting_id":
        second["status"] = "Incomplete"
    if kind == "conflicting_version":
        second["id"] = str(uuid4())
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(
            executor.map(
                lambda body: client.post(
                    endpoint(seeded_provider.id, row["id"]), headers=MANAGER, json=body
                ),
                [first, second],
            )
        )
    assert sorted(r.status_code for r in results) == (
        [201, 201] if kind == "same" else [201, 409]
    )
    assert len(history(client, seeded_provider.id)) == 1
    assert requirement(client, seeded_provider.id)["version"] == 1


@pytest.mark.parametrize("first_operation", ["manual", "review", "concurrent"])
def test_manual_and_suggestion_review_share_version_lock(
    client, seeded_provider, extraction_model, first_operation
):
    suggestion = analyze(client, extraction_model, seeded_provider.id)
    row = requirement(client, seeded_provider.id)

    def manual():
        return client.post(
            endpoint(seeded_provider.id, row["id"]),
            headers=MANAGER,
            json=edit_body(row, status="Incomplete"),
        )

    def review():
        return client.post(
            f"/suggestions/{suggestion['id']}/review",
            headers=MANAGER,
            json={"action": "approve"},
        )

    if first_operation == "concurrent":
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(
                executor.map(lambda operation: operation(), [manual, review])
            )
        assert sorted(r.status_code for r in results) in ([200, 409], [201, 409])
    else:
        operations = (
            [manual, review] if first_operation == "manual" else [review, manual]
        )
        assert operations[0]().status_code in (200, 201)
        assert operations[1]().status_code == 409
    assert requirement(client, seeded_provider.id)["version"] == 1


def test_unfamiliar_verbatim_status_and_other_type_do_not_gain_dentist_rules(
    client, seeded_provider
):
    row = requirement(client, seeded_provider.id, "Hawaii dental license")
    with psycopg.connect(configured_test_url()) as conn:
        conn.execute(
            "UPDATE requirements SET status='  rEcEiVeD  ' WHERE id=%s", (row["id"],)
        )
    dashboard = client.get(f"/providers/{seeded_provider.id}/dashboard").json()
    choices = next(
        r for r in dashboard["checklist_options"] if r["requirement_id"] == row["id"]
    )
    assert choices["statuses"] == [
        "Outstanding",
        "Pending",
        "Incomplete",
        "Received",
        "  rEcEiVeD  ",
    ]
    assert choices["status_tone"] == "finished"
    saved = save(client, seeded_provider.id, row, edit_body(row, status="  rEcEiVeD  "))
    assert saved["applied_status"] == "  rEcEiVeD  "
    type_id = uuid4()
    with psycopg.connect(configured_test_url()) as conn:
        conn.execute(
            "INSERT INTO provider_types VALUES (%s,'Synthetic Other')", (type_id,)
        )
        conn.execute(
            "INSERT INTO requirement_templates VALUES (%s,%s,'Drug screening')",
            (uuid4(), type_id),
        )
    new = client.post(
        "/providers",
        headers=MANAGER,
        json={
            "id": str(uuid4()),
            "name": "Other Fictional",
            "provider_type_id": str(type_id),
        },
    ).json()
    other = requirement(client, new["id"])
    assert (
        client.post(
            endpoint(new["id"], other["id"]), headers=MANAGER, json=edit_body(other)
        ).status_code
        == 422
    )
    assert client.get(f"/providers/{new['id']}/dashboard").json()["checklist_options"][
        0
    ]["statuses"] == ["Outstanding"]


def test_failed_audit_insert_rolls_back_requirement(client, seeded_provider):
    row = requirement(client, seeded_provider.id)
    with psycopg.connect(configured_test_url()) as conn:
        conn.execute(
            "CREATE FUNCTION test_reject_edit() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'test failure'; END $$"
        )
        conn.execute(
            "CREATE TRIGGER test_reject_edit BEFORE INSERT ON checklist_edits FOR EACH ROW EXECUTE FUNCTION test_reject_edit()"
        )
    try:
        result = client.post(
            endpoint(seeded_provider.id, row["id"]),
            headers=MANAGER,
            json=edit_body(row),
        )
        assert result.status_code == 503 and "test failure" not in result.text
        assert requirement(client, seeded_provider.id) == row
        assert history(client, seeded_provider.id) == []
    finally:
        with psycopg.connect(configured_test_url()) as conn:
            conn.execute("DROP TRIGGER test_reject_edit ON checklist_edits")
            conn.execute("DROP FUNCTION test_reject_edit()")


def test_saved_manual_audit_is_immutable_in_postgresql(client, seeded_provider):
    row = requirement(client, seeded_provider.id)
    saved = save(client, seeded_provider.id, row)
    for query in [
        "UPDATE checklist_edits SET applied_status='Pending' WHERE id=%s",
        "DELETE FROM checklist_edits WHERE id=%s",
    ]:
        with (
            pytest.raises(psycopg.errors.RaiseException),
            psycopg.connect(configured_test_url()) as conn,
        ):
            conn.execute(query, (saved["id"],))
    assert history(client, seeded_provider.id) == [saved]


def test_manual_endpoints_fail_safely_without_configuration_or_schema(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    path = endpoint(uuid4(), uuid4())
    body = edit_body({"version": 0})
    with TestClient(main.create_app()) as test_client:
        result = test_client.post(path, headers=MANAGER, json=body)
        assert result.status_code == 503 and "postgresql://" not in result.text
    with disposable_database() as url:
        monkeypatch.setenv("DATABASE_URL", url)
        with TestClient(main.create_app()) as test_client:
            result = test_client.post(path, headers=MANAGER, json=body)
            assert result.status_code == 503 and "UndefinedTable" not in result.text
