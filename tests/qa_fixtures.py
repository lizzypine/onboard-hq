"""Dispose-only publication of excerpts with original source locators."""

from uuid import uuid4

from app.knowledge_models import (
    DraftRequest,
    Extraction,
    KnowledgeScope,
    Passage,
    PublishRequest,
)
from app.knowledge_sources import source_by_key
from app.repository.knowledge import KnowledgeRepository
from app.rules.knowledge import fingerprint
from tests.knowledge_fixtures import SyntheticEmbeddings


async def publish_passages(
    repo,
    source,
    metadata,
    passages,
    *,
    provider_type="Dentist",
    jurisdiction="HI",
    embeddings=None,
    publish_now=True,
    scopes=None,
):
    texts = [p["text"] for p in passages]
    text = "\n\n".join(texts)
    start = 0
    chunks = []
    for passage in passages:
        stop = start + len(passage["text"])
        chunks.append(Passage(**passage, char_start=start, char_end=stop))
        start = stop + 2
    identity = source_by_key(source) if source != "internal-guide" else None
    topic = identity.topic if identity else "internal"
    request = DraftRequest(
        operation_id=uuid4(),
        text=text,
        stated_revision=metadata["revision"],
        effective_from=metadata.get("effective_from"),
        effective_to=metadata.get("effective_to"),
        scopes=scopes
        or [
            KnowledgeScope(
                provider_type=provider_type, jurisdiction=jurisdiction, topic=topic
            )
        ],
    )
    document_id = 0
    if identity is None:
        document_id = next(
            d.id for d in await repo.list_documents() if d.source_key == source
        )
    version = await repo.create_draft(
        document_id,
        request,
        text.encode(),
        "text/plain",
        Extraction(text=text, chunks=chunks),
        fingerprint("create", document_id, request),
        source=identity,
    )
    if publish_now:
        await publish_version(repo, version.version_id, texts, embeddings)
    return await repo.get_version(version.version_id)


async def publish_version(
    repo: KnowledgeRepository, version_id, texts, embeddings=None
):
    publish = PublishRequest(
        operation_id=uuid4(), expected_revision=1, confirmed_review=True
    )
    await repo.publish(
        version_id,
        publish,
        fingerprint("publish", version_id, publish),
        await repo.current_space(),
        await (embeddings or SyntheticEmbeddings()).embed(texts),
    )


class LicensingFixtureEmbeddings(SyntheticEmbeddings):
    """Deterministic word vectors with general licensing synonyms, no case labels."""

    async def embed(self, texts):
        import re

        aliases = {
            "renewal": "renew",
            "renewed": "renew",
            "expiration": "renew",
            "expire": "renew",
            "expired": "renew",
            "valid": "renew",
            "site": "location",
            "sites": "location",
            "locations": "location",
            "licensure": "license",
            "licensed": "license",
            "licenses": "license",
            "dentist": "dental",
            "dentists": "dental",
        }
        normalized = []
        for text in texts:
            words = re.findall(
                r"\w+", text.casefold().replace("continuing education", "ce")
            )
            normalized.append(" ".join(aliases.get(word, word) for word in words))
        return await super().embed(normalized)
