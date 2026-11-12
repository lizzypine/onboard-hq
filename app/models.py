"""Validated application records and transport contracts."""

from datetime import date
from uuid import UUID

from pydantic import BaseModel, Field


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
