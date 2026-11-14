"""Synthetic status choices and completion semantics share one vocabulary."""

from typing import Literal

from app.monitoring_models import Completion

_DENTIST_STATUSES = {
    "Offer letter": ("Outstanding", "Pending", "Incomplete", "Signed"),
    "Hawaii dental license": ("Outstanding", "Pending", "Incomplete", "Received"),
    "State NED license": ("Outstanding", "Pending", "Incomplete", "Received"),
    "Drug screening": (
        "Outstanding",
        "Pending",
        "Scheduled",
        "Incomplete",
        "Completed",
    ),
    "Insurance credentialing": (
        "Outstanding",
        "Pending",
        "Submitted",
        "Incomplete",
        "Approved",
    ),
}


def status_choices(
    provider_type: str, requirement_name: str, *preserved: str
) -> list[str]:
    choices = (
        _DENTIST_STATUSES.get(requirement_name, ("Outstanding",))
        if provider_type == "Dentist"
        else ("Outstanding",)
    )
    return list(dict.fromkeys([*choices, *preserved]))


def classify_completion(
    provider_type: str, requirement_name: str, status: str
) -> Completion:
    if provider_type != "Dentist" or requirement_name not in _DENTIST_STATUSES:
        return "needs_review"
    choices = _DENTIST_STATUSES[requirement_name]
    normalized = status.strip().casefold()
    if normalized == choices[-1].casefold():
        return "finished"
    if normalized in {value.casefold() for value in choices[:-1]}:
        return "outstanding"
    return "needs_review"


def status_tone(
    provider_type: str, requirement_name: str, status: str
) -> Literal["finished", "progress", "attention", "unknown"]:
    completion = classify_completion(provider_type, requirement_name, status)
    if completion == "finished":
        return "finished"
    if completion == "needs_review":
        return "unknown"
    return (
        "progress"
        if status.strip().casefold() in {"pending", "scheduled", "submitted"}
        else "attention"
    )
