"""Idempotent saved analysis lifecycle and normalized captured context."""

from typing import Any

from psycopg import AsyncConnection

from app.database import DatabasePool
from app.models import (
    AnalyzeUpdateResponse,
    FailureCategory,
    SavedUpdate,
    SubmitUpdateRequest,
    UpdateClaim,
)
from app.repository import RecordNotFound, connection, lock_provider, lock_retry
from app.repository.snapshots import load_snapshot, save_snapshot
from app.rules.provider_state import require_active
from db.queries import fetch_provider

READ_UPDATE = """
SELECT u.*, COALESCE((
 SELECT jsonb_agg(to_jsonb(s) || jsonb_build_object('decision',to_jsonb(d),'requirement',n.name) ORDER BY s.created_at,s.id)
 FROM suggestions s JOIN requirements r ON r.id=s.requirement_id
 JOIN requirement_definitions n ON n.id=r.requirement_definition_id
 LEFT JOIN review_decisions d ON d.suggestion_id=s.id WHERE s.update_id=u.id),'[]') AS suggestions,
 ARRAY(SELECT a.message FROM update_ambiguities a WHERE a.update_id=u.id ORDER BY a.id) AS ambiguities
FROM updates u WHERE u.id=%s
"""


class UpdateConflict(ValueError):
    """A request ID is already processing or belongs to different input."""


async def fetch_update(
    conn: AsyncConnection[dict[str, Any]], update_id: int
) -> SavedUpdate:
    row = await (await conn.execute(READ_UPDATE, (update_id,))).fetchone()
    if row is None:
        raise RecordNotFound("Update not found.")
    snapshot = await load_snapshot(conn, update_id)
    return SavedUpdate.model_validate(
        {**row, "update_text": row["original_text"], "provider_snapshot": snapshot}
    )


async def lock_update(conn: AsyncConnection[dict[str, Any]], update_id: int) -> None:
    owner = await (
        await conn.execute("SELECT provider_id FROM updates WHERE id=%s", (update_id,))
    ).fetchone()
    if owner is None:
        raise RecordNotFound("Update not found.")
    await lock_provider(conn, owner["provider_id"])
    await conn.execute("SELECT id FROM updates WHERE id=%s FOR UPDATE", (update_id,))


async def insert_suggestions(
    conn: AsyncConnection[dict[str, Any]],
    saved: SavedUpdate,
    result: AnalyzeUpdateResponse,
) -> None:
    requirements = {r.name: r for r in saved.provider_snapshot.requirements}
    for suggestion in result.suggestions:
        requirement = requirements[suggestion.requirement]
        await conn.execute(
            """INSERT INTO suggestions(update_id,requirement_id,provider_id,
            requirement_version,proposed_status,proposed_date,supporting_text,date_text,
            date_inferred,date_explanation,date_requires_confirmation)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (
                saved.id,
                requirement.id,
                saved.provider_id,
                requirement.version,
                suggestion.proposed_status,
                suggestion.proposed_date,
                suggestion.supporting_text,
                suggestion.date_text,
                suggestion.date_inferred,
                suggestion.date_explanation,
                suggestion.date_requires_confirmation,
            ),
        )
    for message in result.ambiguities:
        await conn.execute(
            "INSERT INTO update_ambiguities(update_id,message) VALUES (%s,%s)",
            (saved.id, message),
        )


class UpdateRepository:
    def __init__(self, pool: DatabasePool) -> None:
        self.pool = pool

    async def claim(self, request: SubmitUpdateRequest) -> UpdateClaim:
        async with connection(self.pool) as conn:
            await lock_retry(conn, request.request_id)
            existing = await (
                await conn.execute(
                    "SELECT id FROM updates WHERE request_id=%s", (request.request_id,)
                )
            ).fetchone()
            created = existing is None
            if existing is None:
                await lock_provider(conn, request.provider_id)
                provider = await fetch_provider(conn, request.provider_id)
                require_active(provider)
                existing = await (
                    await conn.execute(
                        """INSERT INTO updates
                    (request_id,provider_id,original_text,processing_state,message)
                    VALUES (%s,%s,%s,'processing','Analysis is in progress.') RETURNING id""",
                        (request.request_id, request.provider_id, request.update_text),
                    )
                ).fetchone()
                if existing is None:
                    raise UpdateConflict("Request changed concurrently. Please retry.")
                await save_snapshot(conn, existing["id"], provider)
            saved = await fetch_update(conn, existing["id"])
            if (
                saved.provider_id != request.provider_id
                or saved.update_text != request.update_text
            ):
                raise UpdateConflict("This request ID belongs to different input.")
            return UpdateClaim(created=created, update=saved)

    async def complete(
        self, update_id: int, result: AnalyzeUpdateResponse
    ) -> SavedUpdate:
        async with connection(self.pool) as conn:
            await lock_update(conn, update_id)
            saved = await fetch_update(conn, update_id)
            if saved.processing_state != "processing":
                raise UpdateConflict("Analysis is already complete.")
            await insert_suggestions(conn, saved, result)
            await conn.execute(
                "UPDATE updates SET processing_state='completed',message=%s,completed_at=now() WHERE id=%s",
                (result.message, update_id),
            )
            return await fetch_update(conn, update_id)

    async def fail(self, update_id: int, category: FailureCategory) -> SavedUpdate:
        messages = {
            "configuration": "Model analysis is not configured.",
            "timeout": "Analysis timed out. Submit a new update to try again.",
            "model": "Unable to analyze update. Submit a new update to try again.",
        }
        async with connection(self.pool) as conn:
            await lock_update(conn, update_id)
            await conn.execute(
                "UPDATE updates SET processing_state='failed',failure_category=%s,message=%s,completed_at=now() WHERE id=%s AND processing_state='processing'",
                (category, messages[category], update_id),
            )
            return await fetch_update(conn, update_id)

    async def get(self, update_id: int) -> SavedUpdate:
        async with connection(self.pool) as conn:
            return await fetch_update(conn, update_id)

    async def list_for_provider(self, provider_id: int) -> list[SavedUpdate]:
        async with connection(self.pool) as conn:
            await fetch_provider(conn, provider_id)
            rows = await (
                await conn.execute(
                    "SELECT id FROM updates WHERE provider_id=%s ORDER BY created_at DESC,id DESC",
                    (provider_id,),
                )
            ).fetchall()
            return [await fetch_update(conn, row["id"]) for row in rows]
