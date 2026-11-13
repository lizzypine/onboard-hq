"""Provider creation input and configured type-template catalog contracts."""

from datetime import date
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.models import NonBlank


class CreateProviderRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: UUID
    name: NonBlank
    provider_type_id: UUID
    proposed_start_date: date | None = None


class ProviderTypeTemplate(BaseModel):
    id: UUID
    name: str
    requirements: list[str]
