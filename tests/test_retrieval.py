"""Exact hybrid retrieval and passage expansion on actual PostgreSQL."""

import asyncio
from datetime import date

from app.database import create_pool
from app.repository.knowledge import KnowledgeRepository
from tests.test_knowledge import create, internal_id, publish


def test_acronym_and_semantic_paths_share_scope_and_fuse_candidates(client, db_url):
    from app.repository.qa import QARepository

    doc = internal_id(client)
    version = create(
        client,
        doc,
        text="# Exam\nADEX testing.\n\n# Other\nClinical eligibility.\n\n# Cross match\nADEX clinical examination with ADEX evidence.",
    )
    assert publish(client, version).status_code == 200

    async def check():
        async with create_pool(db_url) as pool:
            corpus = await KnowledgeRepository(pool).corpus_snapshot(
                "Dentist", "HI", date(2026, 11, 23)
            )
            # The numeric search vector equals the cross-match passage's stored vector.
            async with pool.connection() as conn:
                raw = await (
                    await conn.execute(
                        "SELECT e.embedding::text AS val FROM knowledge_embeddings e JOIN knowledge_chunks c ON c.id=e.chunk_id WHERE c.section='Cross match'"
                    )
                ).fetchone()
            vector = [float(v) for v in raw["val"].strip("[]").split(",")]
            result = await QARepository(pool).retrieve(corpus, "ADEX", vector)
            assert len(result) == 3
            assert result[0].chunk.section == "Cross match"
            ranks = {
                r.chunk.section: (r.keyword_rank, r.vector_rank, r.fused_rank)
                for r in result
            }
            assert ranks["Cross match"][0] in (1, 2)
            assert ranks["Cross match"][1:] == (1, 1)
            assert ranks["Exam"][0] in (1, 2)
            assert ranks["Other"][0] is None

    asyncio.run(check())


def test_shared_path_eligibility_excludes_pending_expired_future_and_wrong_scope(
    db_url, seeded_provider
):
    from app.repository.catalog import CatalogRepository
    from app.repository.qa import QARepository
    from tests.knowledge_fixtures import SyntheticEmbeddings
    from tests.qa_fixtures import publish_passages

    async def check():
        async with create_pool(db_url) as pool:
            await CatalogRepository(pool).ensure_version(
                "Dental Hygienist", ["Synthetic requirement"], template_version=1
            )
            knowledge = KnowledgeRepository(pool)
            text = "ADEX approved synthetic evidence."
            passages = [{"section": "ADEX", "text": text, "page": 1}]
            rev = {"revision": "Fixture 1"}
            eligible = await publish_passages(
                knowledge,
                "dentist-application",
                rev | {"effective_from": "2026-11-23", "effective_to": "2026-11-23"},
                passages,
            )
            await publish_passages(
                knowledge, "har-79", rev | {"effective_to": "2026-11-22"}, passages
            )
            await publish_passages(
                knowledge,
                "virtual-ce-waiver",
                rev | {"effective_from": "2026-11-24"},
                passages,
            )
            await publish_passages(
                knowledge,
                "board-renewal",
                rev,
                passages,
                provider_type="Dental Hygienist",
            )
            await publish_passages(
                knowledge, "dea-registration", rev, passages, jurisdiction="CA"
            )
            await publish_passages(
                knowledge, "hrs-436b-9", rev, passages, publish_now=False
            )
            corpus = await knowledge.corpus_snapshot(
                "Dentist", "HI", date(2026, 11, 23)
            )
            [query] = await SyntheticEmbeddings().embed([text])
            [match] = await QARepository(pool).retrieve(corpus, "ADEX", query)
            assert match.chunk.version_id == eligible.id
            assert (match.keyword_rank, match.vector_rank) == (1, 1)

    asyncio.run(check())


def test_adjacent_exception_and_continuation_survive_full_rank_lists(
    db_url, seeded_provider
):
    from app.repository.qa import QARepository
    from tests.qa_fixtures import publish_passages

    def chunk(section, text, page):
        return {"section": section, "text": text, "page": page}

    class ControlledEmbeddings:
        async def embed(self, texts):
            vectors = []
            for text in texts:
                vector = [0.0] * 1536
                if "established dentists" in text:
                    vector[0] = 1.0
                elif text.startswith("§16"):
                    vector[:2] = [1.0, 0.4]
                else:
                    vector[1] = 1.0
                vectors.append(vector)
            return vectors

    async def check():
        async with create_pool(db_url) as pool:
            knowledge = KnowledgeRepository(pool)
            anchor = chunk(
                "§16-79-144", "§16-79-144 established dentists need 32 CE hours.", 29
            )
            exception = chunk(
                "§16-79-144", "Initial licensees have alternate requirements.", 29
            )
            continuation = chunk(
                "§16-79-144", "Annual ethics minimum survives those exceptions.", 30
            )
            toc = chunk("Table of Contents", "§16-79-144 Biennial renewal.", 1)
            distraction = chunk(
                "§16-79-144", "References to a similarly labeled heading.", 34
            )
            filler = [
                chunk(f"Filler {i}", f"§16-79-144 synthetic distractor {i}.", 28)
                for i in range(24)
            ]
            await publish_passages(
                knowledge,
                "har-79",
                {"revision": "Fixture 1"},
                [
                    toc,
                    *filler,
                    anchor,
                    exception,
                    continuation,
                    chunk("Appendix", "Boundary.", 32),
                    distraction,
                ],
                embeddings=ControlledEmbeddings(),
            )
            corpus = await knowledge.corpus_snapshot(
                "Dentist", "HI", date(2026, 11, 23)
            )
            [query] = await ControlledEmbeddings().embed([anchor["text"]])
            ranked = await QARepository(pool).retrieve(
                corpus, "§16-79-144 CE hours", query
            )
            context = [p.chunk.text for p in ranked if p.context_order is not None]
            assert anchor["text"] in context
            assert exception["text"] in context
            assert continuation["text"] in context
            assert distraction["text"] not in context
            assert len(context) == 12
            assert max(p.keyword_rank or 0 for p in ranked) == 20
            assert max(p.vector_rank or 0 for p in ranked) == 20

    # Keep the body passages adjacent in source order, with the TOC and its
    # competing match physically separated by a different heading.
    asyncio.run(check())


def test_offline_question_rubric_retrieves_required_source_versions_and_provenance(
    client, db_url, seeded_provider
):
    from json import loads
    from pathlib import Path

    from pydantic_ai.models.test import TestModel

    from app.embeddings import get_embedding_client
    from app.main import app
    from app.qa_routes import get_qa_clock
    from tests.qa_fixtures import LicensingFixtureEmbeddings, publish_passages
    from tests.test_qa import ask, ask_body, install_model

    fixture = loads(
        (Path(__file__).parent / "fixtures/licensing_questions.json").read_text()
    )
    day = date.fromisoformat(fixture["as_of"])
    app.dependency_overrides[get_qa_clock] = lambda: lambda: day
    app.dependency_overrides[get_embedding_client] = LicensingFixtureEmbeddings

    async def seed():
        async with create_pool(db_url) as pool:
            repo = KnowledgeRepository(pool)
            return {
                source: await publish_passages(
                    repo,
                    source,
                    metadata,
                    list(metadata["passages"].values()),
                    embeddings=LicensingFixtureEmbeddings(),
                )
                for source, metadata in fixture["sources"].items()
            }

    published = asyncio.run(seed())
    failures = []
    for case in fixture["cases"]:
        outcome = case["outcome"]
        expected = []
        refs = []
        for item in case["evidence"]:
            version = published[item["source"]]
            locator = fixture["sources"][item["source"]]["passages"][item["passage"]]
            chunk = next(p for p in version.chunks if p.text == locator["text"])
            start = chunk.text.index(item["quote"])
            refs.append(
                {
                    "chunk_id": chunk.id,
                    "quote": item["quote"],
                    "start": start,
                    "end": start + len(item["quote"]),
                }
            )
            expected.append((version.id, chunk.id))
        # Predetermined TestModel output exercises the citation gate and storage.
        # The retrieved evidence set below comes from PostgreSQL, independently.
        output = {"outcome": outcome}
        if outcome in {"supported", "conflicting_guidance"}:
            output["claims"] = [
                {"text": "Synthetic citation plumbing check.", "citations": refs}
            ]
        if outcome == "conflicting_guidance":
            output["conflict_explanation"] = (
                "Synthetic conflict for an offline structural check."
            )
        if outcome == "more_information_needed":
            output["missing_facts"] = "Synthetic missing-context check."
        install_model(TestModel(custom_output_args=output))
        answer = ask(client, ask_body(seeded_provider, case["question"]))
        import psycopg

        with psycopg.connect(db_url) as conn:
            selected = conn.execute(
                "SELECT version_id,chunk_id FROM qa_retrieved_chunks WHERE run_id=%s AND context_order IS NOT NULL",
                (answer["id"],),
            ).fetchall()
        missing = set(expected) - set(selected)
        if missing:
            failures.append((case["id"], sorted(missing)))
        elif answer["outcome"] != outcome:
            failures.append((case["id"], answer["outcome"]))
        else:
            cites = [
                citation
                for claim in answer["claims"]
                for citation in claim["citations"]
            ]
            for item, actual in zip(case["evidence"], cites):
                version = published[item["source"]]
                locator = fixture["sources"][item["source"]]["passages"][
                    item["passage"]
                ]
                assert actual["source_key"] == item["source"]
                assert actual["source_checksum"] == version.checksum
                assert actual["quote"] == item["quote"]
                assert actual["page"] == locator["page"]
                assert actual["section"] == locator["section"]
                assert (
                    version.text[actual["char_start"] : actual["char_end"]]
                    == item["quote"]
                )
    assert failures == []
