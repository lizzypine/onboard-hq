"""Resolve stated date components against the provider's proposed start."""

from calendar import monthrange
from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class DateResolution:
    proposed_date: date | None
    inferred: bool
    explanation: str | None
    warning: str | None


def _unresolved(message: str) -> DateResolution:
    return DateResolution(None, False, None, message)


def _explicit_date(year: int, month: int | None, day: int) -> DateResolution:
    if month is None:
        return _unresolved("Incomplete date: a stated year needs a month and day.")
    try:
        stated = date(year, month, day)
    except (ValueError, OverflowError):
        return _unresolved("The stated date is not a valid calendar date.")
    return DateResolution(stated, False, None, None)


def _latest_annual(month: int, day: int, start: date) -> date | None:
    # Every possible month/day occurs within one 400-year Gregorian cycle.
    for year in range(start.year, max(0, start.year - 400), -1):
        if day <= monthrange(year, month)[1]:
            candidate = date(year, month, day)
            if candidate <= start:
                return candidate
    return None


def _latest_monthly(day: int, start: date) -> date | None:
    index = (start.year - 1) * 12 + start.month - 1
    for current in range(index, max(-1, index - 12), -1):
        year_offset, month_offset = divmod(current, 12)
        year, month = year_offset + 1, month_offset + 1
        if day <= monthrange(year, month)[1]:
            candidate = date(year, month, day)
            if candidate <= start:
                return candidate
    return None


def _valid_partial(month: int | None, day: int) -> bool:
    if not 1 <= day <= 31:
        return False
    if month is None:
        return True
    try:
        date(2000, month, day)  # A leap year permits every possible month/day.
    except (ValueError, OverflowError):
        return False
    return True


def resolve_date(
    *,
    year: int | None,
    month: int | None,
    day: int | None,
    proposed_start_date: date | None,
) -> DateResolution:
    """Infer only the missing components of supported partial date forms."""
    if day is None:
        return _unresolved("No complete date supplied; the day is missing.")
    if year is not None:
        return _explicit_date(year, month, day)
    if not _valid_partial(month, day):
        return _unresolved("The stated date components are not a valid calendar date.")
    if proposed_start_date is None:
        return _unresolved("Cannot infer an incomplete date without a proposed start date.")
    if month is None:
        candidate = _latest_monthly(day, proposed_start_date)
    else:
        candidate = _latest_annual(month, day, proposed_start_date)
    if candidate is None:
        return _unresolved("No valid date occurs on or before the proposed start date.")
    explanation = (
        f"Inferred the most recent valid occurrence on or before proposed start "
        f"date {proposed_start_date.isoformat()}. User approval is required."
    )
    return DateResolution(candidate, True, explanation, None)
