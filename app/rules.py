"""Plain Python validation rules for onboarding updates."""

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
