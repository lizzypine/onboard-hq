"""Review regressions prevent stuck creation, incorrect rows, and guessed dates."""

from uuid import uuid4

import psycopg
import pytest

from app.models import Requirement, SuggestedChange
from app.rules.scope import filter_suggestions
from tests.database import configured_test_url
from tests.fixtures.current_database import configure_catalog
from tests.test_provider_additions import MANAGER, create, extra, reviewed_body


@pytest.mark.parametrize(
    "change", ["empty_latest", "membership_removed", "header_removed"]
)
def test_unavailable_reviewed_template_is_a_definitive_catalog_conflict(client, change):
    template = configure_catalog("Synthetic Other", ["Other standard"])
    payload = reviewed_body(client, [extra()], provider_type_id=template.id)
    with psycopg.connect(configured_test_url()) as conn:
        if change == "empty_latest":
            conn.execute(
                "INSERT INTO checklist_templates(provider_type_id,template_version) VALUES (%s,2)",
                (template.id,),
            )
        elif change == "membership_removed":
            conn.execute(
                "DELETE FROM template_requirements WHERE checklist_template_id=%s",
                (template.checklist_template_id,),
            )
        else:
            conn.execute(
                "DELETE FROM checklist_templates WHERE id=%s",
                (template.checklist_template_id,),
            )
    response = client.post("/providers", headers=MANAGER, json=payload)
    assert response.status_code == 409
    assert response.json().get("code") == "template_changed"
    assert len(client.get("/providers").json()) == 1


@pytest.mark.parametrize("value", [0, 86400, "86400", "2026-12-10T00:00:00Z"])
@pytest.mark.parametrize("field", ["proposed_start_date", "scheduled_date", "deadline"])
def test_creation_dates_require_explicit_calendar_dates(client, value, field):
    payload = reviewed_body(client, [extra(status="Pending")])
    if field == "proposed_start_date":
        payload[field] = value
    else:
        payload["additional_requirements"][0][field] = value
    response = client.post("/providers", headers=MANAGER, json=payload)
    assert response.status_code == 422, response.text
    assert len(client.get("/providers").json()) == 1


@pytest.mark.parametrize("target", ["Straße orientation", "Strasse orientation"])
def test_distinct_unicode_names_keep_the_exact_saved_requirement_id(
    client, extraction_model, target
):
    saved = create(
        client,
        reviewed_body(
            client,
            [
                extra("Straße orientation", "Pending"),
                extra("Strasse orientation", "Pending"),
            ],
        ),
    )
    expected = next(row for row in saved["requirements"] if row["name"] == target)
    extraction_model.custom_output_args = {
        "suggestions": [
            {
                "requirement": target,
                "proposed_status": "Completed",
                "supporting_text": target + " completed.",
            }
        ]
    }
    response = client.post(
        "/updates/analyze",
        json={
            "provider_id": saved["id"],
            "request_id": str(uuid4()),
            "update_text": target + " completed.",
        },
    )
    assert response.status_code == 200, response.text
    suggestion = response.json()["suggestions"][0]
    assert (
        suggestion["requirement"] == target
        and suggestion["requirement_id"] == expected["id"]
    )
    assert (
        client.post(
            f"/suggestions/{suggestion['id']}/review",
            headers=MANAGER,
            json={"action": "approve"},
        ).status_code
        == 200
    )
    current = client.get(f"/providers/{saved['id']}").json()
    other = next(
        row
        for row in current["requirements"]
        if row["name"] in {"Straße orientation", "Strasse orientation"}
        and row["name"] != target
    )
    assert other["status"] == "Pending" and other["version"] == 0


def test_ambiguous_normalized_scope_fails_closed_instead_of_selecting_a_row():
    requirements = [
        Requirement(name="Drug screening", status="Pending"),
        Requirement(name="drug screening", status="Pending"),
    ]
    kept, warnings = filter_suggestions(
        requirements,
        [
            SuggestedChange(
                requirement="DRUG SCREENING",
                proposed_status="Completed",
                supporting_text="Completed",
            )
        ],
    )
    assert kept == []
    assert any("Ambiguous" in warning for warning in warnings)
