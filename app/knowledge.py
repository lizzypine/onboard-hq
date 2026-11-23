"""Authorize source changes and release connections before extraction and embedding."""

from app.embeddings import EmbeddingClient, validate_vectors
from app.knowledge_models import (
    DraftRequest,
    EditDraftRequest,
    OperationReceipt,
    PublishRequest,
    WithdrawRequest,
)
from app.repository.knowledge import KnowledgeRepository
from app.rules.knowledge import (
    fingerprint,
    require_manager,
    require_publishable,
    require_revision,
    require_space,
)
from app.source_extraction import extract_source


async def create_draft(
    repo: KnowledgeRepository, doc: int, req: DraftRequest, role: str
) -> OperationReceipt:
    require_manager(role)
    raw = req.text.encode()
    return await repo.create_draft(
        doc,
        req,
        raw,
        "text/plain",
        extract_source(raw, "text/plain"),
        fingerprint("create", doc, req),
    )


async def edit_draft(
    repo: KnowledgeRepository, vid: int, req: EditDraftRequest, role: str
) -> OperationReceipt:
    require_manager(role)
    digest = fingerprint("edit", vid, req)
    if saved := await repo.check_retry(req.operation_id, digest):
        return saved
    version = await repo.get_version(vid)
    parsed = (
        extract_source(req.text.encode(), "text/plain")
        if req.text != version.text and version.document.source_kind == "internal"
        else None
    )
    return await repo.edit_draft(vid, req, parsed, digest)


async def publish(
    repo: KnowledgeRepository,
    vid: int,
    req: PublishRequest,
    role: str,
    client: EmbeddingClient,
) -> OperationReceipt:
    require_manager(role)
    digest = fingerprint("publish", vid, req)
    captured = await repo.prepare_publication(vid, req.operation_id, digest)
    if isinstance(captured, OperationReceipt):
        return captured
    v, space = captured
    require_revision(v, req.expected_revision, "draft")
    require_publishable(v, req.confirmed_review)
    require_space(space, client.model, client.version, client.dimensions)
    vectors = await client.embed([c.text for c in v.chunks])
    validate_vectors(vectors, len(v.chunks), space.dimensions)
    return await repo.publish(vid, req, digest, space, vectors)


async def withdraw(
    repo: KnowledgeRepository, vid: int, req: WithdrawRequest, role: str
) -> OperationReceipt:
    require_manager(role)
    return await repo.withdraw(vid, req, fingerprint("withdraw", vid, req))


async def reindex(repo: KnowledgeRepository, client: EmbeddingClient) -> None:
    revision, space, chunks = await repo.prepare_space(
        client.model, client.version, client.dimensions
    )
    vectors = await client.embed([c.text for c in chunks]) if chunks else []
    await repo.activate_space(revision, space, chunks, vectors)
