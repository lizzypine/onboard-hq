"""Contracts for rejecting updates with no actionable suggestions."""

import pytest

from app import rules
from app.agent import Requirement, SuggestedChange


def test_empty_suggestions_are_rejected_without_changing_requirements() -> None:
    requirements = [
        Requirement(name="Hawaii dental license", status="Outstanding"),
        Requirement(name="Drug screening", status="Scheduled", deadline="2026-10-22"),
    ]
    original_requirements = [item.model_dump() for item in requirements]

    with pytest.raises(ValueError, match="(?i)insufficient information"):
        rules.validate_update_suggestions(requirements=requirements, suggestions=[])

    assert [item.model_dump() for item in requirements] == original_requirements


def test_nonempty_suggestions_pass_validation() -> None:
    requirements = [Requirement(name="Hawaii dental license", status="Outstanding")]
    suggestions = [
        SuggestedChange(
            requirement="Hawaii dental license",
            proposed_status="Received",
            supporting_text="Hawaii dental license received.",
        )
    ]

    assert rules.validate_update_suggestions(
        requirements=requirements, suggestions=suggestions
    ) is None
