"""Locked, atomic requirement changes with append-only retryable audit evidence."""

from uuid import UUID

from app.checklist_models import ChecklistEdit, ChecklistEditRequest
from app.database import DatabasePool
from app.models import StoredRequirement
from app.repository import RecordNotFound, connection
from app.repository.providers import fetch_provider
from app.rules.checklist import require_edit, require_same_edit


class ChecklistRepository:
    def __init__(self, pool: DatabasePool) -> None:
        self.pool = pool

    async def list_for_provider(self, provider_id: UUID) -> list[ChecklistEdit]:
        async with connection(self.pool) as conn:
            await fetch_provider(conn, provider_id)
            rows = await (
                await conn.execute(
                    "SELECT * FROM checklist_edits WHERE provider_id=%s ORDER BY created_at DESC,id DESC",
                    (provider_id,),
                )
            ).fetchall()
            return [ChecklistEdit.model_validate(row) for row in rows]

    async def edit(
        self, provider_id: UUID, requirement_id: UUID, request: ChecklistEditRequest
    ) -> ChecklistEdit:
        async with connection(self.pool) as conn:
            lock_key = int.from_bytes(request.id.bytes[:8], "big", signed=True)
            await conn.execute("SELECT pg_advisory_xact_lock(%s)", (lock_key,))
            previous = await (
                await conn.execute(
                    "SELECT * FROM checklist_edits WHERE id=%s", (request.id,)
                )
            ).fetchone()
            if previous is not None:
                existing = ChecklistEdit.model_validate(previous)
                require_same_edit(existing, provider_id, requirement_id, request)
                return existing
            row = await (
                await conn.execute(
                    "SELECT r.*,t.name AS provider_type FROM requirements r JOIN providers p ON p.id=r.provider_id JOIN provider_types t ON t.id=p.provider_type_id WHERE r.id=%s AND r.provider_id=%s FOR UPDATE OF r",
                    (requirement_id, provider_id),
                )
            ).fetchone()
            if row is None:
                raise RecordNotFound("Requirement not found for this provider.")
            current = StoredRequirement.model_validate(row)
            require_edit(current, row["provider_type"], request)
            await conn.execute(
                "UPDATE requirements SET status=%s,scheduled_date=%s,deadline=%s,version=version+1 WHERE id=%s",
                (
                    request.status,
                    request.scheduled_date,
                    request.deadline,
                    requirement_id,
                ),
            )
            event = await (
                await conn.execute(
                    "INSERT INTO checklist_edits(id,provider_id,requirement_id,requirement_name,expected_version,resulting_version,previous_status,previous_scheduled_date,previous_deadline,applied_status,applied_scheduled_date,applied_deadline,reviewer_role) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'manager') RETURNING *",
                    (
                        request.id,
                        provider_id,
                        requirement_id,
                        current.name,
                        current.version,
                        current.version + 1,
                        current.status,
                        current.scheduled_date,
                        current.deadline,
                        request.status,
                        request.scheduled_date,
                        request.deadline,
                    ),
                )
            ).fetchone()
            return ChecklistEdit.model_validate(event)
