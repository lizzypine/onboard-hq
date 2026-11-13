"""Direct edits preserve evidence and use the recognized status vocabulary."""

from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.checklist_models import ChecklistEditRequest
from app.models import StoredRequirement
from app.rules.checklist import (
    ChecklistEditConflict,
    ChecklistEditForbidden,
    ChecklistEditInvalid,
    require_edit,
    require_edit_manager,
)
from app.rules.statuses import classify_completion, status_choices, status_tone


def payload(**changes):
    return dict(
        id=uuid4(),
        expected_version=0,
        status="Outstanding",
        scheduled_date=None,
        deadline=None,
        **changes,
    )


def test_direct_edit_preserves_verbatim_status():
    body = payload()
    body["status"] = "  rEcEiVeD  "
    assert ChecklistEditRequest.model_validate(body).status == "  rEcEiVeD  "


@pytest.mark.parametrize(
    "change",
    [
        {"status": " "},
        {"expected_version": -1},
        {"expected_version": True},
        {"deadline": "2026-02-30"},
        {"scheduled_date": "on the 18th"},
        {"requirement_name": "Something else"},
    ],
)
def test_direct_edit_rejects_invalid_or_extra_fields(change):
    with pytest.raises(ValidationError):
        ChecklistEditRequest.model_validate({**payload(), **change})


@pytest.mark.parametrize("missing", ["deadline", "scheduled_date"])
def test_direct_edit_requires_explicit_nullable_dates(missing):
    body = payload()
    del body[missing]
    with pytest.raises(ValidationError):
        ChecklistEditRequest.model_validate(body)


@pytest.mark.parametrize(
    "name,expected",
    [
        ("Offer letter", ["Outstanding", "Pending", "Incomplete", "Signed"]),
        ("Hawaii dental license", ["Outstanding", "Pending", "Incomplete", "Received"]),
        ("State NED license", ["Outstanding", "Pending", "Incomplete", "Received"]),
        (
            "Drug screening",
            ["Outstanding", "Pending", "Scheduled", "Incomplete", "Completed"],
        ),
        (
            "Insurance credentialing",
            ["Outstanding", "Pending", "Submitted", "Incomplete", "Approved"],
        ),
    ],
)
def test_requirement_specific_status_choices(name, expected):
    assert status_choices("Dentist", name) == expected


def test_status_choices_preserve_evidence_without_inventing_other_type_rules():
    assert status_choices(
        "Other", "Drug screening", " Custom ", "Outstanding", " Custom "
    ) == ["Outstanding", " Custom "]
    assert status_choices("Dentist", "Unknown", "Signed") == ["Outstanding", "Signed"]
    assert classify_completion("Other", "Offer letter", "Signed") == "needs_review"


@pytest.mark.parametrize(
    "name,status,tone,completion",
    [
        ("Offer letter", " sIgNeD ", "finished", "finished"),
        ("Drug screening", "Scheduled", "progress", "outstanding"),
        ("Insurance credentialing", "Submitted", "progress", "outstanding"),
        ("Drug screening", "Incomplete", "attention", "outstanding"),
        ("Drug screening", "Outstanding", "attention", "outstanding"),
        ("Drug screening", "Received", "unknown", "needs_review"),
    ],
)
def test_badge_tone_cannot_invent_completion(name, status, tone, completion):
    assert status_tone("Dentist", name, status) == tone
    assert classify_completion("Dentist", name, status) == completion


def test_direct_edit_rules_enforce_role_version_real_change_and_status_scope():
    row = StoredRequirement(
        id=uuid4(),
        provider_id=uuid4(),
        name="Drug screening",
        status="Outstanding",
        version=0,
    )
    request = ChecklistEditRequest.model_validate(payload())
    require_edit_manager("manager")
    with pytest.raises(ChecklistEditForbidden):
        require_edit_manager("proposer")
    with pytest.raises(ChecklistEditInvalid):
        require_edit(row, "Dentist", request)
    with pytest.raises(ChecklistEditConflict):
        require_edit(row, "Dentist", request.model_copy(update={"expected_version": 1}))
    with pytest.raises(ChecklistEditInvalid):
        require_edit(row, "Dentist", request.model_copy(update={"status": "Signed"}))
    require_edit(row, "Dentist", request.model_copy(update={"status": "Completed"}))
