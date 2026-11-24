"""Capture eligibility, retrieve evidence, and save a cited answer without progress writes."""

import json
from asyncio import timeout
from collections.abc import Callable
from datetime import date

from openai import APIError
from pydantic import ValidationError
from pydantic_ai.exceptions import AgentRunError
from pydantic_ai.models import Model
from pydantic_ai.usage import UsageLimits

from app.database import DatabaseUnavailable
from app.embeddings import EmbeddingClient, EmbeddingUnavailable, validate_vectors
from app.generation import AgentConfigurationError
from app.knowledge_models import CorpusSnapshot
from app.qa_agent import QAAgentFactory
from app.qa_models import AnswerDraft, AskRequest, RankedPassage, SavedAnswer
from app.repository.qa import JURISDICTION, ClaimedQuestion, QARepository
from app.rules.knowledge import KnowledgeConflict, require_space
from app.rules.qa import InvalidAnswer, validate_answer

QAClock = Callable[[], date]


def _prompt(
    request: AskRequest,
    capture: ClaimedQuestion,
    corpus: CorpusSnapshot,
    retrieved: list[RankedPassage],
    as_of: date,
) -> str:
    versions = {v.id: v for v in corpus.versions}
    selected = sorted(
        (p for p in retrieved if p.context_order is not None),
        key=lambda item: item.context_order or 0,
    )
    passages = []
    for entry in selected:
        chunk = entry.chunk
        version = versions[chunk.version_id]
        passages.append(
            {
                "chunk_id": chunk.id,
                "text": chunk.text,
                "section": chunk.section[:240],
                "title": version.document.title,
                "authority": version.document.publisher,
                "source_kind": version.document.source_kind,
                "effective_from": version.effective_from,
                "effective_to": version.effective_to,
            }
        )
    return json.dumps(
        {
            "question": request.question,
            "provider_type": capture.provider_type,
            "jurisdiction": JURISDICTION,
            "as_of": as_of,
            "requirement": capture.requirement_name,
            "topic_hint": capture.topic_hint,
            "passages": passages,
        },
        default=str,
        ensure_ascii=False,
    )


async def _retrieval(
    repo: QARepository,
    capture: ClaimedQuestion,
    question: str,
    embeddings: EmbeddingClient,
) -> tuple[CorpusSnapshot, list[RankedPassage]]:
    require_space(
        capture.space, embeddings.model, embeddings.version, embeddings.dimensions
    )
    vectors = await embeddings.embed([question])
    validate_vectors(vectors, 1, capture.space.dimensions)
    corpus = await repo.corpus(capture)
    retrieved = await repo.retrieve(corpus, question, vectors[0])
    await repo.record_retrieval(capture.id, retrieved)
    return corpus, retrieved


async def ask_question(
    repo: QARepository,
    request: AskRequest,
    embeddings: EmbeddingClient,
    agent_factory: QAAgentFactory,
    clock: QAClock,
) -> SavedAnswer:
    as_of = clock()
    capture = await repo.claim(request, as_of)
    if isinstance(capture, SavedAnswer):
        return capture
    if capture.mismatch or not capture.version_ids:
        explanation = (
            f"The question mentions {capture.mismatch}. This provider is a {capture.provider_type}."
            if capture.mismatch
            else "No reviewed guidance applies to this provider type and date."
        )
        return await repo.finalize(
            capture,
            AnswerDraft(outcome="cannot_answer", explanation=explanation),
            None,
            clock(),
        )

    generation_model = None
    try:
        corpus, retrieved = await _retrieval(
            repo, capture, request.question, embeddings
        )
        if not retrieved:
            raise EmbeddingUnavailable("Published guidance has no index evidence.")
        agent = agent_factory()
        if isinstance(agent.model, Model):
            generation_model = agent.model.model_name
        async with timeout(45):
            result = await agent.run(
                _prompt(request, capture, corpus, retrieved, as_of),
                usage_limits=UsageLimits(request_limit=1),
            )
        draft = result.output
        validate_answer(draft, retrieved)
    except (
        AgentConfigurationError,
        AgentRunError,
        APIError,
        DatabaseUnavailable,
        EmbeddingUnavailable,
        InvalidAnswer,
        KnowledgeConflict,
        TimeoutError,
        ValidationError,
    ):
        draft = None
    return await repo.finalize(capture, draft, generation_model, clock())
