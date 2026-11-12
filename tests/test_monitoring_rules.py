"""Completion and deadline behavior, with no database or model calls."""

from datetime import date
from uuid import uuid4

import pytest

from app.models import StoredProvider, StoredRequirement
from app.rules.monitoring import (
    classify_completion,
    classify_deadline,
    monitor_provider,
)

AS_OF = date(2026, 11, 11)


def provider_with(
    name,
    status,
    deadline,
    *,
    provider_type="Dentist",
    scheduled_date=None,
    proposed_start_date=None,
):
    provider_id = uuid4()
    return StoredProvider(
        id=provider_id,
        name="Dr. Kekoa Ejemplo",
        provider_type=provider_type,
        proposed_start_date=proposed_start_date,
        requirements=[
            StoredRequirement(
                id=uuid4(),
                provider_id=provider_id,
                name=name,
                status=status,
                deadline=deadline,
                scheduled_date=scheduled_date,
                version=2,
            )
        ],
    )


@pytest.mark.parametrize(
    "name,status,deadline,completion,deadline_state,finished,overdue",
    [
        ("Offer letter", "Signed", date(2026, 11, 10), "finished", "past", 1, 0),
        (
            "Drug screening",
            "Scheduled",
            date(2026, 11, 18),
            "outstanding",
            "upcoming",
            0,
            0,
        ),
        ("Drug screening", "Completed", date(2026, 11, 10), "finished", "past", 1, 0),
        (
            "Insurance credentialing",
            "Incomplete",
            date(2026, 11, 10),
            "outstanding",
            "past",
            0,
            1,
        ),
    ],
)
def test_confirmed_monitoring_scenarios(
    name, status, deadline, completion, deadline_state, finished, overdue
):
    provider = provider_with(name, status, deadline)
    result = monitor_provider(provider, as_of_date=AS_OF)
    assert result.as_of_date == AS_OF
    assert result.time_zone == "Pacific/Honolulu"
    assert result.requirements[0].requirement_id == provider.requirements[0].id
    assert result.requirements[0].completion == completion
    assert result.requirements[0].deadline_state == deadline_state
    assert result.counts.model_dump() == {
        "total": 1,
        "finished": finished,
        "remaining": 1 - finished,
        "overdue": overdue,
        "needs_review": 0,
    }


@pytest.mark.parametrize(
    "name,status,expected",
    [
        ("Offer letter", "Signed", "finished"),
        ("Offer letter", "Pending", "outstanding"),
        ("Offer letter", "Outstanding", "outstanding"),
        ("Offer letter", "Incomplete", "outstanding"),
        ("Hawaii dental license", "Received", "finished"),
        ("Hawaii dental license", "Pending", "outstanding"),
        ("Hawaii dental license", "Outstanding", "outstanding"),
        ("Hawaii dental license", "Incomplete", "outstanding"),
        ("Drug screening", "Completed", "finished"),
        ("Drug screening", "Scheduled", "outstanding"),
        ("Drug screening", "Pending", "outstanding"),
        ("Drug screening", "Outstanding", "outstanding"),
        ("Drug screening", "Incomplete", "outstanding"),
        ("State NED license", "Received", "finished"),
        ("State NED license", "Outstanding", "outstanding"),
        ("State NED license", "Pending", "outstanding"),
        ("State NED license", "Incomplete", "outstanding"),
        ("Insurance credentialing", "Approved", "finished"),
        ("Insurance credentialing", "Pending", "outstanding"),
        ("Insurance credentialing", "Submitted", "outstanding"),
        ("Insurance credentialing", "Outstanding", "outstanding"),
        ("Insurance credentialing", "Incomplete", "outstanding"),
    ],
)
def test_configured_completion_statuses(name, status, expected):
    assert classify_completion("Dentist", name, status) == expected


@pytest.mark.parametrize("status", [" completed ", "COMPLETED", "\tCoMpLeTeD\n"])
def test_completion_matches_status_only_after_trim_and_casefold(status):
    assert classify_completion("Dentist", "Drug screening", status) == "finished"


@pytest.mark.parametrize(
    "name,status",
    [
        ("Drug screening", "Not completed"),
        ("Drug screening", "Completed?"),
        ("Hawaii dental license", "Not received"),
        ("Insurance credentialing", "Submitted; awaiting approval"),
        ("Drug screening", ""),
        ("Drug screening", "  "),
    ],
)
def test_negated_and_qualified_statuses_need_review(name, status):
    assert classify_completion("Dentist", name, status) == "needs_review"


@pytest.mark.parametrize(
    "provider_type,name,status",
    [
        ("Synthetic other type", "Drug screening", "Completed"),
        ("dentist", "Drug screening", "Completed"),
        ("Dentist", "Synthetic requirement", "Signed"),
        ("Dentist", "drug screening", "Completed"),
        ("Dentist", "Offer letter", "Completed"),
    ],
)
def test_type_and_requirement_boundaries(provider_type, name, status):
    assert classify_completion(provider_type, name, status) == "needs_review"


@pytest.mark.parametrize(
    "deadline,expected",
    [
        (None, "not_set"),
        (date(2026, 11, 10), "past"),
        (date(2026, 11, 11), "due_today"),
        (date(2026, 11, 12), "upcoming"),
    ],
)
def test_deadline_boundaries(deadline, expected):
    result = monitor_provider(
        provider_with("Drug screening", "Scheduled", deadline), as_of_date=AS_OF
    )
    assert classify_deadline(deadline, AS_OF) == expected
    assert result.requirements[0].deadline_state == expected
    assert result.counts.overdue == (1 if expected == "past" else 0)


@pytest.mark.parametrize(
    "deadline", [None, date(2026, 11, 10), AS_OF, date(2026, 11, 12)]
)
def test_finished_requirement_never_counts_as_overdue(deadline):
    result = monitor_provider(
        provider_with("Drug screening", "Completed", deadline), as_of_date=AS_OF
    )
    assert result.requirements[0].completion == "finished"
    assert result.counts.finished == 1
    assert result.counts.remaining == result.counts.overdue == 0


@pytest.mark.parametrize(
    "deadline,scheduled,start,expected,overdue",
    [
        (None, date(2026, 11, 1), None, "not_set", 0),
        (None, None, date(2026, 11, 1), "not_set", 0),
        (date(2026, 11, 18), date(2026, 11, 1), AS_OF, "upcoming", 0),
        (date(2026, 11, 10), date(2026, 11, 18), date(2027, 1, 15), "past", 1),
    ],
)
def test_non_deadline_dates_do_not_change_monitoring(
    deadline, scheduled, start, expected, overdue
):
    result = monitor_provider(
        provider_with(
            "Drug screening",
            "Scheduled",
            deadline,
            scheduled_date=scheduled,
            proposed_start_date=start,
        ),
        as_of_date=AS_OF,
    )
    assert result.requirements[0].deadline_state == expected
    assert result.counts.overdue == overdue


def test_unknown_past_deadline_keeps_uncertainty():
    result = monitor_provider(
        provider_with("Drug screening", "Results being checked", date(2026, 11, 10)),
        as_of_date=AS_OF,
    )
    assert result.requirements[0].completion == "needs_review"
    assert result.requirements[0].deadline_state == "past"
    assert result.counts.overdue == 0
    assert result.counts.remaining == result.counts.needs_review == 1


def test_counts_partition_remaining_and_preserve_row_order():
    provider = provider_with("Offer letter", "Signed", date(2026, 11, 10))
    requirement = provider.requirements[0]
    provider.requirements.extend(
        [
            requirement.model_copy(
                update={"id": uuid4(), "name": "Drug screening", "status": "Scheduled"}
            ),
            requirement.model_copy(
                update={
                    "id": uuid4(),
                    "name": "Insurance credentialing",
                    "status": "Results being checked",
                }
            ),
        ]
    )
    before = provider.model_dump()
    result = monitor_provider(provider, as_of_date=AS_OF)
    assert [r.requirement_id for r in result.requirements] == [
        r.id for r in provider.requirements
    ]
    assert result.counts.model_dump() == {
        "total": 3,
        "finished": 1,
        "remaining": 2,
        "overdue": 1,
        "needs_review": 1,
    }
    assert provider.model_dump() == before


def test_empty_checklist_produces_zero_counts():
    provider = provider_with("Drug screening", "Scheduled", None)
    provider.requirements.clear()
    result = monitor_provider(provider, as_of_date=AS_OF)
    assert result.requirements == []
    assert result.counts.model_dump() == {
        "total": 0,
        "finished": 0,
        "remaining": 0,
        "overdue": 0,
        "needs_review": 0,
    }


def test_completion_reversal_reenters_remaining_and_overdue():
    provider = provider_with("Drug screening", "Completed", date(2026, 11, 10))
    finished = monitor_provider(provider, as_of_date=AS_OF)
    provider.requirements[0] = provider.requirements[0].model_copy(
        update={"status": "Incomplete", "version": 3}
    )
    reversed_result = monitor_provider(provider, as_of_date=AS_OF)
    assert finished.counts.finished == 1
    assert reversed_result.requirements[0].completion == "outstanding"
    assert reversed_result.counts.finished == 0
    assert reversed_result.counts.remaining == reversed_result.counts.overdue == 1


def test_monitoring_preserves_raw_status_and_all_stored_values():
    provider = provider_with("Drug screening", " cOmPlEtEd ", date(2026, 11, 10))
    before = provider.model_dump()
    assert monitor_provider(provider, as_of_date=AS_OF).counts.finished == 1
    assert provider.model_dump() == before
