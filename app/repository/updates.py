"""Idempotent saved analysis lifecycle and immutable captured context."""

from typing import Any
from uuid import UUID, uuid4

from psycopg import AsyncConnection
from psycopg.types.json import Jsonb

from app.database import DatabasePool, DatabaseUnavailable
from app.models import (
    AnalyzeUpdateResponse,
    FailureCategory,
    SavedUpdate,
    StoredProvider,
    SubmitUpdateRequest,
    UpdateClaim,
)
from app.repository import RecordNotFound, connection
from app.repository.providers import fetch_provider

READ_UPDATE = """
SELECT u.*, COALESCE((
 SELECT jsonb_agg(to_jsonb(s) || jsonb_build_object('decision', to_jsonb(d)) ORDER BY s.created_at,s.id)
 FROM suggestions s LEFT JOIN review_decisions d ON d.suggestion_id=s.id
 WHERE s.update_id=u.id), '[]') AS suggestions
FROM updates u WHERE u.id=%s
"""


class UpdateConflict(ValueError):
    """A request ID is already processing or belongs to different input."""


async def fetch_update(
    conn: AsyncConnection[dict[str, Any]], update_id: UUID
) -> SavedUpdate:
    row = await (await conn.execute(READ_UPDATE, (update_id,))).fetchone()
    if row is None:
        raise RecordNotFound("Update not found.")
    snapshot = StoredProvider.model_validate(row["provider_snapshot"])
    names = {r.id: r.name for r in snapshot.requirements}
    for suggestion in row["suggestions"]:
        name = names.get(UUID(suggestion["requirement_id"]))
        if name is None:
            raise DatabaseUnavailable("Saved provider context is unavailable.")
        suggestion["requirement"] = name
    return SavedUpdate.model_validate({**row, "update_text": row["original_text"]})


class UpdateRepository:
    def __init__(self, pool: DatabasePool) -> None:
        self.pool = pool

    async def claim(self, request: SubmitUpdateRequest) -> UpdateClaim:
        async with connection(self.pool) as conn:
            existing = await (
                await conn.execute(
                    "SELECT id FROM updates WHERE request_id=%s", (request.request_id,)
                )
            ).fetchone()
            created = False
            if existing is None:
                snapshot = await fetch_provider(conn, request.provider_id)
                existing = await (
                    await conn.execute(
                        "INSERT INTO updates(id,request_id,provider_id,original_text,provider_snapshot,processing_state,message) VALUES (%s,%s,%s,%s,%s,'processing','Analysis is in progress.') ON CONFLICT(request_id) DO NOTHING RETURNING id",
                        (
                            uuid4(),
                            request.request_id,
                            request.provider_id,
                            request.update_text,
                            Jsonb(snapshot.model_dump(mode="json")),
                        ),
                    )
                ).fetchone()
                created = existing is not None
                if existing is None:
                    existing = await (
                        await conn.execute(
                            "SELECT id FROM updates WHERE request_id=%s",
                            (request.request_id,),
                        )
                    ).fetchone()
            if existing is None:
                raise UpdateConflict("Request changed concurrently. Please retry.")
            saved = await fetch_update(conn, existing["id"])
            if (
                saved.provider_id != request.provider_id
                or saved.update_text != request.update_text
            ):
                raise UpdateConflict("This request ID belongs to different input.")
            return UpdateClaim(created=created, update=saved)

    async def complete(
        self, update_id: UUID, result: AnalyzeUpdateResponse
    ) -> SavedUpdate:
        async with connection(self.pool) as conn:
            await conn.execute(
                "SELECT id FROM updates WHERE id=%s FOR UPDATE", (update_id,)
            )
            saved = await fetch_update(conn, update_id)
            if saved.processing_state != "processing":
                raise UpdateConflict("Analysis is already complete.")
            requirements = {r.name: r for r in saved.provider_snapshot.requirements}
            for suggestion in result.suggestions:
                requirement = requirements[suggestion.requirement]
                await conn.execute(
                    "INSERT INTO suggestions(id,update_id,requirement_id,provider_id,requirement_version,proposed_status,proposed_date,supporting_text,date_text,date_inferred,date_explanation,date_requires_confirmation) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                    (
                        uuid4(),
                        update_id,
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
            await conn.execute(
                "UPDATE updates SET processing_state='completed',message=%s,ambiguities=%s,completed_at=now() WHERE id=%s",
                (result.message, Jsonb(result.ambiguities), update_id),
            )
            return await fetch_update(conn, update_id)

    async def fail(self, update_id: UUID, category: FailureCategory) -> SavedUpdate:
        messages = {
            "configuration": "Model analysis is not configured.",
            "timeout": "Analysis timed out. Submit a new update to try again.",
            "model": "Unable to analyze update. Submit a new update to try again.",
        }
        async with connection(self.pool) as conn:
            await conn.execute(
                "UPDATE updates SET processing_state='failed',failure_category=%s,message=%s,completed_at=now() WHERE id=%s AND processing_state='processing'",
                (category, messages[category], update_id),
            )
            return await fetch_update(conn, update_id)

    async def get(self, update_id: UUID) -> SavedUpdate:
        async with connection(self.pool) as conn:
            return await fetch_update(conn, update_id)

    async def list_for_provider(self, provider_id: UUID) -> list[SavedUpdate]:
        async with connection(self.pool) as conn:
            await fetch_provider(conn, provider_id)
            ids = await (
                await conn.execute(
                    "SELECT id FROM updates WHERE provider_id=%s ORDER BY created_at DESC,id DESC",
                    (provider_id,),
                )
            ).fetchall()
            return [await fetch_update(conn, row["id"]) for row in ids]
