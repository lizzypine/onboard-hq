"""Requirement scope filtering keeps useful changes without mutating inputs."""

import pytest

from app import rules
from app.agent import Requirement, SuggestedChange


def suggestion(name: str, status: str = "Received") -> SuggestedChange:
    return SuggestedChange(
        requirement=name, proposed_status=status, supporting_text="License received."
    )


def test_mixed_scope_keeps_valid_suggestions() -> None:
    requirements = [Requirement(name="Hawaii dental license", status="Outstanding")]
    kept, warnings = rules.filter_suggestions(
        requirements,
        [suggestion("Hawaii dental license"), suggestion("State NED license")],
    )
    assert [item.requirement for item in kept] == ["Hawaii dental license"]
    assert any("State NED license" in warning for warning in warnings)


def test_all_unknown_reaches_empty_guard() -> None:
    requirements = [Requirement(name="Hawaii dental license", status="Outstanding")]
    kept, warnings = rules.filter_suggestions(
        requirements, [suggestion("State NED license")]
    )
    assert kept == []
    assert warnings
    with pytest.raises(ValueError, match="(?i)insufficient information"):
        rules.validate_update_suggestions(requirements, kept)


def test_scope_uses_canonical_names() -> None:
    requirements = [Requirement(name="Hawaii dental license", status="Outstanding")]
    kept, warnings = rules.filter_suggestions(
        requirements, [suggestion("  HAWAII DENTAL LICENSE  ")]
    )
    assert [item.requirement for item in kept] == ["Hawaii dental license"]
    assert warnings == []


def test_blank_status_is_not_actionable() -> None:
    requirements = [Requirement(name="Hawaii dental license", status="Outstanding")]
    kept, warnings = rules.filter_suggestions(
        requirements, [suggestion("Hawaii dental license", "   ")]
    )
    assert kept == []
    assert warnings


def test_scope_preserves_inputs() -> None:
    requirements = [Requirement(name="Hawaii dental license", status="Outstanding")]
    suggestions = [suggestion("  HAWAII DENTAL LICENSE  ")]
    original_requirements = [item.model_dump() for item in requirements]
    original_suggestions = [item.model_dump() for item in suggestions]
    rules.filter_suggestions(requirements, suggestions)
    assert [item.model_dump() for item in requirements] == original_requirements
    assert [item.model_dump() for item in suggestions] == original_suggestions
