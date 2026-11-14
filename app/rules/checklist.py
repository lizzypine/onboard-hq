"""Role, version, status and retry identity rules for explicit Manager edits."""

from uuid import UUID

from app.checklist_models import ChecklistEdit, ChecklistEditRequest
from app.models import DemoRole, StoredRequirement
from app.rules.statuses import status_choices


class ChecklistEditForbidden(ValueError):
    """Only a simulated Manager can save checklist edits."""


class ChecklistEditConflict(ValueError):
    """The requirement version or edit identity has changed."""


class ChecklistEditInvalid(ValueError):
    """The edit is not an allowed real change."""


def require_edit_manager(role: DemoRole) -> None:
    if role != "manager":
        raise ChecklistEditForbidden("Manager mode is required to edit the checklist.")


def require_edit(
    current: StoredRequirement, provider_type: str, request: ChecklistEditRequest
) -> None:
    if current.version != request.expected_version:
        raise ChecklistEditConflict(
            "The checklist changed. Refresh data before editing again."
        )
    if request.status not in status_choices(
        provider_type, current.name, current.status
    ):
        raise ChecklistEditInvalid("Choose a status available for this requirement.")
    if (current.status, current.scheduled_date, current.deadline) == (
        request.status,
        request.scheduled_date,
        request.deadline,
    ):
        raise ChecklistEditInvalid("Change a checklist value before saving.")


def require_same_edit(
    existing: ChecklistEdit,
    provider_id: UUID,
    requirement_id: UUID,
    request: ChecklistEditRequest,
) -> None:
    original = ChecklistEditRequest(
        id=existing.id,
        expected_version=existing.expected_version,
        status=existing.applied_status,
        scheduled_date=existing.applied_scheduled_date,
        deadline=existing.applied_deadline,
    )
    if (
        existing.provider_id != provider_id
        or existing.requirement_id != requirement_id
        or original != request
    ):
        raise ChecklistEditConflict(
            "This edit attempt already saved different values. Refresh data before editing again."
        )
