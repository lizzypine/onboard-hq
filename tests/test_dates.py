"""Calendar inference uses the provider start date, never today's date."""

from datetime import date

import pytest

from app import rules


@pytest.mark.parametrize(
    "year,month,day,start,expected,inferred",
    [
        (None, 10, 22, "2027-01-15", "2026-10-22", True),
        (None, None, 18, "2027-01-15", "2026-12-18", True),
        (None, None, 18, "2026-11-01", "2026-10-18", True),
        (None, None, 18, "2026-10-18", "2026-10-18", True),
        (None, None, 31, "2026-03-01", "2026-01-31", True),
        (None, 2, 29, "2027-01-15", "2024-02-29", True),
        (None, 10, 22, None, None, False),
        (2026, 10, 22, None, "2026-10-22", False),
        (2027, 2, 1, "2027-01-15", "2027-02-01", False),
        (None, 2, 30, "2027-01-15", None, False),
        (None, 13, 18, "2027-01-15", None, False),
        (None, None, 0, "2027-01-15", None, False),
        (2026, None, 18, "2027-01-15", None, False),
        (None, None, None, "2027-01-15", None, False),
        (None, None, 18, "0001-01-01", None, False),
        (2026, 2, 29, "2027-01-15", None, False),
        (10**40, 1, 1, "2027-01-15", None, False),
        (None, 10**40, 1, "2027-01-15", None, False),
    ],
)
def test_resolve_date(
    year: int | None,
    month: int | None,
    day: int | None,
    start: str | None,
    expected: str | None,
    inferred: bool,
) -> None:
    reference = date.fromisoformat(start) if start else None
    result = rules.resolve_date(
        year=year, month=month, day=day, proposed_start_date=reference
    )
    expected_date = date.fromisoformat(expected) if expected else None
    assert (result.proposed_date, result.inferred) == (expected_date, inferred)
    if expected_date is None:
        assert result.warning
    if inferred:
        assert reference is not None
        assert result.explanation is not None
        assert reference.isoformat() in result.explanation
