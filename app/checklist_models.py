"""Direct checklist edit contracts, separate from model suggestions and reviews."""

from datetime import date, datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ChecklistEditRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: UUID
    expected_version: Annotated[int, Field(strict=True, ge=0)]
    status: str
    scheduled_date: date | None
    deadline: date | None

    @field_validator("status")
    @classmethod
    def nonblank_status(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("A status is required.")
        return value


class ChecklistEdit(BaseModel):
    id: UUID
    provider_id: UUID
    requirement_id: UUID
    requirement_name: str
    expected_version: int
    resulting_version: int
    previous_status: str
    previous_scheduled_date: date | None
    previous_deadline: date | None
    applied_status: str
    applied_scheduled_date: date | None
    applied_deadline: date | None
    reviewer_role: Literal["manager"]
    created_at: datetime


class RequirementEditOptions(BaseModel):
    requirement_id: UUID
    statuses: list[str]
    status_tone: Literal["finished", "progress", "attention", "unknown"]
