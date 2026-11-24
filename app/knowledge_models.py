"""Contracts for reviewed source versions, exact passage locators and corpus snapshots."""

from datetime import date, datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

Label = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)
]
Status = Literal["draft", "published", "superseded", "withdrawn"]
Media = Literal["text/plain", "text/html", "application/pdf"]


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SourceIdentity(Contract):
    source_key: str
    title: str
    publisher: str
    url: str | None
    media_type: Media
    topic: str


class KnowledgeScope(Contract):
    provider_type: Label
    jurisdiction: Label
    topic: Label


class SourceReviewOptions(Contract):
    topics: list[str]
    default_scope: KnowledgeScope


class Passage(Contract):
    text: str
    section: str
    page: int | None = None
    char_start: int
    char_end: int


class Extraction(Contract):
    text: str
    chunks: list[Passage]


class KnowledgeChunk(Passage):
    id: int
    version_id: int


class VersionSummary(Contract):
    id: int
    status: Status
    draft_revision: int
    stated_revision: str | None


class KnowledgeDocument(Contract):
    id: int
    source_key: str
    title: str
    source_kind: Literal["official", "internal"]
    publisher: str
    original_url: str | None
    versions: list[VersionSummary] = Field(default_factory=list)


class KnowledgeVersion(VersionSummary):
    document_id: int
    document: KnowledgeDocument
    text: str
    media_type: Media
    checksum: str
    retrieved_at: datetime
    reviewed_at: datetime | None
    effective_from: date | None
    effective_to: date | None
    scopes: list[KnowledgeScope]
    review_issues: list[str]
    chunks: list[KnowledgeChunk]


class DraftRequest(Contract):
    operation_id: UUID
    text: Annotated[str, Field(min_length=1, max_length=2_000_000)]
    stated_revision: Label | None = None
    scopes: Annotated[list[KnowledgeScope], Field(min_length=1, max_length=128)]
    review_issues: Annotated[list[Label], Field(max_length=100)] = Field(
        default_factory=list
    )
    effective_from: date | None = None
    effective_to: date | None = None

    @model_validator(mode="after")
    def validate_metadata(self):
        if not self.text.strip() or (
            self.effective_from
            and self.effective_to
            and self.effective_to < self.effective_from
        ):
            raise ValueError("Provide nonblank text and an ordered effective period.")
        if len({s.model_dump_json() for s in self.scopes}) != len(self.scopes) or len(
            set(self.review_issues)
        ) != len(self.review_issues):
            raise ValueError("Scopes and review issues must be distinct.")
        return self


class EditDraftRequest(DraftRequest):
    expected_revision: Annotated[int, Field(gt=0)]


class WithdrawRequest(Contract):
    operation_id: UUID
    expected_revision: Annotated[int, Field(gt=0)]


class PublishRequest(WithdrawRequest):
    confirmed_review: bool


class OperationReceipt(Contract):
    operation_id: UUID
    action: Literal["create", "edit", "publish", "withdraw"]
    version_id: int
    draft_revision: int
    corpus_revision: int
    superseded_version_id: int | None
    decided_at: datetime
    role: Literal["manager"]


class EmbeddingSpace(Contract):
    id: int
    model: str
    version: str
    dimensions: int


class CorpusSnapshot(Contract):
    revision: int
    active_space: EmbeddingSpace
    versions: list[KnowledgeVersion]
    chunks: list[KnowledgeChunk]
