"""Validate that suggested changes belong to the provider's checklist."""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING

from app.rules.catalog import normalize_name

if TYPE_CHECKING:
    from app.agent import Requirement, SuggestedChange


def validate_update_suggestions(
    requirements: Sequence[Requirement], suggestions: Sequence[SuggestedChange]
) -> None:
    """Reject empty suggestions without changing the supplied requirements."""
    if not suggestions:
        raise ValueError("Insufficient information: no actionable suggestions.")


def filter_suggestions(
    requirements: Sequence[Requirement], suggestions: Sequence[SuggestedChange]
) -> tuple[list[SuggestedChange], list[str]]:
    """Keep actionable checklist changes and warn about unmatched suggestions."""
    names: dict[str, list[str]] = {}
    for item in requirements:
        names.setdefault(normalize_name(item.name), []).append(item.name)
    kept: list[SuggestedChange] = []
    warnings: list[str] = []
    for suggestion in suggestions:
        matches = names.get(normalize_name(suggestion.requirement), [])
        if not matches:
            warnings.append(
                f"Unmatched requirement: {suggestion.requirement}. "
                "No change was proposed for this requirement."
            )
        elif len(matches) != 1:
            warnings.append(
                f"Ambiguous requirement: {suggestion.requirement}. "
                "No change was proposed for this requirement."
            )
        elif not suggestion.proposed_status.strip():
            warnings.append(f"No actionable status supplied for {matches[0]}.")
        else:
            kept.append(suggestion.model_copy(update={"requirement": matches[0]}))
    return kept, warnings
