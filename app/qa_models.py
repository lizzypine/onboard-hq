"""Question, generation and retained licensing answer contracts."""

from datetime import date, datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field, StringConstraints

from app.knowledge_models import Contract, EmbeddingSpace, KnowledgeChunk
from app.models import RecordId

Question = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True, min_length=1, max_length=2000, pattern=r"^[^\x00]+$"
    ),
]
AnswerText = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True, min_length=1, max_length=2500, pattern=r"^[^\x00]+$"
    ),
]
DraftOutcome = Literal[
    "supported", "more_information_needed", "conflicting_guidance", "cannot_answer"
]
AnswerOutcome = DraftOutcome | Literal["service_unavailable"]


class AskRequest(Contract):
    request_id: UUID
    provider_id: RecordId
    requirement_id: RecordId | None = None
    question: Question


class CitationRef(Contract):
    chunk_id: RecordId
    quote: Annotated[str, Field(min_length=1, max_length=1400)]
    start: Annotated[int, Field(strict=True, ge=0)]
    end: RecordId


class ClaimDraft(Contract):
    text: AnswerText
    citations: Annotated[list[CitationRef], Field(min_length=1, max_length=8)]


class AnswerDraft(Contract):
    outcome: DraftOutcome
    claims: Annotated[list[ClaimDraft], Field(max_length=12)] = Field(
        default_factory=list
    )
    explanation: AnswerText | None = None
    missing_facts: AnswerText | None = None
    conflict_explanation: AnswerText | None = None


class SavedCitation(Contract):
    chunk_id: int
    version_id: int
    document_id: int
    source_key: str
    source_title: str
    source_kind: Literal["official", "internal"]
    publisher: str
    original_url: str | None
    stated_revision: str | None
    source_checksum: str
    retrieved_at: datetime
    reviewed_at: datetime
    effective_from: date | None
    effective_to: date | None
    section: str
    page: int | None
    char_start: int
    char_end: int
    quote: str


class SavedClaim(Contract):
    text: str
    citations: list[SavedCitation]


class SavedAnswer(AskRequest):
    id: int
    provider_name: str
    provider_type: str
    requirement_name: str | None
    topic_hint: str | None
    jurisdiction: str
    as_of: date
    state: Literal["processing", "completed", "failed"]
    outcome: AnswerOutcome | None
    claims: list[SavedClaim]
    explanation: str | None
    missing_facts: str | None
    conflict_explanation: str | None
    failure_message: str | None
    corpus_revision: int
    embedding_space: EmbeddingSpace
    generation_model: str | None
    created_at: datetime
    completed_at: datetime | None
    outdated: bool
    historical_source_warning: str | None


class RankedPassage(Contract):
    chunk: KnowledgeChunk
    keyword_rank: int | None = None
    vector_rank: int | None = None
    fused_rank: int | None = None
    context_order: int | None = None
