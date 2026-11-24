"""Manager source decisions and retained evidence through real HTTP and PostgreSQL."""

import asyncio
from uuid import uuid4

import psycopg
import pytest

MANAGER = {"X-Demo-Role": "manager"}
SCOPE = {"provider_type": "Dentist", "jurisdiction": "HI", "topic": "dental"}


def content(text="Reviewed synthetic procedure.", **overrides):
    return {
        "operation_id": str(uuid4()),
        "text": text,
        "stated_revision": "Synthetic 1",
        "scopes": [SCOPE],
        "review_issues": [],
    } | overrides


def internal_id(client):
    response = client.get("/knowledge/documents", headers=MANAGER)
    assert response.status_code == 200
    return next(
        doc["id"] for doc in response.json() if doc["source_kind"] == "internal"
    )


def create(client, doc, **kwargs):
    response = client.post(
        f"/knowledge/documents/{doc}/drafts", json=content(**kwargs), headers=MANAGER
    )
    assert response.status_code == 201, response.text
    return response.json()["version_id"]


def publish(client, version, revision=1, **opts):
    body = {
        "operation_id": str(uuid4()),
        "expected_revision": revision,
        "confirmed_review": True,
        **opts,
    }
    return client.post(
        f"/knowledge/versions/{version}/publish", json=body, headers=MANAGER
    )


def test_source_roles_and_draft_retry(client):
    doc = internal_id(client)
    url = f"/knowledge/documents/{doc}/drafts"
    body = content()
    assert client.post(url, json=body).status_code == 403
    first = client.post(url, json=body, headers=MANAGER)
    assert first.status_code == 201
    assert client.post(url, json=body, headers=MANAGER).json() == first.json()
    assert (
        client.post(url, json={**body, "text": "Changed"}, headers=MANAGER).status_code
        == 409
    )
    version = first.json()["version_id"]
    assert client.get(f"/knowledge/versions/{version}").status_code == 403
    assert client.get(f"/knowledge/versions/{version}/original").status_code == 403
    new = content("Correction", expected_revision=1)
    assert (
        client.put(
            f"/knowledge/versions/{version}", json=new, headers=MANAGER
        ).status_code
        == 200
    )
    assert (
        client.put(
            f"/knowledge/versions/{version}",
            json={**new, "operation_id": str(uuid4())},
            headers=MANAGER,
        ).status_code
        == 409
    )
    assert publish(client, version).status_code == 409


def test_publication_requires_review_and_complete_vectors(client, db_url):
    doc = internal_id(client)
    issue = create(client, doc, review_issues=["Confirm contact"])
    assert publish(client, issue).status_code == 422
    v = create(client, doc)
    assert publish(client, v, confirmed_review=False).status_code == 422
    from app.embeddings import get_embedding_client
    from app.main import app
    from tests.knowledge_fixtures import BrokenEmbeddings

    app.dependency_overrides[get_embedding_client] = BrokenEmbeddings
    assert publish(client, v).status_code == 503
    assert (
        client.get(f"/knowledge/versions/{v}", headers=MANAGER).json()["status"]
        == "draft"
    )
    with psycopg.connect(db_url) as conn:
        assert conn.execute(
            "SELECT count(*) FROM knowledge_publications WHERE action='publish'"
        ).fetchone() == (0,)


def test_supersede_withdraw_retain_original_and_retry_receipt(client, db_url):
    doc = internal_id(client)
    v1 = create(client, doc, text="First procedure.")
    key = str(uuid4())
    receipt = publish(client, v1, operation_id=key)
    assert receipt.status_code == 200, receipt.text
    v2 = create(client, doc, text="Replacement procedure.")
    assert publish(client, v2).status_code == 200
    assert publish(client, v1, operation_id=key).json() == receipt.json()
    assert (
        client.get(f"/knowledge/operations/{key}", headers=MANAGER).json()
        == receipt.json()
    )
    assert client.get(f"/knowledge/versions/{v1}").json()["status"] == "superseded"
    assert (
        client.get(f"/knowledge/versions/{v1}/original").content == b"First procedure."
    )
    withdraw = {"operation_id": str(uuid4()), "expected_revision": 1}
    url = f"/knowledge/versions/{v2}/withdraw"
    assert client.post(url, json=withdraw).status_code == 403
    result = client.post(url, json=withdraw, headers=MANAGER)
    assert result.status_code == 200
    assert result.json() == client.post(url, json=withdraw, headers=MANAGER).json()
    assert client.get(f"/knowledge/versions/{v2}").json()["status"] == "withdrawn"
    with psycopg.connect(db_url) as conn:
        for stmt in [
            "UPDATE knowledge_chunks SET text='edit'",
            "DELETE FROM knowledge_publications",
            "UPDATE knowledge_versions SET original='new'",
            "UPDATE knowledge_scopes SET topic='other'",
        ]:
            with pytest.raises(psycopg.Error), conn.transaction():
                conn.execute(stmt)
        with pytest.raises(psycopg.Error), conn.transaction():
            conn.execute("UPDATE knowledge_embeddings SET embedding='[1,2]'")


def test_pgvector_rejects_wrong_dimensions_and_incomplete_publication(client, db_url):
    version = create(client, internal_id(client))
    with psycopg.connect(db_url) as conn:
        with pytest.raises(psycopg.errors.CheckViolation), conn.transaction():
            conn.execute(
                """INSERT INTO knowledge_embeddings(chunk_id,space_id,dimensions,embedding)
                SELECT c.id,s.active_space_id,1536,'[1,2]'::vector FROM knowledge_chunks c
                CROSS JOIN knowledge_state s WHERE c.version_id=%s""",
                (version,),
            )
        with pytest.raises(psycopg.errors.RaiseException), conn.transaction():
            conn.execute(
                "UPDATE knowledge_versions SET status='published',reviewed_at=now() WHERE id=%s",
                (version,),
            )


def test_scope_dates_reindex_failure_and_activation(client, db_url):
    import asyncio
    from datetime import date

    from app.database import create_pool
    from app.embeddings import EmbeddingUnavailable
    from app.knowledge import reindex
    from app.repository.knowledge import KnowledgeRepository
    from tests.knowledge_fixtures import BrokenEmbeddings, SyntheticEmbeddings

    v = create(
        client,
        internal_id(client),
        effective_from="2026-01-01",
        effective_to="2026-12-31",
    )
    assert publish(client, v).status_code == 200

    async def check():
        async with create_pool(db_url) as pool:
            repo = KnowledgeRepository(pool)
            before = await repo.corpus_snapshot("Dentist", "HI", date(2026, 12, 31))
            assert [x.id for x in before.versions] == [v]
            assert before.chunks[0].version_id == v
            for provider, jurisdiction, on in [
                ("Dentist", "HI", date(2027, 1, 1)),
                ("Dentist", "CA", date(2026, 12, 31)),
                ("Dental Hygienist", "HI", date(2026, 12, 31)),
            ]:
                snapshot = await repo.corpus_snapshot(provider, jurisdiction, on)
                assert snapshot.chunks == []
            bad = BrokenEmbeddings()
            bad.model = "synthetic-v2"
            bad.dimensions = 4
            with pytest.raises(EmbeddingUnavailable):
                await reindex(repo, bad)
            assert await repo.current_space() == before.active_space
            good = SyntheticEmbeddings()
            good.model = bad.model
            good.dimensions = 4
            await reindex(repo, good)
            after = await repo.corpus_snapshot("Dentist", "HI", date(2026, 2, 1))
            assert after.active_space.dimensions == 4
            assert after.revision == before.revision + 1
            assert after.chunks == before.chunks

    asyncio.run(check())


def test_edit_during_embedding_prevents_stale_publication(client, db_url):
    from app.embeddings import get_embedding_client
    from app.main import app
    from tests.knowledge_fixtures import SyntheticEmbeddings

    doc = internal_id(client)
    prior = create(client, doc, text="Approved earlier.")
    assert publish(client, prior).status_code == 200
    edited = create(client, doc, text="Original draft.")

    class MidflightEdit(SyntheticEmbeddings):
        async def embed(self, texts):
            # A second connection can commit while the embedding call is in progress.
            other = await asyncio.to_thread(
                client.put,
                f"/knowledge/versions/{edited}",
                json=content("Corrected draft.", expected_revision=1),
                headers=MANAGER,
            )
            assert other.status_code == 200
            return await super().embed(texts)

    app.dependency_overrides[get_embedding_client] = MidflightEdit
    assert publish(client, edited).status_code == 409
    assert client.get(f"/knowledge/versions/{prior}").json()["status"] == "published"
    assert (
        client.get(f"/knowledge/versions/{edited}", headers=MANAGER).json()[
            "draft_revision"
        ]
        == 2
    )


def test_internal_ingest_retains_safe_text_and_unresolved_issues(client, db_url):
    import asyncio
    import re

    from app.database import create_pool
    from app.knowledge_sources import ingest
    from app.repository.knowledge import KnowledgeRepository

    async def save():
        async with create_pool(db_url) as pool:
            return await ingest(KnowledgeRepository(pool), "internal-guide")

    receipt = asyncio.run(save())
    v = client.get(f"/knowledge/versions/{receipt.version_id}", headers=MANAGER).json()
    assert {
        "Dental license",
        "Hawaii NED and HI-PDMP",
        "Federal DEA registration",
        "Final handoff",
    } == {c["section"] for c in v["chunks"]}
    assert "main office" in v["text"]
    assert not re.search(
        r"\b\d+\s+[\w ]+(?:street|road|avenue|drive)\b|[\w.]+@[\w.]+",
        v["text"],
        re.IGNORECASE,
    )
    assert any("PDMP" in issue for issue in v["review_issues"])
    assert any("recipient" in issue for issue in v["review_issues"])
    assert publish(client, v["id"]).status_code == 422


def test_official_original_provenance_and_download_safety(client, db_url, monkeypatch):
    from app import knowledge_sources
    from app.database import create_pool
    from app.repository.knowledge import KnowledgeRepository

    raw = (
        b"<h2>Reviewed section</h2><p>Known statement.</p><script>untrusted()</script>"
    )

    async def fetch(source):
        assert source.source_key == "board-laws"
        return raw

    monkeypatch.setattr(knowledge_sources, "fetch_source", fetch)

    async def save():
        async with create_pool(db_url) as pool:
            return await knowledge_sources.ingest(
                KnowledgeRepository(pool), "board-laws"
            )

    v = asyncio.run(save()).version_id
    url = f"/knowledge/versions/{v}"
    details = client.get(url, headers=MANAGER).json()
    assert details["text"] == "Known statement."
    assert details["effective_from"] is None
    assert details["reviewed_at"] is None
    assert details["document"]["source_kind"] == "official"
    assert (
        client.put(
            url,
            headers=MANAGER,
            json=content("Replacement official statement", expected_revision=1),
        ).status_code
        == 422
    )
    assert (
        client.put(
            url, headers=MANAGER, json=content("Known statement.", expected_revision=1)
        ).status_code
        == 200
    )
    assert publish(client, v, revision=2).status_code == 200
    download = client.get(url + "/original")
    assert download.content == raw
    assert "sandbox" in download.headers["content-security-policy"]
    assert "attachment" in download.headers["content-disposition"]
    assert download.headers["x-content-type-options"] == "nosniff"


def test_requirement_context_is_bound_to_saved_type_and_definition(
    db_url, seeded_provider
):
    from app.database import create_pool
    from app.repository.knowledge import KnowledgeRepository

    ids = {r.name: r.id for r in seeded_provider.requirements}

    async def bindings():
        async with create_pool(db_url) as pool:
            return await KnowledgeRepository(pool).requirement_topics(
                seeded_provider.id
            )

    assert asyncio.run(bindings()) == {
        ids["Hawaii dental license"]: ["dental"],
        ids["State NED license"]: ["ned"],
    }


@pytest.mark.parametrize("operation", ["publish", "withdraw", "reindex"])
def test_source_operation_waits_for_embedding_space_activation(
    client, db_url, operation
):
    from app.database import create_pool
    from app.knowledge import reindex
    from app.repository.knowledge import KnowledgeRepository
    from tests.knowledge_fixtures import SyntheticEmbeddings
    from tests.test_catalog_races import wait_until_row_lock_blocks

    doc = internal_id(client)
    published_version = create(client, doc)
    assert publish(client, published_version).status_code == 200
    draft = create(client, doc)
    new_client = SyntheticEmbeddings()
    new_client.model = str(uuid4())

    async def scenario():
        async with create_pool(db_url) as pool:
            repo = KnowledgeRepository(pool)
            previous = await repo.current_space()
            revision, next_space, _ = await repo.prepare_space(
                new_client.model, new_client.version, new_client.dimensions
            )
            async with pool.connection() as activator:
                await activator.execute(
                    """INSERT INTO knowledge_embeddings(chunk_id,space_id,dimensions,embedding)
                    SELECT chunk_id,%s,dimensions,embedding FROM knowledge_embeddings
                    WHERE space_id=%s""",
                    (next_space.id, previous.id),
                )
                await activator.execute(
                    "UPDATE knowledge_state SET active_space_id=%s,revision=revision+1 WHERE singleton",
                    (next_space.id,),
                )
                if operation == "publish":
                    task = asyncio.create_task(
                        asyncio.to_thread(publish, client, draft)
                    )
                elif operation == "withdraw":
                    task = asyncio.create_task(
                        asyncio.to_thread(
                            client.post,
                            f"/knowledge/versions/{published_version}/withdraw",
                            json={"operation_id": str(uuid4()), "expected_revision": 1},
                            headers=MANAGER,
                        )
                    )
                else:
                    task = asyncio.create_task(reindex(repo, new_client))
                try:
                    await wait_until_row_lock_blocks(activator)
                finally:
                    await activator.commit()
                result = await asyncio.wait_for(task, timeout=5)
            assert await repo.current_space() == next_space
            if operation == "publish":
                assert result.status_code == 409
                assert (await repo.get_version(draft)).status == "draft"
            elif operation == "withdraw":
                assert result.status_code == 200
                assert result.json()["corpus_revision"] == revision + 2
            else:
                assert result is None

    asyncio.run(scenario())


@pytest.mark.parametrize("label", ["continuing education", "reneweal"])
def test_unsupported_topic_draft_remains_readable_and_publication_fails_before_embedding(
    client, db_url, label
):
    from app.embeddings import get_embedding_client
    from app.main import app
    from tests.knowledge_fixtures import BrokenEmbeddings, SyntheticEmbeddings

    version = create(client, internal_id(client), scopes=[SCOPE | {"topic": label}])
    assert client.get(f"/knowledge/versions/{version}", headers=MANAGER).json()[
        "scopes"
    ] == [SCOPE | {"topic": label}]

    app.dependency_overrides[get_embedding_client] = BrokenEmbeddings
    blocked = publish(client, version)
    assert blocked.status_code == 422, blocked.text
    assert "scope topics" in blocked.json()["detail"]
    assert "renewal" in blocked.json()["detail"]
    with psycopg.connect(db_url) as conn:
        assert conn.execute(
            "SELECT status FROM knowledge_versions WHERE id=%s", (version,)
        ).fetchone() == ("draft",)
        assert conn.execute("SELECT count(*) FROM knowledge_embeddings").fetchone() == (
            0,
        )

    corrected = client.put(
        f"/knowledge/versions/{version}",
        json=content(scopes=[SCOPE | {"topic": "Renewal"}], expected_revision=1),
        headers=MANAGER,
    )
    assert corrected.status_code == 200, corrected.text
    app.dependency_overrides[get_embedding_client] = SyntheticEmbeddings
    assert publish(client, version, revision=2).status_code == 200
