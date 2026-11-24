"""Question scope and exact supporting-citation validation."""

import re
from collections.abc import Iterable

from app.qa_models import AnswerDraft, RankedPassage
from app.rules.knowledge import (
    CONTROLLED_SUBSTANCE_TOPICS,
    DENTAL_TOPICS,
    SHARED_TOPICS,
    SUPPORTED_TOPICS,
)

DENTAL_TERMS = frozenset({"adex", "ce", "periodontal"})
CONTROLLED_SUBSTANCE_TERMS = frozenset({"csr", "dea", "ned", "pdmp"})


def question_topics(question: str) -> list[str]:
    """Narrow on clear question signals and search all topics when intent is broad."""
    words = re.findall(r"\w+", question.casefold())
    normalized = " ".join(words)
    dental = not DENTAL_TERMS.isdisjoint(words) or bool(
        re.search(
            r"\b(?:continuing ed(?:ucation)?|dental (?:renewal|licen[cs](?:e|es|ing)))\b",
            normalized,
        )
    )
    controlled = not CONTROLLED_SUBSTANCE_TERMS.isdisjoint(words) or any(
        phrase in normalized
        for phrase in (
            "controlled substance",
            "drug enforcement administration",
            "narcotics enforcement division",
            "prescriber education",
            "prescription drug monitoring program",
        )
    )
    if dental == controlled:
        return sorted(SUPPORTED_TOPICS)
    selected = DENTAL_TOPICS if dental else CONTROLLED_SUBSTANCE_TOPICS
    return sorted(selected | SHARED_TOPICS)


class QuestionConflict(ValueError):
    """A request UUID was already used for different input."""


class QuestionScopeError(ValueError):
    """The requested requirement does not belong to the selected provider."""


class InvalidAnswer(ValueError):
    """A generated answer could not be supported by its supplied citations."""


def mismatched_type(question: str, selected: str, types: Iterable[str]) -> str | None:
    for provider_type in types:
        # Dental hygienist is commonly shortened to hygienist. A token boundary
        # avoids interpreting "dentistry" as an explicit request about a dentist.
        label = (
            "hygienist"
            if provider_type.casefold() == "dental hygienist"
            else provider_type
        )
        if provider_type.casefold() != selected.casefold() and re.search(
            rf"(?<!\w){re.escape(label)}s?(?!\w)", question, re.IGNORECASE
        ):
            return provider_type
    return None


def validate_answer(draft: AnswerDraft, retrieved: list[RankedPassage]) -> None:
    passages = {
        p.chunk.id: p.chunk.text for p in retrieved if p.context_order is not None
    }
    if draft.outcome == "supported" and not draft.claims:
        raise InvalidAnswer("A supported answer needs at least one cited claim.")
    if draft.outcome == "cannot_answer" and draft.claims:
        raise InvalidAnswer("An abstention cannot contain affirmative claims.")
    if draft.outcome != "cannot_answer" and draft.explanation:
        raise InvalidAnswer("Affirmative guidance belongs in cited claims.")
    if (draft.outcome == "more_information_needed") != bool(draft.missing_facts):
        raise InvalidAnswer("Missing facts must accompany a request for information.")
    if (draft.outcome == "conflicting_guidance") != bool(draft.conflict_explanation):
        raise InvalidAnswer("Conflicting guidance needs an explanation.")

    all_spans: set[tuple[int, int, int]] = set()
    for claim in draft.claims:
        spans: set[tuple[int, int, int]] = set()
        for cite in claim.citations:
            span = (cite.chunk_id, cite.start, cite.end)
            text = passages.get(cite.chunk_id, "")
            if (
                not cite.quote.strip()
                or not 0 <= cite.start < cite.end <= len(text)
                or text[cite.start : cite.end] != cite.quote
                or span in spans
            ):
                raise InvalidAnswer(
                    "Citation must quote a distinct exact span of a supplied passage."
                )
            spans.add(span)
        all_spans.update(spans)
    if draft.outcome == "conflicting_guidance" and len(all_spans) < 2:
        raise InvalidAnswer("Conflicting guidance needs evidence for each position.")
