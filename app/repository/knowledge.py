"""Short, locked source transactions with stable operation retries."""

from uuid import UUID

from app.embeddings import validate_vectors
from app.knowledge_models import (
    DraftRequest,
    EditDraftRequest,
    EmbeddingSpace,
    Extraction,
    KnowledgeChunk,
    Media,
    OperationReceipt,
    PublishRequest,
    SourceIdentity,
    WithdrawRequest,
)
from app.repository import connection, lock_retry
from app.repository.knowledge_reads import (
    CHUNK,
    Conn,
    KnowledgeReads,
    replay,
    row,
    state,
    version_read,
)
from app.repository.knowledge_writes import (
    insert_draft,
    receipt,
    replace_chunks,
    replace_metadata,
)
from app.rules.knowledge import (
    KnowledgeConflict,
    KnowledgeInvalid,
    require_publishable,
    require_revision,
)


async def locked_replay(conn: Conn, key: UUID, digest: str) -> OperationReceipt | None:
    await lock_retry(conn, key)
    return await replay(conn, key, digest)


async def store_vectors(
    conn: Conn,
    space: EmbeddingSpace,
    chunks: list[KnowledgeChunk],
    vectors: list[list[float]],
) -> None:
    validate_vectors(vectors, len(chunks), space.dimensions)
    async with conn.cursor() as cur:
        await cur.executemany(
            """INSERT INTO knowledge_embeddings(chunk_id,space_id,dimensions,embedding)
            VALUES (%s,%s,%s,%s::vector) ON CONFLICT (chunk_id,space_id) DO NOTHING""",
            [
                (c.id, space.id, space.dimensions, str(v))
                for c, v in zip(chunks, vectors, strict=True)
            ],
        )


class KnowledgeRepository(KnowledgeReads):
    async def create_draft(
        self,
        doc: int,
        req: DraftRequest,
        raw: bytes,
        media: Media,
        parsed: Extraction,
        digest: str,
        source: SourceIdentity | None = None,
    ) -> OperationReceipt:
        async with connection(self.pool) as conn:
            if saved := await locked_replay(conn, req.operation_id, digest):
                return saved
            if source:
                await conn.execute(
                    """INSERT INTO knowledge_documents(source_key,title,source_kind,publisher,original_url)
                    VALUES (%s,%s,%s,%s,%s) ON CONFLICT(source_key) DO NOTHING""",
                    (
                        source.source_key,
                        source.title,
                        "official" if source.url else "internal",
                        source.publisher,
                        source.url,
                    ),
                )
                d = await row(
                    conn,
                    "SELECT * FROM knowledge_documents WHERE source_key=%s",
                    (source.source_key,),
                )
                if (
                    d["original_url"] != source.url
                    or d["title"] != source.title
                    or d["publisher"] != source.publisher
                ):
                    raise KnowledgeConflict(
                        "The configured source identity changed. Register a new source key."
                    )
                doc = d["id"]
            else:
                d = await row(
                    conn,
                    "SELECT source_kind FROM knowledge_documents WHERE id=%s",
                    (doc,),
                )
                if d["source_kind"] != "internal":
                    raise KnowledgeInvalid(
                        "Use controlled ingestion for official sources."
                    )
            vid = await insert_draft(conn, doc, req, raw, media, parsed)
            return await receipt(conn, req.operation_id, digest, "create", vid)

    async def edit_draft(
        self, vid: int, req: EditDraftRequest, parsed: Extraction | None, digest: str
    ) -> OperationReceipt:
        async with connection(self.pool) as conn:
            if saved := await locked_replay(conn, req.operation_id, digest):
                return saved
            await row(
                conn, "SELECT id FROM knowledge_versions WHERE id=%s FOR UPDATE", (vid,)
            )
            v = await version_read(conn, vid)
            require_revision(v, req.expected_revision, "draft")
            if req.text != v.text:
                if v.document.source_kind != "internal" or parsed is None:
                    raise KnowledgeInvalid(
                        "Official extracted text must match its retained original."
                    )
                await conn.execute(
                    "UPDATE knowledge_versions SET original=%s,text=%s WHERE id=%s",
                    (req.text.encode(), parsed.text, vid),
                )
                await replace_chunks(conn, vid, parsed)
            await conn.execute(
                """UPDATE knowledge_versions SET stated_revision=%s,effective_from=%s,effective_to=%s,
                draft_revision=draft_revision+1 WHERE id=%s""",
                (req.stated_revision, req.effective_from, req.effective_to, vid),
            )
            await replace_metadata(conn, vid, req)
            return await receipt(conn, req.operation_id, digest, "edit", vid)

    async def publish(
        self,
        vid: int,
        req: PublishRequest,
        digest: str,
        space: EmbeddingSpace,
        vectors: list[list[float]],
    ) -> OperationReceipt:
        async with connection(self.pool) as conn:
            if saved := await locked_replay(conn, req.operation_id, digest):
                return saved
            _, active = await state(conn, True)
            if active != space:
                raise KnowledgeConflict(
                    "The embedding space changed during publication."
                )
            await row(
                conn, "SELECT id FROM knowledge_versions WHERE id=%s FOR UPDATE", (vid,)
            )
            v = await version_read(conn, vid)
            require_revision(v, req.expected_revision, "draft")
            require_publishable(v, req.confirmed_review)
            await store_vectors(conn, space, v.chunks, vectors)
            previous = await (
                await conn.execute(
                    "UPDATE knowledge_versions SET status='superseded' WHERE document_id=%s AND status='published' RETURNING id",
                    (v.document_id,),
                )
            ).fetchone()
            await conn.execute(
                "UPDATE knowledge_versions SET status='published',reviewed_at=now() WHERE id=%s",
                (vid,),
            )
            await conn.execute("UPDATE knowledge_state SET revision=revision+1")
            return await receipt(
                conn,
                req.operation_id,
                digest,
                "publish",
                vid,
                previous["id"] if previous else None,
            )

    async def withdraw(
        self, vid: int, req: WithdrawRequest, digest: str
    ) -> OperationReceipt:
        async with connection(self.pool) as conn:
            if saved := await locked_replay(conn, req.operation_id, digest):
                return saved
            await state(conn, True)
            v = await version_read(conn, vid)
            require_revision(v, req.expected_revision, "published")
            await conn.execute(
                "UPDATE knowledge_versions SET status='withdrawn' WHERE id=%s", (vid,)
            )
            await conn.execute("UPDATE knowledge_state SET revision=revision+1")
            return await receipt(conn, req.operation_id, digest, "withdraw", vid)

    async def prepare_space(
        self, model: str, version: str, dimensions: int
    ) -> tuple[int, EmbeddingSpace, list[KnowledgeChunk]]:
        async with connection(self.pool) as conn:
            rev, _ = await state(conn, True)
            args = (model, version, dimensions)
            await conn.execute(
                "INSERT INTO embedding_spaces(model,version,dimensions) VALUES (%s,%s,%s) ON CONFLICT DO NOTHING",
                args,
            )
            space = EmbeddingSpace(
                **await row(
                    conn,
                    "SELECT * FROM embedding_spaces WHERE model=%s AND version=%s AND dimensions=%s",
                    args,
                )
            )
            chunks = await (
                await conn.execute(
                    f"""SELECT {CHUNK} FROM knowledge_chunks c WHERE EXISTS(
                SELECT FROM knowledge_versions v WHERE v.id=c.version_id AND v.status='published')
                AND NOT EXISTS (SELECT FROM knowledge_embeddings e WHERE e.chunk_id=c.id AND e.space_id=%s)
                ORDER BY c.id""",
                    (space.id,),
                )
            ).fetchall()
            return rev, space, [KnowledgeChunk(**c) for c in chunks]

    async def activate_space(
        self,
        revision: int,
        space: EmbeddingSpace,
        chunks: list[KnowledgeChunk],
        vectors: list[list[float]],
    ) -> None:
        async with connection(self.pool) as conn:
            current, active = await state(conn, True)
            if current != revision:
                raise KnowledgeConflict(
                    "Published sources changed during reindex. Start the reindex again."
                )
            if active == space:
                return
            await store_vectors(conn, space, chunks, vectors)
            incomplete = await (
                await conn.execute(
                    """SELECT FROM knowledge_chunks c JOIN knowledge_versions v ON v.id=c.version_id
                WHERE v.status='published' AND NOT EXISTS(SELECT FROM knowledge_embeddings e WHERE e.chunk_id=c.id AND e.space_id=%s) LIMIT 1""",
                    (space.id,),
                )
            ).fetchone()
            if incomplete is not None:
                raise KnowledgeConflict("The new space has incomplete passages.")
            await conn.execute(
                "UPDATE knowledge_state SET active_space_id=%s,revision=revision+1",
                (space.id,),
            )
