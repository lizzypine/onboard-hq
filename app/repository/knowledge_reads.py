"""Consistent source catalog, retained evidence and scope-filtered corpus reads."""

from datetime import date
from typing import Any
from uuid import UUID

from psycopg import AsyncConnection

from app.database import DatabasePool
from app.knowledge_models import (
    CorpusSnapshot,
    EmbeddingSpace,
    KnowledgeChunk,
    KnowledgeDocument,
    KnowledgeScope,
    KnowledgeVersion,
    OperationReceipt,
    VersionSummary,
)
from app.repository import RecordNotFound, connection
from app.rules.knowledge import KnowledgeConflict

Conn = AsyncConnection[dict[str, Any]]
RECEIPT = "operation_id,action,version_id,draft_revision,corpus_revision,superseded_version_id,decided_at,role"
SUMMARY = "id,status,draft_revision,stated_revision"
CHUNK = "id,version_id,section,page,char_start,char_end,text"


async def row(conn: Conn, query: str, args: tuple = ()) -> dict[str, Any]:
    found = await (await conn.execute(query, args)).fetchone()
    if found is None:
        raise RecordNotFound("Knowledge record does not exist.")
    return found


async def state(conn: Conn, lock: bool = False) -> tuple[int, EmbeddingSpace]:
    found = await row(
        conn,
        "SELECT s.revision,e.* FROM knowledge_state s JOIN embedding_spaces e ON e.id=s.active_space_id WHERE singleton"
        + (" FOR UPDATE OF s" if lock else ""),
    )
    revision = found.pop("revision")
    return revision, EmbeddingSpace(**found)


async def version_read(conn: Conn, vid: int) -> KnowledgeVersion:
    base = await row(
        conn,
        "SELECT id,document_id,status,draft_revision,stated_revision,text,media_type,checksum,retrieved_at,reviewed_at,effective_from,effective_to FROM knowledge_versions WHERE id=%s",
        (vid,),
    )
    doc = KnowledgeDocument(
        **await row(
            conn,
            "SELECT * FROM knowledge_documents WHERE id=%s",
            (base["document_id"],),
        )
    )
    scopes = await (
        await conn.execute(
            "SELECT p.name AS provider_type,s.jurisdiction,s.topic FROM knowledge_scopes s JOIN provider_types p ON p.id=s.provider_type_id WHERE version_id=%s ORDER BY p.name,s.jurisdiction,s.topic",
            (vid,),
        )
    ).fetchall()
    issues = await (
        await conn.execute(
            "SELECT issue FROM knowledge_review_issues WHERE version_id=%s ORDER BY issue",
            (vid,),
        )
    ).fetchall()
    chunks = await (
        await conn.execute(
            f"SELECT {CHUNK} FROM knowledge_chunks WHERE version_id=%s ORDER BY char_start",
            (vid,),
        )
    ).fetchall()
    return KnowledgeVersion(
        **base,
        document=doc,
        scopes=[KnowledgeScope(**s) for s in scopes],
        review_issues=[i["issue"] for i in issues],
        chunks=[KnowledgeChunk(**c) for c in chunks],
    )


async def replay(conn: Conn, key: UUID, digest: str) -> OperationReceipt | None:
    saved = await (
        await conn.execute(
            f"SELECT {RECEIPT},request_hash FROM knowledge_publications WHERE operation_id=%s",
            (key,),
        )
    ).fetchone()
    if saved is None:
        return None
    if saved.pop("request_hash") != digest:
        raise KnowledgeConflict("Operation identity already used with different input.")
    return OperationReceipt(**saved)


class KnowledgeReads:
    def __init__(self, pool: DatabasePool):
        self.pool = pool

    async def list_documents(self) -> list[KnowledgeDocument]:
        async with connection(self.pool) as conn:
            await conn.execute(
                "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY"
            )
            docs = await (
                await conn.execute(
                    "SELECT * FROM knowledge_documents ORDER BY title,id"
                )
            ).fetchall()
            result = []
            for doc in docs:
                versions = await (
                    await conn.execute(
                        f"SELECT {SUMMARY} FROM knowledge_versions WHERE document_id=%s ORDER BY id DESC",
                        (doc["id"],),
                    )
                ).fetchall()
                result.append(
                    KnowledgeDocument(
                        **doc, versions=[VersionSummary(**v) for v in versions]
                    )
                )
            return result

    async def get_version(self, version_id: int) -> KnowledgeVersion:
        async with connection(self.pool) as conn:
            await conn.execute(
                "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY"
            )
            return await version_read(conn, version_id)

    async def original(self, vid: int) -> tuple[str, str, bytes]:
        async with connection(self.pool) as conn:
            v = await row(
                conn,
                "SELECT status,media_type,original FROM knowledge_versions WHERE id=%s",
                (vid,),
            )
            return v["status"], v["media_type"], v["original"]

    async def operation(self, key: UUID) -> OperationReceipt:
        async with connection(self.pool) as conn:
            return OperationReceipt(
                **await row(
                    conn,
                    f"SELECT {RECEIPT} FROM knowledge_publications WHERE operation_id=%s",
                    (key,),
                )
            )

    async def check_retry(self, key: UUID, digest: str) -> OperationReceipt | None:
        async with connection(self.pool) as conn:
            return await replay(conn, key, digest)

    async def prepare_publication(
        self, version_id: int, operation_id: UUID, digest: str
    ) -> OperationReceipt | tuple[KnowledgeVersion, EmbeddingSpace]:
        # A concurrent successful retry must not look like a stale draft.
        async with connection(self.pool) as conn:
            await conn.execute(
                "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY"
            )
            if saved := await replay(conn, operation_id, digest):
                return saved
            return await version_read(conn, version_id), (await state(conn))[1]

    async def current_space(self) -> EmbeddingSpace:
        async with connection(self.pool) as conn:
            return (await state(conn))[1]

    async def corpus_snapshot(
        self, provider_type: str, jurisdiction: str, as_of: date
    ) -> CorpusSnapshot:
        async with connection(self.pool) as conn:
            await conn.execute(
                "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY"
            )
            revision, space = await state(conn)
            ids = await (
                await conn.execute(
                    """SELECT v.id FROM knowledge_versions v WHERE status='published'
                AND (effective_from IS NULL OR effective_from<=%s) AND (effective_to IS NULL OR effective_to>=%s)
                AND EXISTS (SELECT FROM knowledge_scopes s JOIN provider_types p ON p.id=s.provider_type_id
                WHERE s.version_id=v.id AND p.name=%s AND s.jurisdiction=%s) ORDER BY v.id""",
                    (as_of, as_of, provider_type, jurisdiction),
                )
            ).fetchall()
            versions = [await version_read(conn, v["id"]) for v in ids]
            return CorpusSnapshot(
                revision=revision,
                active_space=space,
                versions=versions,
                chunks=[c for v in versions for c in v.chunks],
            )

    async def requirement_topics(self, provider_id: int) -> dict[int, list[str]]:
        async with connection(self.pool) as conn:
            rows = await (
                await conn.execute(
                    """SELECT r.id,l.topic FROM requirements r
                JOIN providers p ON p.id=r.provider_id JOIN checklist_templates c ON c.id=p.checklist_template_id
                JOIN requirement_knowledge_links l ON l.requirement_definition_id=r.requirement_definition_id
                AND l.provider_type_id=c.provider_type_id WHERE p.id=%s ORDER BY r.id,l.topic""",
                    (provider_id,),
                )
            ).fetchall()
            result: dict[int, list[str]] = {}
            for item in rows:
                result.setdefault(item["id"], []).append(item["topic"])
            return result
