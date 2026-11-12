"""Pure synthetic completion and deadline rules; no clock or I/O."""

from datetime import date

from app.models import StoredProvider
from app.monitoring_models import (
    Completion,
    DeadlineState,
    MonitoringCounts,
    ProviderMonitoring,
    RequirementMonitoring,
)

_DENTIST_STATUS_RULES: dict[str, tuple[str, frozenset[str]]] = {
    "Offer letter": ("signed", frozenset({"pending", "outstanding", "incomplete"})),
    "Hawaii dental license": (
        "received",
        frozenset({"pending", "outstanding", "incomplete"}),
    ),
    "Drug screening": (
        "completed",
        frozenset({"scheduled", "pending", "outstanding", "incomplete"}),
    ),
    "State NED license": (
        "received",
        frozenset({"outstanding", "pending", "incomplete"}),
    ),
    "Insurance credentialing": (
        "approved",
        frozenset({"pending", "submitted", "outstanding", "incomplete"}),
    ),
}


def classify_completion(
    provider_type: str, requirement_name: str, status: str
) -> Completion:
    if provider_type != "Dentist" or requirement_name not in _DENTIST_STATUS_RULES:
        return "needs_review"
    finished, unfinished = _DENTIST_STATUS_RULES[requirement_name]
    normalized = status.strip().casefold()
    if normalized == finished:
        return "finished"
    if normalized in unfinished:
        return "outstanding"
    return "needs_review"


def classify_deadline(deadline: date | None, as_of_date: date) -> DeadlineState:
    if deadline is None:
        return "not_set"
    if deadline < as_of_date:
        return "past"
    if deadline == as_of_date:
        return "due_today"
    return "upcoming"


def monitor_provider(
    provider: StoredProvider, *, as_of_date: date
) -> ProviderMonitoring:
    rows = [
        RequirementMonitoring(
            requirement_id=requirement.id,
            completion=classify_completion(
                provider.provider_type, requirement.name, requirement.status
            ),
            deadline_state=classify_deadline(requirement.deadline, as_of_date),
        )
        for requirement in provider.requirements
    ]
    finished = sum(row.completion == "finished" for row in rows)
    return ProviderMonitoring(
        as_of_date=as_of_date,
        requirements=rows,
        counts=MonitoringCounts(
            total=len(rows),
            finished=finished,
            remaining=len(rows) - finished,
            overdue=sum(
                row.completion == "outstanding" and row.deadline_state == "past"
                for row in rows
            ),
            needs_review=sum(row.completion == "needs_review" for row in rows),
        ),
    )
