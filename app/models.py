"""Validated application records and transport contracts."""

from datetime import date, datetime
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StringConstraints,
    model_validator,
)


class Requirement(BaseModel):
    name: str
    status: str
    deadline: date | None = None


class ProviderContext(BaseModel):
    provider_id: str
    name: str
    provider_type: str
    proposed_start_date: date | None = None
    requirements: list[Requirement]


class AnalyzeUpdateRequest(BaseModel):
    provider: ProviderContext
    update_text: str


class SuggestedChange(BaseModel):
    requirement: str
    proposed_status: str
    proposed_date: date | None = None
    supporting_text: str
    date_text: str | None = None
    date_inferred: bool = False
    date_explanation: str | None = None
    date_requires_confirmation: bool = False


class AnalyzeUpdateResponse(BaseModel):
    message: str
    suggestions: list[SuggestedChange] = Field(default_factory=list)
    ambiguities: list[str] = Field(default_factory=list)


class StoredRequirement(Requirement):
    id: UUID
    provider_id: UUID
    source_template_id: UUID | None = None
    scheduled_date: date | None = None
    version: int = Field(ge=0)


class ProviderSummary(BaseModel):
    id: UUID
    name: str
    provider_type: str
    proposed_start_date: date | None = None


class StoredProvider(ProviderSummary):
    requirements: list[StoredRequirement]


def to_provider_context(provider: StoredProvider) -> ProviderContext:
    return ProviderContext(
        provider_id=str(provider.id),
        name=provider.name,
        provider_type=provider.provider_type,
        proposed_start_date=provider.proposed_start_date,
        requirements=[
            Requirement(name=r.name, status=r.status, deadline=r.deadline)
            for r in provider.requirements
        ],
    )


NonBlank = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
VerbatimStatus = Annotated[str, StringConstraints(pattern=r"\S")]
FailureCategory = Literal["configuration", "timeout", "model"]


class SubmitUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    provider_id: UUID
    request_id: UUID
    update_text: NonBlank


class ReviewDecision(BaseModel):
    id: UUID
    suggestion_id: UUID
    outcome: Literal["approved", "corrected", "rejected"]
    previous_status: str
    previous_scheduled_date: date | None
    applied_status: str | None
    applied_scheduled_date: date | None
    reviewer_role: Literal["manager"]
    reviewed_at: datetime


class SavedSuggestion(SuggestedChange):
    id: UUID
    requirement_id: UUID
    requirement_version: int = Field(ge=0)
    decision: ReviewDecision | None = None


class SavedUpdate(BaseModel):
    id: UUID
    request_id: UUID
    provider_id: UUID
    update_text: str
    provider_snapshot: StoredProvider
    processing_state: Literal["processing", "completed", "failed"]
    message: str
    suggestions: list[SavedSuggestion]
    ambiguities: list[str]
    failure_category: FailureCategory | None
    created_at: datetime
    completed_at: datetime | None


class UpdateClaim(BaseModel):
    created: bool
    update: SavedUpdate


DemoRole = Literal["proposer", "manager"]


class ReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: Literal["approve", "correct", "reject"]
    corrected_status: VerbatimStatus | None = None
    date_action: Literal["preserve", "set", "clear"] = "preserve"
    corrected_date: date | None = None
    date_confirmed: StrictBool = False

    @model_validator(mode="after")
    def validate_combination(self) -> Self:
        if self.action != "correct" and (
            self.corrected_status is not None
            or self.date_action != "preserve"
            or self.corrected_date is not None
        ):
            raise ValueError("Only corrected approvals accept edited fields.")
        if (
            self.action == "correct"
            and self.corrected_status is None
            and self.date_action == "preserve"
        ):
            raise ValueError("A corrected approval requires an edit.")
        if self.action == "reject" and self.date_confirmed:
            raise ValueError("Rejection cannot confirm a date.")
        if self.date_action == "set" and self.corrected_date is None:
            raise ValueError("Setting a date requires a valid date.")
        if self.date_action != "set" and self.corrected_date is not None:
            raise ValueError("A date value requires the set action.")
        return self


class ReviewChange(BaseModel):
    outcome: Literal["approved", "corrected", "rejected"]
    applied_status: str | None
    applied_scheduled_date: date | None
