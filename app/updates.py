"""Orchestrate model extraction and deterministic suggestion validation."""

from datetime import date

from pydantic_ai import Agent

from app.agent import (
    AnalyzeUpdateRequest,
    AnalyzeUpdateResponse,
    ExtractedSuggestion,
    ExtractionResult,
    MentionedDate,
    SuggestedChange,
    extract_update,
)
from app.rules import filter_suggestions, resolve_date, validate_update_suggestions


def _with_date(
    candidate: SuggestedChange,
    raw: ExtractedSuggestion,
    start: date | None,
) -> tuple[SuggestedChange, list[str]]:
    if raw.date is None and raw.proposed_status.strip().casefold() != "scheduled":
        return candidate, []
    mentioned = raw.date or MentionedDate(text="")
    resolved = resolve_date(
        year=mentioned.year,
        month=mentioned.month,
        day=mentioned.day,
        proposed_start_date=start,
    )
    result = candidate.model_copy(
        update={
            "proposed_date": resolved.proposed_date,
            "date_text": mentioned.text or None,
            "date_inferred": resolved.inferred,
            "date_explanation": resolved.explanation,
            "date_requires_confirmation": resolved.inferred,
        }
    )
    warnings = (
        [f"{candidate.requirement}: {resolved.warning}"] if resolved.warning else []
    )
    return result, warnings


async def process_update(
    request: AnalyzeUpdateRequest, agent: Agent[None, ExtractionResult]
) -> AnalyzeUpdateResponse:
    """Return inspectable suggestions without mutating provider context."""
    extracted = await extract_update(request, agent)
    warnings = list(extracted.ambiguities)
    suggestions: list[SuggestedChange] = []
    for raw in extracted.suggestions:
        candidate = SuggestedChange(
            requirement=raw.requirement,
            proposed_status=raw.proposed_status,
            supporting_text=raw.supporting_text,
        )
        kept, scope_warnings = filter_suggestions(
            request.provider.requirements, [candidate]
        )
        warnings.extend(scope_warnings)
        if not kept:
            continue
        change, date_warnings = _with_date(
            kept[0], raw, request.provider.proposed_start_date
        )
        suggestions.append(change)
        warnings.extend(date_warnings)
    try:
        validate_update_suggestions(request.provider.requirements, suggestions)
    except ValueError as exc:
        return AnalyzeUpdateResponse(message=str(exc), ambiguities=warnings)
    return AnalyzeUpdateResponse(
        message="Review the proposed changes. No checklist statuses were changed.",
        suggestions=suggestions,
        ambiguities=warnings,
    )
