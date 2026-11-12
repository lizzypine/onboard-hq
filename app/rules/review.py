"""Pure role, date, and concurrency decisions; no HTTP or database clients."""

from datetime import date

from app.models import (
    DemoRole,
    ReviewChange,
    ReviewRequest,
    SavedSuggestion,
    StoredRequirement,
)


class ReviewForbidden(ValueError):
    """The simulated role cannot make review decisions."""


class ReviewConflict(ValueError):
    """A suggestion is no longer pending against the captured checklist version."""


class ReviewValidationError(ValueError):
    """The manager must supply a valid confirmed date before approval."""


def require_manager(role: DemoRole) -> None:
    if role != "manager":
        raise ReviewForbidden("Manager mode is required to review suggestions.")


def _scheduled_date(
    requirement: StoredRequirement, suggestion: SavedSuggestion, request: ReviewRequest
) -> date | None:
    value = (
        suggestion.proposed_date
        if suggestion.proposed_date is not None
        else requirement.scheduled_date
    )
    if request.date_action == "set":
        value = request.corrected_date
    elif request.date_action == "clear":
        value = None
    if suggestion.date_requires_confirmation and (
        not request.date_confirmed or value is None
    ):
        raise ReviewValidationError(
            "Check and explicitly confirm a valid inferred date before approving."
        )
    return value


def resolve_review(
    requirement: StoredRequirement, suggestion: SavedSuggestion, request: ReviewRequest
) -> ReviewChange:
    if suggestion.decision is not None or suggestion.requirement_id != requirement.id:
        raise ReviewConflict(
            "This suggestion is already reviewed or no longer matches its requirement."
        )
    if request.action == "reject":
        return ReviewChange(
            outcome="rejected", applied_status=None, applied_scheduled_date=None
        )
    if requirement.version != suggestion.requirement_version:
        raise ReviewConflict(
            "The checklist changed after extraction. Reanalyze before approving."
        )
    status = (
        request.corrected_status
        if request.corrected_status is not None
        else suggestion.proposed_status
    )
    return ReviewChange(
        outcome="approved" if request.action == "approve" else "corrected",
        applied_status=status,
        applied_scheduled_date=_scheduled_date(requirement, suggestion, request),
    )
