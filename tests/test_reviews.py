"""Actual HTTP roles and PostgreSQL transactions for manager decisions."""

from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import psycopg
import pytest

from tests.database import configured_test_url

MANAGER = {"X-Demo-Role": "manager"}


def post_suggestion(client, provider, extraction_model, inferred=False):
    suggestion = {
        "requirement": "Drug screening",
        "proposed_status": "Completed",
        "supporting_text": "Drug screening completed.",
    }
    if inferred:
        suggestion.update(
            proposed_status="Scheduled", date={"text": "on the 18th", "day": 18}
        )
    extraction_model.custom_output_args = {
        "suggestions": [suggestion],
        "ambiguities": [],
    }
    result = client.post(
        "/updates/analyze",
        json={
            "provider_id": str(provider.id),
            "request_id": str(uuid4()),
            "update_text": "Drug screening update.",
        },
    )
    assert result.status_code == 200
    return result.json()["suggestions"][0]


def requirement(client, provider):
    rows = client.get(f"/providers/{provider.id}").json()["requirements"]
    return next(r for r in rows if r["name"] == "Drug screening")


def test_only_manager_can_apply_saved_suggestion(
    client, seeded_provider, extraction_model
):
    suggestion = post_suggestion(client, seeded_provider, extraction_model)
    path = f"/suggestions/{suggestion['id']}/review"
    assert client.post(path, json={"action": "approve"}).status_code == 403
    assert requirement(client, seeded_provider)["status"] == "Scheduled"
    decision = client.post(path, json={"action": "approve"}, headers=MANAGER)
    assert decision.status_code == 200
    assert decision.json()["previous_status"] == "Scheduled"
    assert decision.json()["applied_status"] == "Completed"
    assert requirement(client, seeded_provider)["version"] == 1
    assert (
        client.post(path, json={"action": "approve"}, headers=MANAGER).status_code
        == 409
    )
    history = client.get(f"/providers/{seeded_provider.id}/updates").json()[0]
    assert history["suggestions"][0]["supporting_text"] == "Drug screening completed."
    assert history["suggestions"][0]["decision"]["outcome"] == "approved"


@pytest.mark.parametrize("same_suggestion", [False, True])
def test_concurrent_reviews_apply_once_and_never_overwrite_newer_version(
    client, seeded_provider, extraction_model, same_suggestion
):
    first = post_suggestion(client, seeded_provider, extraction_model)
    second = (
        first
        if same_suggestion
        else post_suggestion(client, seeded_provider, extraction_model)
    )

    def decide(suggestion):
        return client.post(
            f"/suggestions/{suggestion['id']}/review",
            json={"action": "approve"},
            headers=MANAGER,
        ).status_code

    with ThreadPoolExecutor(max_workers=2) as workers:
        codes = list(workers.map(decide, [first, second]))
    assert sorted(codes) == [200, 409]
    assert requirement(client, seeded_provider)["version"] == 1
    with psycopg.connect(configured_test_url()) as conn:
        assert conn.execute("SELECT count(*) FROM review_decisions").fetchone() == (1,)


def test_correction_and_date_clearing_preserve_deadline_and_original_suggestion(
    client, seeded_provider, extraction_model
):
    suggestion = post_suggestion(client, seeded_provider, extraction_model)
    with psycopg.connect(configured_test_url()) as conn:
        conn.execute(
            "UPDATE requirements SET deadline='2026-11-30',scheduled_date='2026-11-20' WHERE id=%s",
            (suggestion["requirement_id"],),
        )
    result = client.post(
        f"/suggestions/{suggestion['id']}/review",
        json={
            "action": "correct",
            "corrected_status": "Incomplete",
            "date_action": "clear",
        },
        headers=MANAGER,
    )
    assert result.status_code == 200
    assert result.json()["outcome"] == "corrected"
    row = requirement(client, seeded_provider)
    assert row["status"] == "Incomplete"
    assert row["scheduled_date"] is None
    assert row["deadline"] == "2026-11-30"
    history = client.get(f"/providers/{seeded_provider.id}/updates").json()[0]
    assert history["suggestions"][0]["proposed_status"] == "Completed"


def test_rejection_retains_history_without_changing_requirement(
    client, seeded_provider, extraction_model
):
    suggestion = post_suggestion(client, seeded_provider, extraction_model)
    before = requirement(client, seeded_provider)
    result = client.post(
        f"/suggestions/{suggestion['id']}/review",
        json={"action": "reject"},
        headers=MANAGER,
    )
    assert result.status_code == 200
    assert result.json()["applied_status"] is None
    assert requirement(client, seeded_provider) == before


def test_inferred_date_must_be_confirmed_by_manager(
    client, seeded_provider, extraction_model
):
    suggestion = post_suggestion(
        client, seeded_provider, extraction_model, inferred=True
    )
    path = f"/suggestions/{suggestion['id']}/review"
    assert (
        client.post(path, json={"action": "approve"}, headers=MANAGER).status_code
        == 422
    )
    result = client.post(
        path,
        json={
            "action": "correct",
            "date_action": "set",
            "corrected_date": "2026-11-17",
            "date_confirmed": True,
        },
        headers=MANAGER,
    )
    assert result.status_code == 200
    assert requirement(client, seeded_provider)["scheduled_date"] == "2026-11-17"


def test_review_failure_rolls_back_requirement_update_and_decision(
    client, seeded_provider, extraction_model
):
    suggestion = post_suggestion(client, seeded_provider, extraction_model)
    url = configured_test_url()
    with psycopg.connect(url) as conn:
        conn.execute(
            "CREATE FUNCTION onboard_test_block_decision() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'sentinel-secret'; END $$"
        )
        conn.execute(
            "CREATE TRIGGER onboard_test_fail_decision BEFORE INSERT ON review_decisions FOR EACH ROW EXECUTE FUNCTION onboard_test_block_decision()"
        )
    try:
        result = client.post(
            f"/suggestions/{suggestion['id']}/review",
            json={"action": "approve"},
            headers=MANAGER,
        )
        assert result.status_code == 503
        assert "sentinel-secret" not in result.text
        assert requirement(client, seeded_provider)["status"] == "Scheduled"
        assert requirement(client, seeded_provider)["version"] == 0
        with psycopg.connect(url) as conn:
            assert conn.execute("SELECT count(*) FROM review_decisions").fetchone() == (
                0,
            )
    finally:
        with psycopg.connect(url) as conn:
            conn.execute("DROP TRIGGER onboard_test_fail_decision ON review_decisions")
            conn.execute("DROP FUNCTION onboard_test_block_decision()")


@pytest.mark.parametrize(
    "headers,body",
    [
        ({"X-Demo-Role": "admin"}, {"action": "approve"}),
        (MANAGER, {"action": "approve", "provider_id": str(uuid4())}),
        (MANAGER, {"action": "approve", "date_confirmed": "yes"}),
    ],
)
def test_invalid_role_and_forged_fields_are_rejected(
    client, seeded_provider, extraction_model, headers, body
):
    suggestion = post_suggestion(client, seeded_provider, extraction_model)
    assert (
        client.post(
            f"/suggestions/{suggestion['id']}/review", json=body, headers=headers
        ).status_code
        == 422
    )
    assert requirement(client, seeded_provider)["version"] == 0


def test_multiple_requirements_can_be_reviewed_independently(
    client, seeded_provider, extraction_model
):
    extraction_model.custom_output_args = {
        "suggestions": [
            {
                "requirement": "Drug screening",
                "proposed_status": "Completed",
                "supporting_text": "Drug screening completed.",
            },
            {
                "requirement": "Insurance credentialing",
                "proposed_status": "Incomplete",
                "supporting_text": "Credentialing returned for missing info.",
            },
        ]
    }
    saved = client.post(
        "/updates/analyze",
        json={
            "provider_id": str(seeded_provider.id),
            "request_id": str(uuid4()),
            "update_text": "Drug screening completed. Credentialing returned for missing info.",
        },
    )
    assert saved.status_code == 200
    suggestions = {s["requirement"]: s for s in saved.json()["suggestions"]}
    drug = suggestions["Drug screening"]["id"]
    credentialing = suggestions["Insurance credentialing"]["id"]
    assert (
        client.post(
            f"/suggestions/{drug}/review", json={"action": "approve"}, headers=MANAGER
        ).status_code
        == 200
    )
    assert (
        client.post(
            f"/suggestions/{credentialing}/review",
            json={"action": "reject"},
            headers=MANAGER,
        ).status_code
        == 200
    )
    rows = client.get(f"/providers/{seeded_provider.id}").json()["requirements"]
    assert {r["name"]: r["status"] for r in rows}["Drug screening"] == "Completed"
    assert {r["name"]: r["status"] for r in rows}[
        "Insurance credentialing"
    ] == "Pending"
