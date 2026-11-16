"""Locked atomic checklist edits with append-only retryable evidence."""

from app.checklist_models import ChecklistEdit, ChecklistEditRequest
from app.database import DatabasePool
from app.models import StoredRequirement
from app.repository import RecordNotFound, connection, lock_provider, lock_retry
from app.rules.checklist import require_edit, require_same_edit
from app.rules.provider_state import require_active
from db.queries import fetch_provider

EDIT_QUERY = """SELECT e.*,d.name AS requirement_name FROM checklist_edits e
 JOIN requirements r ON r.id=e.requirement_id
 JOIN requirement_definitions d ON d.id=r.requirement_definition_id"""


class ChecklistRepository:
    def __init__(self, pool: DatabasePool) -> None:
        self.pool = pool

    async def list_for_provider(self, provider_id: int) -> list[ChecklistEdit]:
        async with connection(self.pool) as conn:
            await fetch_provider(conn, provider_id)
            rows = await (
                await conn.execute(
                    EDIT_QUERY
                    + " WHERE e.provider_id=%s ORDER BY e.created_at DESC,e.id DESC",
                    (provider_id,),
                )
            ).fetchall()
            return [ChecklistEdit.model_validate(row) for row in rows]

    async def edit(
        self, provider_id: int, requirement_id: int, request: ChecklistEditRequest
    ) -> ChecklistEdit:
        async with connection(self.pool) as conn:
            await lock_retry(conn, request.operation_id)
            previous = await (
                await conn.execute(
                    EDIT_QUERY + " WHERE e.operation_id=%s", (request.operation_id,)
                )
            ).fetchone()
            if previous is not None:
                existing = ChecklistEdit.model_validate(previous)
                require_same_edit(existing, provider_id, requirement_id, request)
                return existing
            await lock_provider(conn, provider_id)
            provider = await fetch_provider(conn, provider_id)
            require_active(provider)
            row = await (
                await conn.execute(
                    """SELECT r.*,d.name FROM requirements r
                JOIN requirement_definitions d ON d.id=r.requirement_definition_id
                WHERE r.id=%s AND r.provider_id=%s FOR UPDATE OF r""",
                    (requirement_id, provider_id),
                )
            ).fetchone()
            if row is None:
                raise RecordNotFound("Requirement not found for this provider.")
            current = StoredRequirement.model_validate(row)
            require_edit(current, provider.provider_type, request)
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
                    """INSERT INTO checklist_edits
                (operation_id,provider_id,requirement_id,expected_version,resulting_version,
                 previous_status,previous_scheduled_date,previous_deadline,applied_status,
                 applied_scheduled_date,applied_deadline,reviewer_role)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'manager') RETURNING *""",
                    (
                        request.operation_id,
                        provider_id,
                        requirement_id,
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
            if event is None:
                raise RecordNotFound("Saved edit not found.")
            return ChecklistEdit.model_validate(
                {**event, "requirement_name": current.name}
            )
