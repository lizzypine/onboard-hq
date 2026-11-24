"""Pure authorization, concurrency and retry checks for source management."""

import hashlib

from pydantic import BaseModel

from app.knowledge_models import EmbeddingSpace, KnowledgeDocument, KnowledgeVersion

DENTAL_TOPICS = frozenset({"dental", "renewal"})
CONTROLLED_SUBSTANCE_TOPICS = frozenset({"ned", "dea", "pdmp"})
SHARED_TOPICS = frozenset({"licensing", "internal", "statutory"})
SUPPORTED_TOPICS = DENTAL_TOPICS | CONTROLLED_SUBSTANCE_TOPICS | SHARED_TOPICS


class KnowledgeForbidden(ValueError):
    pass


class KnowledgeConflict(ValueError):
    pass


class KnowledgeInvalid(ValueError):
    pass


def require_manager(role: str) -> None:
    if role != "manager":
        raise KnowledgeForbidden("A simulated Manager is required.")


def require_visible_version(role: str, status: str) -> None:
    if status == "draft":
        require_manager(role)


def visible_documents(
    documents: list[KnowledgeDocument], role: str
) -> list[KnowledgeDocument]:
    if role == "manager":
        return documents
    visible = []
    for document in documents:
        versions = [v for v in document.versions if v.status != "draft"]
        if versions:
            visible.append(document.model_copy(update={"versions": versions}))
    return visible


def require_revision(version: KnowledgeVersion, revision: int, status: str) -> None:
    if version.status != status or version.draft_revision != revision:
        raise KnowledgeConflict("The source version changed. Load its saved state.")


def require_publishable(version: KnowledgeVersion, confirmed: bool) -> None:
    if (
        not confirmed
        or version.review_issues
        or not version.chunks
        or not version.scopes
    ):
        raise KnowledgeInvalid(
            "Confirm review and resolve all issues before publishing."
        )

    if any(scope.topic.lower() not in SUPPORTED_TOPICS for scope in version.scopes):
        raise KnowledgeInvalid(
            "Use supported scope topics: " + ", ".join(sorted(SUPPORTED_TOPICS)) + "."
        )


def fingerprint(action: str, target: int, request: BaseModel) -> str:
    return hashlib.sha256(
        f"{action}/{target}/{request.model_dump_json()}".encode()
    ).hexdigest()


def require_space(
    space: EmbeddingSpace, model: str, version: str, dimensions: int
) -> None:
    if (space.model, space.version, space.dimensions) != (model, version, dimensions):
        raise KnowledgeConflict(
            "The configured embedding space requires explicit reindex and activation."
        )
