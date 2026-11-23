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

GENERIC_ADDITIONAL_STATUSES = (
    "Outstanding",
    "Pending",
    "Scheduled",
    "Incomplete",
    "Completed",
)


def configured_status_catalog(provider_type: str) -> dict[str, list[str]]:
    if provider_type.strip(" ").lower() != "dentist":
        return {}
    return {name.lower(): list(choices) for name, choices in _DENTIST_STATUSES.items()}


def known_statuses(
    provider_type: str, requirement_name: str, *, is_additional: bool = False
) -> tuple[str, ...] | None:
    fallback = GENERIC_ADDITIONAL_STATUSES if is_additional else None
    if provider_type.strip(" ").lower() != "dentist":
        return fallback
    normalized = requirement_name.strip(" ").lower()
    return next(
        (
            choices
            for name, choices in _DENTIST_STATUSES.items()
            if name.lower() == normalized
        ),
        fallback,
    )


def status_choices(
    provider_type: str,
    requirement_name: str,
    *preserved: str,
    is_additional: bool = False,
) -> list[str]:
    choices = known_statuses(
        provider_type, requirement_name, is_additional=is_additional
    ) or ("Outstanding",)
    return list(dict.fromkeys([*choices, *preserved]))


def classify_completion(
    provider_type: str,
    requirement_name: str,
    status: str,
    *,
    is_additional: bool = False,
) -> Completion:
    choices = known_statuses(
        provider_type, requirement_name, is_additional=is_additional
    )
    if choices is None:
        return "needs_review"
    normalized = status.strip().casefold()
    if normalized == choices[-1].casefold():
        return "finished"
    if normalized in {value.casefold() for value in choices[:-1]}:
        return "outstanding"
    return "needs_review"


def status_tone(
    provider_type: str,
    requirement_name: str,
    status: str,
    *,
    is_additional: bool = False,
) -> Literal["finished", "progress", "attention", "unknown"]:
    completion = classify_completion(
        provider_type, requirement_name, status, is_additional=is_additional
    )
    if completion == "finished":
        return "finished"
    if completion == "needs_review":
        return "unknown"
    return (
        "progress"
        if status.strip().casefold() in {"pending", "scheduled", "submitted"}
        else "attention"
    )
