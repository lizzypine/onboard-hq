"""Create synthetic source fixtures through the real repository and HTTP API."""

from hashlib import sha256
from uuid import uuid4

from app.database import create_pool
from app.knowledge_models import DraftRequest, KnowledgeScope
from app.knowledge_sources import source_by_key
from app.repository.knowledge import KnowledgeRepository
from app.source_extraction import extract_source
from tests.fixtures.current_database import run_async

MANAGER = {"X-Demo-Role": "manager"}
QUOTE = 'Renewal note: <img src=x onerror="window.injected=true"> remains literal.'
CONFLICT_QUOTE = "Another synthetic note specifies a different renewal period."
SOURCE = "## Renewal review\n\n" + QUOTE + "\n\n" + CONFLICT_QUOTE
ISSUE = "Confirm the synthetic reviewer role."
SCOPE = {"provider_type": "Dentist", "jurisdiction": "HI", "topic": "renewal"}


def create_source(page, server, **changes):
    documents = page.request.get(
        server.url + "/knowledge/documents", headers=MANAGER
    ).json()
    internal = next(doc for doc in documents if doc["source_kind"] == "internal")
    response = page.request.post(
        server.url + f"/knowledge/documents/{internal['id']}/drafts",
        headers=MANAGER,
        data={
            "operation_id": str(uuid4()),
            "text": SOURCE,
            "scopes": [SCOPE],
            **changes,
        },
    )
    assert response.status == 201, response.text()
    return response.json()["version_id"]


def publish_source(page, server, version):
    response = page.request.post(
        server.url + f"/knowledge/versions/{version}/publish",
        headers=MANAGER,
        data={
            "operation_id": str(uuid4()),
            "expected_revision": 1,
            "confirmed_review": True,
        },
    )
    assert response.ok, response.text()


def import_official(server):
    source = source_by_key("board-laws")
    raw = b"<h2>Board rules review</h2><p>Synthetic official guidance.</p>"
    parsed = extract_source(raw, source.media_type)
    request = DraftRequest(
        operation_id=uuid4(),
        text=parsed.text,
        scopes=[KnowledgeScope(**SCOPE)],
    )

    async def save():
        async with create_pool(server.database_url) as pool:
            return await KnowledgeRepository(pool).create_draft(
                0, request, raw, source.media_type, parsed, sha256(raw).hexdigest(), source
            )

    return run_async(save).version_id
