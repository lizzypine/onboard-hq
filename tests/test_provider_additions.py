"""Atomic reviewed creation, provider-only workflows, and stable initial receipts."""

from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import psycopg
import pytest

from tests.database import configured_test_url
from tests.fixtures.current_database import configure_catalog

MANAGER = {"X-Demo-Role": "manager"}


def reviewed_body(client, additions=None, **changes):
    kinds = client.get("/provider-types").json()
    kind = next(
        (k for k in kinds if k["id"] == changes.get("provider_type_id")), kinds[0]
    )
    return {
        "creation_request_id": str(uuid4()),
        "name": "Dr. Walkthrough Example",
        "provider_type_id": kind["id"],
        "checklist_template_id": kind["checklist_template_id"],
        "template_fingerprint": kind["template_fingerprint"],
        "additional_requirements": additions or [],
        **changes,
    }


def extra(name="Orientation", status="Completed", **changes):
    return {
        "name": name,
        "status": status,
        "scheduled_date": None,
        "deadline": None,
        **changes,
    }


def create(client, payload):
    response = client.post("/providers", headers=MANAGER, json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def test_reviewed_additions_share_saved_workflows_and_keep_original_provider(
    client, seeded_provider, extraction_model
):
    original = client.get(f"/providers/{seeded_provider.id}").json()
    payload = reviewed_body(
        client,
        [
            extra(scheduled_date="2026-12-10", deadline="2026-12-20"),
            extra("IT access", "Scheduled"),
        ],
    )
    saved = create(client, payload)
    rows = {r["name"]: r for r in saved["requirements"]}
    assert len(rows) == 7
    assert rows["Orientation"]["checklist_template_id"] is None
    assert (
        rows["Orientation"]["status"],
        rows["Orientation"]["scheduled_date"],
        rows["Orientation"]["deadline"],
    ) == ("Completed", "2026-12-10", "2026-12-20")
    assert all(r["version"] == 0 for r in rows.values())
    assert all(
        r["status"] == "Outstanding"
        and r["scheduled_date"] is None
        and r["deadline"] is None
        for r in rows.values()
        if r["checklist_template_id"] is not None
    )
    dashboard = client.get(f"/providers/{saved['id']}/dashboard").json()
    assert dashboard["monitoring"]["counts"]["finished"] == 1
    assert dashboard["monitoring"]["counts"]["remaining"] == 6
    assert dashboard["monitoring"]["counts"]["needs_review"] == 0
    option = next(
        o
        for o in dashboard["checklist_options"]
        if o["requirement_id"] == rows["IT access"]["id"]
    )
    assert option["statuses"] == [
        "Outstanding",
        "Pending",
        "Scheduled",
        "Incomplete",
        "Completed",
    ]
    assert client.get(f"/providers/{saved['id']}/checklist-edits").json() == []
    extraction_model.custom_output_args = {
        "suggestions": [
            {
                "requirement": "IT access",
                "proposed_status": "Completed",
                "supporting_text": "IT access completed.",
            }
        ]
    }
    analysis = client.post(
        "/updates/analyze",
        json={
            "provider_id": saved["id"],
            "request_id": str(uuid4()),
            "update_text": "IT access completed.",
        },
    )
    assert analysis.status_code == 200, analysis.text
    captured = next(
        r
        for r in analysis.json()["provider_snapshot"]["requirements"]
        if r["name"] == "IT access"
    )
    assert (
        captured["checklist_template_id"] is None and captured["status"] == "Scheduled"
    )
    suggestion = analysis.json()["suggestions"][0]
    decision = client.post(
        f"/suggestions/{suggestion['id']}/review",
        headers=MANAGER,
        json={"action": "approve"},
    )
    assert decision.status_code == 200, decision.text
    edit = client.post(
        f"/providers/{saved['id']}/requirements/{rows['Orientation']['id']}/edits",
        headers=MANAGER,
        json={
            "operation_id": str(uuid4()),
            "expected_version": 0,
            "status": "Incomplete",
            "scheduled_date": None,
            "deadline": "2026-12-20",
        },
    )
    assert edit.status_code == 201, edit.text
    current = client.get(f"/providers/{saved['id']}").json()
    assert create(client, payload) == current
    assert client.get(f"/providers/{seeded_provider.id}").json() == original


@pytest.mark.parametrize(
    "additions",
    [
        [extra("Drug screening")],
        [extra("Orientation"), extra(" orientation ")],
        [extra(status="Signed")],
        [extra(name=" ")],
        [extra(deadline="2026-02-30")],
    ],
)
def test_invalid_additions_leave_no_provider_or_definition(client, additions):
    before = client.get("/providers").json()
    with psycopg.connect(configured_test_url()) as conn:
        definitions = conn.execute(
            "SELECT id,name FROM requirement_definitions ORDER BY id"
        ).fetchall()
    response = client.post(
        "/providers", headers=MANAGER, json=reviewed_body(client, additions)
    )
    assert response.status_code == 422, response.text
    assert client.get("/providers").json() == before
    with psycopg.connect(configured_test_url()) as conn:
        assert (
            conn.execute(
                "SELECT id,name FROM requirement_definitions ORDER BY id"
            ).fetchall()
            == definitions
        )


def test_template_change_requires_another_review_without_definition_residue(client):
    payload = reviewed_body(client, [extra()])
    configure_catalog("Dentist", ["Drug screening", "New standard item"], version=2)
    response = client.post("/providers", headers=MANAGER, json=payload)
    assert response.status_code == 409
    assert response.json()["code"] == "template_changed"
    with psycopg.connect(configured_test_url()) as conn:
        assert conn.execute("SELECT count(*) FROM providers").fetchone() == (1,)
        assert (
            conn.execute(
                "SELECT id FROM requirement_definitions WHERE name='Orientation'"
            ).fetchone()
            is None
        )
    updated = reviewed_body(
        client, [extra()], creation_request_id=payload["creation_request_id"]
    )
    assert len(create(client, updated)["requirements"]) == 3


def test_same_header_membership_change_requires_another_review(client):
    template = configure_catalog("Synthetic Other", ["Standard item"])
    payload = reviewed_body(client, [extra()], provider_type_id=template.id)
    with psycopg.connect(configured_test_url()) as conn:
        definition = conn.execute(
            "INSERT INTO requirement_definitions(name) VALUES ('Another standard') RETURNING id"
        ).fetchone()[0]
        conn.execute(
            "INSERT INTO template_requirements VALUES (%s,%s)",
            (template.checklist_template_id, definition),
        )
    response = client.post("/providers", headers=MANAGER, json=payload)
    assert response.status_code == 409 and response.json()["code"] == "template_changed"


def test_shared_additional_names_reuse_canonical_definitions_across_types(client):
    other = configure_catalog("Synthetic Other", ["Other standard"])
    first = create(client, reviewed_body(client, [extra()]))
    second = create(
        client,
        reviewed_body(
            client, [extra(" orientation ", "Scheduled")], provider_type_id=other.id
        ),
    )
    a = next(r for r in first["requirements"] if r["name"] == "Orientation")
    b = next(r for r in second["requirements"] if r["name"] == "Orientation")
    assert a["requirement_definition_id"] == b["requirement_definition_id"]
    assert a["status"] == "Completed" and b["status"] == "Scheduled"
    assert a["checklist_template_id"] is None and b["checklist_template_id"] is None


def test_concurrent_creation_retries_and_reordering_preserve_initial_values(client):
    payload = reviewed_body(client, [extra(), extra("IT access", "Scheduled")])
    with ThreadPoolExecutor(max_workers=2) as workers:
        results = list(workers.map(lambda _: create(client, payload), range(2)))
    assert results[0] == results[1]
    assert (
        create(
            client,
            {
                **payload,
                "additional_requirements": list(
                    reversed(payload["additional_requirements"])
                ),
            },
        )
        == results[0]
    )
    with psycopg.connect(configured_test_url()) as conn:
        conn.execute(
            "UPDATE providers SET archived_at=now() WHERE id=%s", (results[0]["id"],)
        )
    configure_catalog("Dentist", ["Drug screening"], version=2)
    assert create(client, payload)["archived_at"] is not None
    changed = {
        **payload,
        "additional_requirements": [
            extra(status="Pending"),
            extra("IT access", "Scheduled"),
        ],
    }
    assert client.post("/providers", headers=MANAGER, json=changed).status_code == 409
    assert len(client.get("/providers?state=all").json()) == 2


def test_new_definitions_roll_back_with_failed_checklist_insert(client):
    payload = reviewed_body(client, [extra()])
    with psycopg.connect(configured_test_url()) as conn:
        conn.execute("""CREATE FUNCTION reject_test_addition() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN IF NEW.checklist_template_id IS NULL THEN RAISE EXCEPTION 'Synthetic failure'; END IF; RETURN NEW; END $$""")
        conn.execute(
            "CREATE TRIGGER reject_test_addition BEFORE INSERT ON requirements FOR EACH ROW EXECUTE FUNCTION reject_test_addition()"
        )
    try:
        response = client.post("/providers", headers=MANAGER, json=payload)
        assert response.status_code == 503
        with psycopg.connect(configured_test_url()) as conn:
            assert conn.execute("SELECT count(*) FROM providers").fetchone() == (1,)
            assert (
                conn.execute(
                    "SELECT name FROM requirement_definitions WHERE name='Orientation'"
                ).fetchone()
                is None
            )
    finally:
        with psycopg.connect(configured_test_url()) as conn:
            conn.execute("DROP TRIGGER reject_test_addition ON requirements")
            conn.execute("DROP FUNCTION reject_test_addition()")


@pytest.mark.parametrize(
    "changes",
    [
        {"scheduled_date": "2026-12-11"},
        {"deadline": "2026-12-21"},
        {"status": "Pending"},
    ],
)
def test_reusing_creation_identity_with_changed_initial_fields_conflicts(
    client, changes
):
    payload = reviewed_body(
        client, [extra(scheduled_date="2026-12-10", deadline="2026-12-20")]
    )
    saved = create(client, payload)
    changed = {
        **payload,
        "additional_requirements": [
            {**payload["additional_requirements"][0], **changes}
        ],
    }
    assert client.post("/providers", headers=MANAGER, json=changed).status_code == 409
    assert client.get(f"/providers/{saved['id']}").json() == saved


def test_simultaneous_different_types_reuse_definitions_without_deadlock(client):
    template = configure_catalog("Synthetic Other", ["Other standard"])
    first = reviewed_body(
        client, [extra("Alpha", "Pending"), extra("Zulu", "Scheduled")]
    )
    second = reviewed_body(
        client,
        [extra("Zulu", "Completed"), extra("Alpha", "Outstanding")],
        provider_type_id=template.id,
    )
    with ThreadPoolExecutor(max_workers=2) as workers:
        results = list(workers.map(lambda body: create(client, body), [first, second]))
    assert results[0]["id"] != results[1]["id"]
    with psycopg.connect(configured_test_url()) as conn:
        assert conn.execute(
            "SELECT name,count(*) FROM requirement_definitions WHERE name IN ('Alpha','Zulu') GROUP BY name ORDER BY name"
        ).fetchall() == [("Alpha", 1), ("Zulu", 1)]


def test_configured_name_additions_use_specific_vocabulary(client):
    configure_catalog("Dentist", ["Drug screening"], version=2)
    saved = create(client, reviewed_body(client, [extra("Offer letter", "Signed")]))
    dashboard = client.get(f"/providers/{saved['id']}/dashboard").json()
    assert dashboard["monitoring"]["counts"]["finished"] == 1
    invalid = reviewed_body(client, [extra("Offer letter", "Completed")])
    assert client.post("/providers", headers=MANAGER, json=invalid).status_code == 422
