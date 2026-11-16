"""Provider creation input and configured type-template catalog contracts."""

from datetime import date
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.models import NonBlank, RecordId


class CreateProviderRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    creation_request_id: UUID
    name: NonBlank
    provider_type_id: RecordId
    proposed_start_date: date | None = None


class ProviderTypeTemplate(BaseModel):
    id: RecordId
    checklist_template_id: RecordId
    template_version: int
    name: str
    requirements: list[str]
