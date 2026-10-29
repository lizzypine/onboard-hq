"""Validate that suggested changes belong to the provider's checklist."""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING

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
    names = {item.name.strip().casefold(): item.name for item in requirements}
    kept: list[SuggestedChange] = []
    warnings: list[str] = []
    for suggestion in suggestions:
        canonical = names.get(suggestion.requirement.strip().casefold())
        if canonical is None:
            warnings.append(
                f"Unmatched requirement: {suggestion.requirement}. "
                "No change was proposed for this requirement."
            )
        elif not suggestion.proposed_status.strip():
            warnings.append(f"No actionable status supplied for {canonical}.")
        else:
            kept.append(suggestion.model_copy(update={"requirement": canonical}))
    return kept, warnings
