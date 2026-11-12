"""Atomic application of one terminal manager decision."""

from uuid import UUID, uuid4

from app.database import DatabasePool
from app.models import ReviewDecision, ReviewRequest, StoredRequirement
from app.repository import RecordNotFound, connection
from app.repository.updates import fetch_update
from app.rules.review import ReviewConflict, resolve_review


class ReviewRepository:
    def __init__(self, pool: DatabasePool) -> None:
        self.pool = pool

    async def decide(
        self, suggestion_id: UUID, request: ReviewRequest
    ) -> ReviewDecision:
        async with connection(self.pool) as conn:
            row = await (
                await conn.execute(
                    "SELECT id,update_id,requirement_id FROM suggestions WHERE id=%s FOR UPDATE",
                    (suggestion_id,),
                )
            ).fetchone()
            if row is None:
                raise RecordNotFound("Suggestion not found.")
            update = await fetch_update(conn, row["update_id"])
            if update.processing_state != "completed":
                raise ReviewConflict("Analysis is unfinished and cannot be reviewed.")
            suggestion = next(s for s in update.suggestions if s.id == suggestion_id)
            current = await (
                await conn.execute(
                    "SELECT * FROM requirements WHERE id=%s FOR UPDATE",
                    (row["requirement_id"],),
                )
            ).fetchone()
            requirement = StoredRequirement.model_validate(current)
            change = resolve_review(requirement, suggestion, request)
            if change.outcome != "rejected":
                await conn.execute(
                    "UPDATE requirements SET status=%s,scheduled_date=%s,version=version+1 WHERE id=%s",
                    (
                        change.applied_status,
                        change.applied_scheduled_date,
                        requirement.id,
                    ),
                )
            decision = await (
                await conn.execute(
                    "INSERT INTO review_decisions(id,suggestion_id,outcome,previous_status,previous_scheduled_date,applied_status,applied_scheduled_date,reviewer_role) VALUES (%s,%s,%s,%s,%s,%s,%s,'manager') RETURNING *",
                    (
                        uuid4(),
                        suggestion_id,
                        change.outcome,
                        requirement.status,
                        requirement.scheduled_date,
                        change.applied_status,
                        change.applied_scheduled_date,
                    ),
                )
            ).fetchone()
            return ReviewDecision.model_validate(decision)
