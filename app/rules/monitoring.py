"""Pure synthetic completion and deadline rules; no clock or I/O."""

from datetime import date

from app.models import StoredProvider
from app.monitoring_models import (
    DeadlineState,
    MonitoringCounts,
    ProviderMonitoring,
    RequirementMonitoring,
)
from app.rules.statuses import classify_completion


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
