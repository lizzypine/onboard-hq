"""Update request and output models; agent implementation is deferred."""

from datetime import date

from pydantic import BaseModel, Field


class Requirement(BaseModel):
    """A provider's current onboarding requirement."""

    name: str
    status: str
    deadline: date | None = None


class ProviderContext(BaseModel):
    """Synthetic provider details supplied with an update."""

    provider_id: str
    name: str
    provider_type: str
    proposed_start_date: date | None = None
    requirements: list[Requirement]


class AnalyzeUpdateRequest(BaseModel):
    """The selected provider context and original free-text update."""

    provider: ProviderContext
    update_text: str


class SuggestedChange(BaseModel):
    """A proposed change presented for human review."""

    requirement: str
    proposed_status: str
    proposed_date: date | None = None
    supporting_text: str


class AnalyzeUpdateResponse(BaseModel):
    """Suggested changes and ambiguities displayed by the page."""

    message: str
    suggestions: list[SuggestedChange] = Field(default_factory=list)
    ambiguities: list[str] = Field(default_factory=list)
