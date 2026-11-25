"""Read-only licensing question routes and dependency wiring."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Path

from app.database import DatabasePool
from app.dependencies import get_pool
from app.embeddings import EmbeddingClient, get_embedding_client
from app.monitoring import get_monitoring_date
from app.qa import QAClock, ask_question
from app.qa_agent import QAAgentFactory, get_qa_agent_factory
from app.qa_models import AskRequest, SavedAnswer
from app.repository.qa import QARepository

router = APIRouter()
ResourcePath = Annotated[int, Path(gt=0)]


def get_qa_clock() -> QAClock:
    return get_monitoring_date


@router.post("/qa/ask", response_model=SavedAnswer)
async def ask(
    request: AskRequest,
    pool: Annotated[DatabasePool, Depends(get_pool)],
    embeddings: Annotated[EmbeddingClient, Depends(get_embedding_client)],
    agent_factory: Annotated[QAAgentFactory, Depends(get_qa_agent_factory)],
    clock: Annotated[QAClock, Depends(get_qa_clock)],
) -> SavedAnswer:
    return await ask_question(
        QARepository(pool), request, embeddings, agent_factory, clock
    )


@router.get("/qa/requests/{request_id}", response_model=SavedAnswer)
async def saved_request(
    request_id: UUID,
    pool: Annotated[DatabasePool, Depends(get_pool)],
    clock: Annotated[QAClock, Depends(get_qa_clock)],
) -> SavedAnswer:
    return await QARepository(pool).find(request_id, clock())


@router.get("/qa/{answer_id}", response_model=SavedAnswer)
async def saved_answer(
    answer_id: ResourcePath,
    pool: Annotated[DatabasePool, Depends(get_pool)],
    clock: Annotated[QAClock, Depends(get_qa_clock)],
) -> SavedAnswer:
    return await QARepository(pool).find(answer_id, clock())


@router.get("/providers/{provider_id}/answers", response_model=list[SavedAnswer])
async def saved_answers(
    provider_id: ResourcePath,
    pool: Annotated[DatabasePool, Depends(get_pool)],
    clock: Annotated[QAClock, Depends(get_qa_clock)],
) -> list[SavedAnswer]:
    return await QARepository(pool).list_for_provider(provider_id, clock())
