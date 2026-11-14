"""Derived dashboard contracts, kept separate from stored evidence."""

from datetime import date
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from app.checklist_models import RequirementEditOptions
from app.models import StoredProvider

Completion = Literal["finished", "outstanding", "needs_review"]
DeadlineState = Literal["not_set", "upcoming", "due_today", "past"]


class RequirementMonitoring(BaseModel):
    requirement_id: UUID
    completion: Completion
    deadline_state: DeadlineState


class MonitoringCounts(BaseModel):
    total: int = Field(ge=0)
    finished: int = Field(ge=0)
    remaining: int = Field(ge=0)
    overdue: int = Field(ge=0)
    needs_review: int = Field(ge=0)


class ProviderMonitoring(BaseModel):
    as_of_date: date
    time_zone: Literal["Pacific/Honolulu"] = "Pacific/Honolulu"
    requirements: list[RequirementMonitoring]
    counts: MonitoringCounts


class ProviderDashboard(BaseModel):
    provider: StoredProvider
    monitoring: ProviderMonitoring
    checklist_options: list[RequirementEditOptions]
