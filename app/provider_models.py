"""Provider creation input and configured type-template catalog contracts."""

import re
from datetime import date
from typing import Annotated, Self
from uuid import UUID

from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    StringConstraints,
    model_validator,
)

from app.models import NonBlank, RecordId
from app.rules.catalog import template_fingerprint as fingerprint
from app.rules.statuses import GENERIC_ADDITIONAL_STATUSES, configured_status_catalog


def require_calendar_date(value: object) -> object:
    if type(value) is date or (
        isinstance(value, str) and re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value)
    ):
        return value
    raise ValueError("Use a calendar date in YYYY-MM-DD format.")


CalendarDate = Annotated[date, BeforeValidator(require_calendar_date)]


class AdditionalRequirementInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: NonBlank
    status: NonBlank
    scheduled_date: CalendarDate | None = None
    deadline: CalendarDate | None = None


class CreateProviderRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    creation_request_id: UUID
    name: NonBlank
    provider_type_id: RecordId
    checklist_template_id: RecordId
    template_fingerprint: Annotated[str, StringConstraints(pattern=r"^[a-f0-9]{64}$")]
    proposed_start_date: CalendarDate | None = None
    additional_requirements: list[AdditionalRequirementInput] = Field(
        default_factory=list
    )


class ProviderTypeTemplate(BaseModel):
    id: RecordId
    checklist_template_id: RecordId
    template_version: int
    name: str
    requirements: list[str]
    template_fingerprint: str = ""
    additional_statuses: list[str] = Field(default_factory=list)
    configured_statuses: dict[str, list[str]] = Field(default_factory=dict)

    @model_validator(mode="after")
    def derive_metadata(self) -> Self:
        self.template_fingerprint = fingerprint(
            self.id,
            self.checklist_template_id,
            self.template_version,
            self.requirements,
        )
        self.additional_statuses = list(GENERIC_ADDITIONAL_STATUSES)
        self.configured_statuses = configured_status_catalog(self.name)
        return self
