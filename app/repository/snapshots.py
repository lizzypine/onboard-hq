"""Normalized immutable analysis-context capture and reconstruction."""

from typing import Any

from psycopg import AsyncConnection

from app.models import CapturedProvider, StoredProvider
from app.repository import RecordNotFound


async def save_snapshot(
    conn: AsyncConnection[dict[str, Any]], update_id: int, provider: StoredProvider
) -> None:
    for requirement in provider.requirements:
        await conn.execute(
            """INSERT INTO update_requirement_snapshots
            (update_id,requirement_id,provider_id,status,scheduled_date,deadline,requirement_version)
            VALUES (%s,%s,%s,%s,%s,%s,%s)""",
            (
                update_id,
                requirement.id,
                provider.id,
                requirement.status,
                requirement.scheduled_date,
                requirement.deadline,
                requirement.version,
            ),
        )


async def load_snapshot(
    conn: AsyncConnection[dict[str, Any]], update_id: int
) -> CapturedProvider:
    profile = await (
        await conn.execute(
            """SELECT p.id,p.creation_request_id,p.name,
        p.checklist_template_id,p.proposed_start_date,t.name AS provider_type,c.template_version
        FROM updates u JOIN providers p ON p.id=u.provider_id
        JOIN checklist_templates c ON c.id=p.checklist_template_id
        JOIN provider_types t ON t.id=c.provider_type_id WHERE u.id=%s""",
            (update_id,),
        )
    ).fetchone()
    if profile is None:
        raise RecordNotFound("Update not found.")
    requirements = await (
        await conn.execute(
            """SELECT r.id,r.provider_id,r.checklist_template_id,
        r.requirement_definition_id,d.name,s.status,s.scheduled_date,s.deadline,s.requirement_version AS version
        FROM update_requirement_snapshots s JOIN requirements r ON r.id=s.requirement_id
        JOIN requirement_definitions d ON d.id=r.requirement_definition_id
        WHERE s.update_id=%s ORDER BY d.name,r.id""",
            (update_id,),
        )
    ).fetchall()
    return CapturedProvider.model_validate({**profile, "requirements": requirements})
