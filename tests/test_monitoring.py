"""The monitoring clock uses Hawaii dates and captures one aware instant."""

from datetime import UTC, date, datetime, timedelta, timezone

import pytest

from app import monitoring


@pytest.mark.parametrize(
    "instant,expected",
    [
        (datetime(2026, 11, 11, 9, 59, 59, tzinfo=UTC), date(2026, 11, 10)),
        (datetime(2026, 11, 11, 10, 0, 0, tzinfo=UTC), date(2026, 11, 11)),
        (
            datetime(2026, 11, 11, 19, 0, tzinfo=timezone(timedelta(hours=9))),
            date(2026, 11, 11),
        ),
    ],
)
def test_hawaii_date_boundary(instant, expected):
    assert monitoring.hawaii_date_at(instant) == expected


def test_hawaii_date_rejects_naive_instant():
    with pytest.raises(ValueError):
        monitoring.hawaii_date_at(datetime(2026, 11, 11, 10))


def test_monitoring_date_captures_one_utc_instant(monkeypatch):
    calls = []

    class FixedDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            calls.append(tz)
            return datetime(2026, 11, 11, 9, 59, 59, tzinfo=UTC)

    monkeypatch.setattr(monitoring, "datetime", FixedDateTime)
    assert monitoring.get_monitoring_date() == date(2026, 11, 10)
    assert calls == [UTC]
