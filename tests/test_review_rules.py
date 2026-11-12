"""Plain review decisions protect roles, dates, and captured versions."""

from datetime import date
from uuid import uuid4

import pytest
from pydantic import ValidationError


def records(inferred=False, version=2, proposed_date=date(2026, 10, 22)):
    from app.models import SavedSuggestion, StoredRequirement

    requirement = StoredRequirement(
        id=uuid4(),
        provider_id=uuid4(),
        name="Drug screening",
        status="Outstanding",
        scheduled_date=date(2026, 10, 20),
        deadline=date(2026, 10, 30),
        version=version,
    )
    suggestion = SavedSuggestion(
        id=uuid4(),
        requirement_id=requirement.id,
        requirement_version=2,
        requirement="Drug screening",
        proposed_status="Scheduled",
        proposed_date=proposed_date,
        supporting_text="Scheduled",
        date_inferred=inferred,
        date_requires_confirmation=inferred,
    )
    return requirement, suggestion


@pytest.mark.parametrize(
    "body",
    [
        {"action": "approve", "date_confirmed": "true"},
        {"action": "approve", "date_confirmed": 1},
        {"action": "approve", "corrected_status": "Received"},
        {"action": "approve", "provider_id": str(uuid4())},
        {"action": "correct"},
        {"action": "correct", "corrected_status": " "},
        {"action": "correct", "date_action": "set"},
        {"action": "correct", "date_action": "clear", "corrected_date": "2026-10-22"},
        {"action": "correct", "date_action": "set", "corrected_date": "2026-02-30"},
        {"action": "reject", "date_confirmed": True},
    ],
)
def test_invalid_review_payloads_are_rejected(body):
    from app.models import ReviewRequest

    with pytest.raises(ValidationError):
        ReviewRequest.model_validate(body)


def test_proposer_cannot_review():
    from app.rules.review import ReviewForbidden, require_manager

    with pytest.raises(ReviewForbidden):
        require_manager("proposer")


@pytest.mark.parametrize(
    "proposed,want",
    [(date(2026, 10, 22), date(2026, 10, 22)), (None, date(2026, 10, 20))],
)
def test_approval_uses_proposal_date_or_preserves_existing(proposed, want):
    from app.models import ReviewRequest
    from app.rules.review import resolve_review

    requirement, suggestion = records(proposed_date=proposed)
    change = resolve_review(requirement, suggestion, ReviewRequest(action="approve"))
    assert change.applied_status == "Scheduled"
    assert change.applied_scheduled_date == want
    assert requirement.deadline == date(2026, 10, 30)
    assert requirement.status == "Outstanding"


def test_corrected_approval_can_clear_explicit_date_without_rewriting_proposal():
    from app.models import ReviewRequest
    from app.rules.review import resolve_review

    requirement, suggestion = records()
    change = resolve_review(
        requirement,
        suggestion,
        ReviewRequest(
            action="correct", corrected_status="Incomplete", date_action="clear"
        ),
    )
    assert change.outcome == "corrected"
    assert change.applied_status == "Incomplete"
    assert change.applied_scheduled_date is None
    assert suggestion.proposed_status == "Scheduled"


@pytest.mark.parametrize(
    "body",
    [
        {"action": "approve"},
        {"action": "correct", "date_action": "clear", "date_confirmed": True},
    ],
)
def test_inferred_date_requires_valid_confirmed_date(body):
    from app.models import ReviewRequest
    from app.rules.review import ReviewValidationError, resolve_review

    requirement, suggestion = records(inferred=True)
    with pytest.raises(ReviewValidationError):
        resolve_review(requirement, suggestion, ReviewRequest(**body))


def test_inferred_date_can_be_corrected_and_confirmed():
    from app.models import ReviewRequest
    from app.rules.review import resolve_review

    requirement, suggestion = records(inferred=True)
    change = resolve_review(
        requirement,
        suggestion,
        ReviewRequest(
            action="correct",
            date_action="set",
            corrected_date="2026-10-21",
            date_confirmed=True,
        ),
    )
    assert change.applied_scheduled_date == date(2026, 10, 21)


def test_stale_approval_conflicts_but_rejection_can_dismiss_it():
    from app.models import ReviewRequest
    from app.rules.review import ReviewConflict, resolve_review

    requirement, suggestion = records(version=3)
    with pytest.raises(ReviewConflict):
        resolve_review(requirement, suggestion, ReviewRequest(action="approve"))
    change = resolve_review(requirement, suggestion, ReviewRequest(action="reject"))
    assert change.outcome == "rejected"
    assert change.applied_status is None
