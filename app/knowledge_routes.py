"""HTTP contracts for reviewed source management and retained originals."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Path, Response

from app import knowledge
from app.database import DatabasePool
from app.dependencies import get_pool
from app.embeddings import EmbeddingClient, get_embedding_client
from app.knowledge_models import (
    DraftRequest,
    EditDraftRequest,
    KnowledgeDocument,
    KnowledgeVersion,
    OperationReceipt,
    PublishRequest,
    SourceReviewOptions,
    WithdrawRequest,
)
from app.models import DemoRole
from app.repository.knowledge import KnowledgeRepository

router = APIRouter(prefix="/knowledge")
Role = Annotated[DemoRole, Header(alias="X-Demo-Role")]


def repository(pool: Annotated[DatabasePool, Depends(get_pool)]) -> KnowledgeRepository:
    return KnowledgeRepository(pool)


Repo = Annotated[KnowledgeRepository, Depends(repository)]


@router.get("/documents")
async def documents(repo: Repo, role: Role = "proposer") -> list[KnowledgeDocument]:
    return await knowledge.list_documents(repo, role)


@router.get("/review-options")
def review_options(role: Role = "proposer") -> SourceReviewOptions:
    return knowledge.source_review_options(role)


@router.get("/providers/{provider_id}/requirement-topics")
async def requirement_topics(
    provider_id: Annotated[int, Path(gt=0)], repo: Repo
) -> dict[int, list[str]]:
    return await repo.requirement_topics(provider_id)


@router.get("/versions/{version_id}")
async def version(
    version_id: int, repo: Repo, role: Role = "proposer"
) -> KnowledgeVersion:
    return await knowledge.read_version(repo, version_id, role)


@router.get("/versions/{version_id}/original")
async def original(version_id: int, repo: Repo, role: Role = "proposer") -> Response:
    media, raw = await knowledge.read_original(repo, version_id, role)
    extension = {"text/plain": "txt", "text/html": "html", "application/pdf": "pdf"}[
        media
    ]
    return Response(
        content=raw,
        media_type=media,
        headers={
            "Content-Disposition": f'attachment; filename="knowledge-{version_id}.{extension}"',
            "Content-Security-Policy": "sandbox; default-src 'none'",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.post("/documents/{document_id}/drafts", status_code=201)
async def create(
    document_id: int, req: DraftRequest, repo: Repo, role: Role = "proposer"
) -> OperationReceipt:
    return await knowledge.create_draft(repo, document_id, req, role)


@router.put("/versions/{version_id}")
async def edit(
    version_id: int, req: EditDraftRequest, repo: Repo, role: Role = "proposer"
) -> OperationReceipt:
    return await knowledge.edit_draft(repo, version_id, req, role)


@router.post("/versions/{version_id}/publish")
async def publish(
    version_id: int,
    req: PublishRequest,
    repo: Repo,
    client: Annotated[EmbeddingClient, Depends(get_embedding_client)],
    role: Role = "proposer",
) -> OperationReceipt:
    return await knowledge.publish(repo, version_id, req, role, client)


@router.post("/versions/{version_id}/withdraw")
async def withdraw(
    version_id: int, req: WithdrawRequest, repo: Repo, role: Role = "proposer"
) -> OperationReceipt:
    return await knowledge.withdraw(repo, version_id, req, role)


@router.get("/operations/{operation_id}")
async def operation(
    operation_id: UUID, repo: Repo, role: Role = "proposer"
) -> OperationReceipt:
    return await knowledge.read_operation(repo, operation_id, role)
