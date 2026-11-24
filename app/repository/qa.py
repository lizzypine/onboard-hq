"""Persist captured questions and answer evidence with short database transactions."""

from dataclasses import dataclass
from datetime import date
from uuid import UUID

from app.database import DatabasePool
from app.knowledge_models import CorpusSnapshot, EmbeddingSpace
from app.qa_models import (
    AnswerDraft,
    AskRequest,
    RankedPassage,
    SavedAnswer,
    SavedCitation,
    SavedClaim,
)
from app.repository import RecordNotFound, connection, lock_retry
from app.repository.knowledge_reads import (
    ELIGIBLE_VERSIONS,
    Conn,
    eligible_version_ids,
    row,
    snapshot_of,
    state,
)
from app.retrieval import PATH_LIMIT, merge_paths
from app.rules.qa import (
    QuestionConflict,
    QuestionScopeError,
    mismatched_type,
    question_topics,
)

JURISDICTION = "HI"
FAILURE_MESSAGE = "Licensing guidance is temporarily unavailable."
HISTORICAL_WARNING = (
    "This answer used earlier approved guidance. Ask again for current guidance."
)

# The same current eligibility definition used at capture also flags effective
# dates crossing a Hawaii calendar boundary without a corpus publication.
CURRENT_ELIGIBILITY = (
    ELIGIBLE_VERSIONS.replace("%(as_of)s", "%s")
    .replace("%(provider_type)s", "r.provider_type")
    .replace("%(jurisdiction)s", "r.jurisdiction")
    .replace("%(topics)s", "ARRAY(SELECT topic FROM qa_run_topics WHERE run_id=r.id)")
)
ANSWER_SELECT = f"""
SELECT r.id,r.request_id,r.provider_id,r.provider_name,r.provider_type,r.requirement_id,
    r.requirement_name,r.topic_hint,r.jurisdiction,r.question,r.as_of,r.state,r.outcome,
    r.explanation,r.missing_facts,r.conflict_explanation,r.failure_message,r.corpus_revision,
    r.generation_model,r.created_at,r.completed_at,
    e.id AS space_id,e.model,e.version,e.dimensions,
    (r.became_outdated OR r.corpus_revision<>s.revision OR
        ARRAY({CURRENT_ELIGIBILITY} ORDER BY v.id) <>
        ARRAY(SELECT version_id FROM qa_corpus_versions WHERE run_id=r.id ORDER BY version_id)
    ) AS outdated
FROM qa_runs r JOIN embedding_spaces e ON e.id=r.embedding_space_id CROSS JOIN knowledge_state s
"""


@dataclass(frozen=True)
class ClaimedQuestion:
    id: int
    provider_type: str
    requirement_name: str | None
    topic_hint: str | None
    revision: int
    space: EmbeddingSpace
    version_ids: list[int]
    mismatch: str | None


async def _provider_context(
    conn: Conn, request: AskRequest, type_id: int
) -> tuple[str | None, str | None]:
    if request.requirement_id is None:
        return None, None
    requirement = await (
        await conn.execute(
            """
            SELECT d.name,
                (SELECT min(l.topic) FROM requirement_knowledge_links l
                    WHERE l.provider_type_id=%s AND l.requirement_definition_id=d.id) AS topic
            FROM requirements r JOIN requirement_definitions d ON d.id=r.requirement_definition_id
            WHERE r.id=%s AND r.provider_id=%s
            """,
            (type_id, request.requirement_id, request.provider_id),
        )
    ).fetchone()
    if requirement is None:
        raise QuestionScopeError(
            "The requirement does not belong to the selected provider."
        )
    return requirement["name"], requirement["topic"]


async def _claims(conn: Conn, run_id: int) -> list[SavedClaim]:
    evidence = await (
        await conn.execute(
            """
            SELECT a.position,a.text AS claim,e.chunk_id,e.quote,
                c.char_start+e.quote_start AS char_start,c.char_start+e.quote_end AS char_end,
                c.page,c.section,c.version_id,v.document_id,v.stated_revision,
                v.checksum AS source_checksum,v.retrieved_at,v.reviewed_at,v.effective_from,v.effective_to,
                d.source_key,d.title AS source_title,d.source_kind,d.publisher,d.original_url
            FROM qa_claims a JOIN qa_citations e ON e.run_id=a.run_id AND e.claim_position=a.position
            JOIN knowledge_chunks c ON c.id=e.chunk_id
            JOIN knowledge_versions v ON v.id=c.version_id JOIN knowledge_documents d ON d.id=v.document_id
            WHERE a.run_id=%s ORDER BY a.position,e.position
            """,
            (run_id,),
        )
    ).fetchall()
    claims: dict[int, SavedClaim] = {}
    for item in evidence:
        position, claim = item.pop("position"), item.pop("claim")
        saved_claim = claims.setdefault(position, SavedClaim(text=claim, citations=[]))
        saved_claim.citations.append(SavedCitation(**item))
    return list(claims.values())


async def _answers(
    conn: Conn, where: str, key: int | UUID, as_of: date
) -> list[SavedAnswer]:
    records = await (
        await conn.execute(
            ANSWER_SELECT + where + " ORDER BY r.created_at DESC,r.id DESC",
            (as_of, as_of, key),
        )
    ).fetchall()
    results = []
    for record in records:
        space = EmbeddingSpace(
            id=record.pop("space_id"),
            model=record.pop("model"),
            version=record.pop("version"),
            dimensions=record.pop("dimensions"),
        )
        # A processing retry can race a terminal commit after the run SELECT.
        results.append(
            SavedAnswer(
                **record,
                embedding_space=space,
                claims=await _claims(conn, record["id"])
                if record["state"] == "completed"
                else [],
                historical_source_warning=HISTORICAL_WARNING
                if record["outdated"]
                else None,
            )
        )
    return results


async def _insert_claims(conn: Conn, run_id: int, draft: AnswerDraft) -> None:
    for index, claim in enumerate(draft.claims, 1):
        await conn.execute(
            "INSERT INTO qa_claims(run_id,position,text) VALUES (%s,%s,%s)",
            (run_id, index, claim.text),
        )
        async with conn.cursor() as cursor:
            await cursor.executemany(
                """
                INSERT INTO qa_citations(run_id,claim_position,position,chunk_id,context_order,quote,quote_start,quote_end)
                VALUES (%s,%s,%s,%s,
                    (SELECT context_order FROM qa_retrieved_chunks WHERE run_id=%s AND chunk_id=%s),%s,%s,%s)
                """,
                [
                    (
                        run_id,
                        index,
                        pos,
                        cite.chunk_id,
                        run_id,
                        cite.chunk_id,
                        cite.quote,
                        cite.start,
                        cite.end,
                    )
                    for pos, cite in enumerate(claim.citations, 1)
                ],
            )


class QARepository:
    def __init__(self, pool: DatabasePool):
        self.pool = pool

    async def claim(
        self, request: AskRequest, as_of: date
    ) -> SavedAnswer | ClaimedQuestion:
        async with connection(self.pool) as conn:
            await lock_retry(conn, request.request_id)
            prior = await _answers(
                conn, "WHERE r.request_id=%s", request.request_id, as_of
            )
            if prior:
                saved = prior[0]
                if (saved.provider_id, saved.requirement_id, saved.question) != (
                    request.provider_id,
                    request.requirement_id,
                    request.question,
                ):
                    raise QuestionConflict(
                        "Request identity already used with different input."
                    )
                return saved
            provider = await row(
                conn,
                """
                SELECT p.name,t.name AS provider_type,t.id AS type_id
                FROM providers p JOIN checklist_templates c ON c.id=p.checklist_template_id
                JOIN provider_types t ON t.id=c.provider_type_id WHERE p.id=%s
                """,
                (request.provider_id,),
            )
            provider_type = provider["provider_type"]
            name, topic = await _provider_context(conn, request, provider["type_id"])
            topics = question_topics(request.question)
            types = await (
                await conn.execute("SELECT name FROM provider_types ORDER BY name")
            ).fetchall()
            mismatch = mismatched_type(
                request.question,
                provider_type,
                dict.fromkeys(
                    ["Dentist", "Dental Hygienist", *(t["name"] for t in types)]
                ),
            )
            revision, space = await state(conn, lock=True)
            versions = await eligible_version_ids(
                conn, provider_type, JURISDICTION, as_of, topics=topics
            )
            inserted = await row(
                conn,
                """
                INSERT INTO qa_runs(request_id,provider_id,provider_type_id,provider_name,provider_type,
                    requirement_id,requirement_name,topic_hint,jurisdiction,question,as_of,corpus_revision,embedding_space_id)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id
                """,
                (
                    request.request_id,
                    request.provider_id,
                    provider["type_id"],
                    provider["name"],
                    provider_type,
                    request.requirement_id,
                    name,
                    topic,
                    JURISDICTION,
                    request.question,
                    as_of,
                    revision,
                    space.id,
                ),
            )
            run_id = inserted["id"]
            async with conn.cursor() as cursor:
                await cursor.executemany(
                    "INSERT INTO qa_run_topics(run_id,topic) VALUES (%s,%s)",
                    [(run_id, topic) for topic in topics],
                )
                await cursor.executemany(
                    "INSERT INTO qa_corpus_versions(run_id,version_id) VALUES (%s,%s)",
                    [(run_id, vid) for vid in versions],
                )
            return ClaimedQuestion(
                run_id, provider_type, name, topic, revision, space, versions, mismatch
            )

    async def corpus(self, capture: ClaimedQuestion) -> CorpusSnapshot:
        async with connection(self.pool) as conn:
            await conn.execute(
                "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY"
            )
            return await snapshot_of(
                conn, capture.revision, capture.space, capture.version_ids
            )

    async def retrieve(
        self, corpus: CorpusSnapshot, question: str, vector: list[float]
    ) -> list[RankedPassage]:
        eligible_ids = [version.id for version in corpus.versions]
        async with connection(self.pool) as conn:
            keywords = await (
                await conn.execute(
                    """
                    WITH terms AS (
                      SELECT string_agg(quote_literal(word),' | ')::tsquery AS query
                      FROM unnest(tsvector_to_array(to_tsvector('english',%s))) AS word
                    )
                    SELECT c.id FROM knowledge_chunks c
                    JOIN knowledge_versions v ON v.id=c.version_id
                    JOIN knowledge_documents d ON d.id=v.document_id
                    CROSS JOIN terms t
                    WHERE c.version_id=ANY(%s) AND (
                        c.terms @@ t.query
                        OR to_tsvector('english',c.section) @@ t.query
                        OR to_tsvector('english',d.title) @@ t.query
                    )
                    ORDER BY ts_rank_cd(
                        c.terms || setweight(to_tsvector('english',c.section),'B')
                                || setweight(to_tsvector('english',d.title),'C'),t.query
                    ) DESC,c.id LIMIT %s
                    """,
                    (question, eligible_ids, PATH_LIMIT),
                )
            ).fetchall()
            vectors = await (
                await conn.execute(
                    """
                    SELECT c.id FROM knowledge_chunks c JOIN knowledge_embeddings e ON e.chunk_id=c.id
                    WHERE c.version_id=ANY(%s) AND e.space_id=%s
                    ORDER BY e.embedding <=> %s::vector,c.id LIMIT %s
                    """,
                    (eligible_ids, corpus.active_space.id, str(vector), PATH_LIMIT),
                )
            ).fetchall()
        return merge_paths(
            corpus.chunks, [r["id"] for r in keywords], [r["id"] for r in vectors]
        )

    async def record_retrieval(
        self, run_id: int, retrieved: list[RankedPassage]
    ) -> None:
        async with connection(self.pool) as conn, conn.cursor() as cursor:
            await cursor.executemany(
                """
                INSERT INTO qa_retrieved_chunks(run_id,chunk_id,version_id,keyword_rank,vector_rank,fused_rank,context_order)
                VALUES (%s,%s,%s,%s,%s,%s,%s)
                """,
                [
                    (
                        run_id,
                        p.chunk.id,
                        p.chunk.version_id,
                        p.keyword_rank,
                        p.vector_rank,
                        p.fused_rank,
                        p.context_order,
                    )
                    for p in retrieved
                ],
            )

    async def finalize(
        self,
        capture: ClaimedQuestion,
        draft: AnswerDraft | None,
        generation_model: str | None,
        as_of: date,
    ) -> SavedAnswer:
        async with connection(self.pool) as conn:
            revision, _ = await state(conn, lock=True)
            await row(
                conn, "SELECT id FROM qa_runs WHERE id=%s FOR UPDATE", (capture.id,)
            )
            recorded_topics = await (
                await conn.execute(
                    "SELECT topic FROM qa_run_topics WHERE run_id=%s", (capture.id,)
                )
            ).fetchall()
            current = await eligible_version_ids(
                conn,
                capture.provider_type,
                JURISDICTION,
                as_of,
                topics=[r["topic"] for r in recorded_topics],
            )
            outdated = revision != capture.revision or current != capture.version_ids
            if draft is not None:
                await _insert_claims(conn, capture.id, draft)
            await conn.execute(
                """
                UPDATE qa_runs SET state=%s,outcome=%s,explanation=%s,missing_facts=%s,conflict_explanation=%s,
                    failure_message=%s,completed_at=now(),generation_model=%s,became_outdated=%s WHERE id=%s
                """,
                (
                    "completed" if draft else "failed",
                    draft.outcome if draft else "service_unavailable",
                    draft.explanation if draft else None,
                    draft.missing_facts if draft else None,
                    draft.conflict_explanation if draft else None,
                    None if draft else FAILURE_MESSAGE,
                    generation_model,
                    outdated,
                    capture.id,
                ),
            )
            return (await _answers(conn, "WHERE r.id=%s", capture.id, as_of))[0]

    async def find(self, key: int | UUID, as_of: date) -> SavedAnswer:
        selector = "WHERE r.request_id=%s" if isinstance(key, UUID) else "WHERE r.id=%s"
        async with connection(self.pool) as conn:
            await conn.execute(
                "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY"
            )
            records = await _answers(conn, selector, key, as_of)
            if not records:
                raise RecordNotFound("Saved answer not found.")
            return records[0]

    async def list_for_provider(
        self, provider_id: int, as_of: date
    ) -> list[SavedAnswer]:
        async with connection(self.pool) as conn:
            await conn.execute(
                "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY"
            )
            await row(conn, "SELECT id FROM providers WHERE id=%s", (provider_id,))
            return await _answers(conn, "WHERE r.provider_id=%s", provider_id, as_of)
