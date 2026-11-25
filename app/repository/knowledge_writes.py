"""Source draft and immutable operation receipt persistence inside caller transactions."""

from uuid import UUID

from app.knowledge_models import DraftRequest, Extraction, Media, OperationReceipt
from app.repository.knowledge_reads import RECEIPT, Conn, row
from app.rules.knowledge import KnowledgeInvalid


async def receipt(
    conn: Conn,
    key: UUID,
    digest: str,
    action: str,
    vid: int,
    superseded: int | None = None,
) -> OperationReceipt:
    result = await row(
        conn,
        f"""INSERT INTO knowledge_publications(operation_id,request_hash,action,version_id,
        draft_revision,corpus_revision,superseded_version_id) SELECT %s,%s,%s,v.id,v.draft_revision,s.revision,%s
        FROM knowledge_versions v CROSS JOIN knowledge_state s WHERE v.id=%s RETURNING {RECEIPT}""",
        (key, digest, action, superseded, vid),
    )
    return OperationReceipt(**result)


async def replace_metadata(conn: Conn, vid: int, req: DraftRequest) -> None:
    await conn.execute(
        "DELETE FROM knowledge_review_issues WHERE version_id=%s", (vid,)
    )
    await conn.execute("DELETE FROM knowledge_scopes WHERE version_id=%s", (vid,))
    async with conn.cursor() as cur:
        await cur.executemany(
            "INSERT INTO knowledge_review_issues VALUES (%s,%s)",
            [(vid, issue) for issue in req.review_issues],
        )
    for scope in req.scopes:
        inserted = await conn.execute(
            """INSERT INTO knowledge_scopes SELECT %s,id,%s,%s FROM provider_types WHERE name=%s""",
            (vid, scope.jurisdiction, scope.topic, scope.provider_type),
        )
        if inserted.rowcount != 1:
            raise KnowledgeInvalid("The selected provider type is not configured.")


async def replace_chunks(conn: Conn, vid: int, parsed: Extraction) -> None:
    await conn.execute("DELETE FROM knowledge_chunks WHERE version_id=%s", (vid,))
    async with conn.cursor() as cur:
        await cur.executemany(
            """INSERT INTO knowledge_chunks(version_id,text,section,page,char_start,char_end)
            VALUES (%s,%s,%s,%s,%s,%s)""",
            [
                (vid, c.text, c.section, c.page, c.char_start, c.char_end)
                for c in parsed.chunks
            ],
        )


async def insert_draft(
    conn: Conn,
    doc: int,
    req: DraftRequest,
    raw: bytes,
    media: Media,
    parsed: Extraction,
) -> int:
    record = await row(
        conn,
        """INSERT INTO knowledge_versions(document_id,stated_revision,text,original,media_type,
        retrieved_at,effective_from,effective_to) VALUES (%s,%s,%s,%s,%s,now(),%s,%s) RETURNING id""",
        (
            doc,
            req.stated_revision,
            parsed.text,
            raw,
            media,
            req.effective_from,
            req.effective_to,
        ),
    )
    vid = int(record["id"])
    await replace_metadata(conn, vid, req)
    await replace_chunks(conn, vid, parsed)
    return vid
