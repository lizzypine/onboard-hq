"""Exact hybrid retrieval and passage expansion on actual PostgreSQL."""

import asyncio
from datetime import date

import pytest

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
    initial = next(
        r for r in seeded_provider.requirements if r.name == "Hawaii dental license"
    )
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
        # An initial dental-license row can still launch cross-topic questions.
        context = (
            {"requirement_id": initial.id} if case["id"] == "dea-prerequisite" else {}
        )
        answer = ask(client, ask_body(seeded_provider, case["question"], **context))
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


def test_dental_ce_retrieves_only_applicable_scope_rows_despite_initial_license_hint(
    client, db_url, seeded_provider
):
    import psycopg
    from pydantic_ai.models.test import TestModel

    from app.knowledge_models import KnowledgeScope
    from app.repository.catalog import CatalogRepository
    from tests.qa_fixtures import publish_passages
    from tests.test_qa import ask, ask_body, evidence, install_model, supported

    question = "How much dental continuing education is needed for renewal?"
    expected_quote = "Dentists need continuing education for renewal."
    revision = {"revision": "Fixture 1"}

    def passages(text):
        return [{"text": text, "section": "Renewal", "page": 1}]

    async def seed():
        async with create_pool(db_url) as pool:
            await CatalogRepository(pool).ensure_version(
                "Dental Hygienist", ["Synthetic requirement"], template_version=1
            )
            knowledge = KnowledgeRepository(pool)
            renewal = await publish_passages(
                knowledge, "board-renewal", revision, passages(expected_quote)
            )
            shared = await publish_passages(
                knowledge,
                "internal-guide",
                revision,
                passages("See the renewal guidance."),
            )
            ned = await publish_passages(
                knowledge, "ned-instructions", revision, passages(question)
            )
            mixed = await publish_passages(
                knowledge,
                "ned-renewal",
                revision,
                passages(question),
                scopes=[
                    KnowledgeScope(
                        provider_type="Dentist", jurisdiction="HI", topic="ned"
                    ),
                    KnowledgeScope(
                        provider_type="Dental Hygienist",
                        jurisdiction="HI",
                        topic="renewal",
                    ),
                    KnowledgeScope(
                        provider_type="Dentist", jurisdiction="CA", topic="renewal"
                    ),
                ],
            )
            return renewal, shared, ned, mixed

    renewal, shared, ned, mixed = asyncio.run(seed())
    install_model(
        TestModel(
            custom_output_args=supported(evidence(renewal.chunks[0].id, expected_quote))
        )
    )
    initial_row = next(
        r for r in seeded_provider.requirements if r.name == "Hawaii dental license"
    )
    answer = ask(
        client, ask_body(seeded_provider, question, requirement_id=initial_row.id)
    )
    assert answer["topic_hint"] == "dental"
    assert answer["outcome"] == "supported"
    assert answer["claims"][0]["citations"][0]["version_id"] == renewal.id
    with psycopg.connect(db_url) as conn:
        membership = conn.execute(
            "SELECT version_id FROM qa_corpus_versions WHERE run_id=%s", (answer["id"],)
        ).fetchall()
        ranked = conn.execute(
            "SELECT version_id,keyword_rank,vector_rank FROM qa_retrieved_chunks WHERE run_id=%s",
            (answer["id"],),
        ).fetchall()
        assert {version for (version,) in membership} == {renewal.id, shared.id}
        assert {version for version, _, _ in ranked} == {renewal.id, shared.id}
        assert any(
            version == renewal.id and kw and cosine for version, kw, cosine in ranked
        )
        assert {ned.id, mixed.id}.isdisjoint(version for version, _, _ in ranked)
        topics = conn.execute(
            "SELECT topic FROM qa_run_topics WHERE run_id=%s", (answer["id"],)
        ).fetchall()
        assert {topic for (topic,) in topics} == {
            "dental",
            "renewal",
            "internal",
            "licensing",
            "statutory",
        }


def test_newly_effective_unrelated_topic_does_not_stale_dental_answer(
    client, db_url, seeded_provider
):
    from pydantic_ai.models.test import TestModel

    from app.main import app
    from app.qa_routes import get_qa_clock
    from tests.qa_fixtures import publish_passages
    from tests.test_qa import ask, ask_body, evidence, install_model, supported

    day = date(2026, 11, 23)
    app.dependency_overrides[get_qa_clock] = lambda: lambda: day
    quote = "ADEX is required."

    def passage(text):
        return [{"section": "Application", "text": text, "page": 1}]

    async def seed():
        async with create_pool(db_url) as pool:
            repo = KnowledgeRepository(pool)
            await publish_passages(
                repo,
                "ned-instructions",
                {"revision": "Future fixture", "effective_from": "2026-11-24"},
                passage("NED application guidance."),
            )
            return await publish_passages(
                repo,
                "dentist-application",
                {"revision": "Current fixture"},
                passage(quote),
            )

    version = asyncio.run(seed())

    class AfterMidnight(TestModel):
        async def request(self, messages, model_settings, model_request_parameters):
            nonlocal day
            day = date(2026, 11, 24)
            return await super().request(
                messages, model_settings, model_request_parameters
            )

    install_model(
        AfterMidnight(custom_output_args=supported(evidence(version.chunks[0].id)))
    )
    answer = ask(client, ask_body(seeded_provider))
    assert answer["outcome"] == "supported"
    assert answer["outdated"] is False
    assert client.get(f"/qa/{answer['id']}").json() == answer


@pytest.mark.parametrize(
    "question,requirement,topic,source,quote",
    [
        (
            "Is Form 224a used for renewal?",
            "Hawaii dental license",
            "dental",
            "dea-registration",
            "Use Form 224a for renewal.",
        ),
        (
            "Do I need in-person BLS skills under the virtual waiver?",
            "State NED license",
            "ned",
            "virtual-ce-waiver",
            "BLS skills must be demonstrated in person.",
        ),
    ],
)
def test_unidentified_question_family_reaches_cross_topic_source_in_either_row(
    client, db_url, seeded_provider, question, requirement, topic, source, quote
):
    from pydantic_ai.models.test import TestModel

    from tests.qa_fixtures import publish_passages
    from tests.test_qa import ask, ask_body, evidence, install_model

    async def seed():
        async with create_pool(db_url) as pool:
            return await publish_passages(
                KnowledgeRepository(pool),
                source,
                {"revision": "Synthetic scope test"},
                [{"section": "Renewal", "page": None, "text": quote}],
            )

    version = asyncio.run(seed())
    install_model(
        TestModel(
            custom_output_args={
                "outcome": "supported",
                "claims": [
                    {
                        "text": quote,
                        "citations": [evidence(version.chunks[0].id, quote)],
                    }
                ],
            }
        )
    )
    requirement_id = next(
        r.id for r in seeded_provider.requirements if r.name == requirement
    )
    answer = ask(
        client, ask_body(seeded_provider, question, requirement_id=requirement_id)
    )
    assert answer["topic_hint"] == topic
    assert answer["outcome"] == "supported", question
    assert answer["claims"][0]["citations"][0]["version_id"] == version.id


def test_broad_questions_from_either_row_retrieve_all_configured_topics(
    client, db_url, seeded_provider
):
    import psycopg

    from app.knowledge_models import KnowledgeScope
    from app.knowledge_sources import manifest
    from tests.qa_fixtures import publish_passages
    from tests.test_qa import ask, ask_body

    by_topic = {source.topic: source.source_key for source in manifest()}
    extras = {"statutory", "internal"}

    async def seed():
        async with create_pool(db_url) as pool:
            repo = KnowledgeRepository(pool)
            versions = []
            for topic, source in by_topic.items():
                labels = {topic} | (extras if source == "internal-guide" else set())
                versions.append(
                    await publish_passages(
                        repo,
                        source,
                        {"revision": "Synthetic scope test"},
                        [
                            {
                                "section": "Renewal",
                                "page": None,
                                "text": "Review license renewal guidance.",
                            }
                        ],
                        scopes=[
                            KnowledgeScope(
                                provider_type="Dentist", jurisdiction="HI", topic=label
                            )
                            for label in sorted(labels)
                        ],
                        publish_now=False,
                    )
                )
            return versions

    versions = asyncio.run(seed())
    for version in versions:
        response = publish(client, version.id)
        assert response.status_code == 200, response.text
    for requirement in ("Hawaii dental license", "State NED license"):
        requirement_id = next(
            r.id for r in seeded_provider.requirements if r.name == requirement
        )
        answer = ask(
            client,
            ask_body(
                seeded_provider,
                "Which renewal guidance applies?",
                requirement_id=requirement_id,
            ),
        )
        with psycopg.connect(db_url) as conn:
            captured = conn.execute(
                "SELECT topic FROM qa_run_topics WHERE run_id=%s", (answer["id"],)
            ).fetchall()
            ranked = conn.execute(
                "SELECT version_id,keyword_rank,vector_rank FROM qa_retrieved_chunks WHERE run_id=%s",
                (answer["id"],),
            ).fetchall()
        assert {row[0] for row in captured} == by_topic.keys() | extras
        assert {vid for vid, keyword, vector in ranked if keyword and vector} == {
            version.id for version in versions
        }


async def publish_education_sources(db_url, provider_type="Dentist"):
    from tests.qa_fixtures import publish_passages

    async with create_pool(db_url) as pool:
        repo = KnowledgeRepository(pool)
        versions = {}
        for source, excerpt in (
            (
                "prescriber-education",
                "NED prescriber education on controlled medications.",
            ),
            ("dea-training", "DEA MATE education on opioid prescribing."),
            ("board-renewal", "Dental license continuing education for renewal."),
        ):
            version = await publish_passages(
                repo,
                source,
                {"revision": "Fixture"},
                [{"section": "CE", "text": excerpt, "page": 1}],
                provider_type=provider_type,
            )
            versions[source] = version.id
        return versions


@pytest.mark.parametrize(
    "question,include_dental",
    [
        ("Which continuing education do I need for opioid prescribing?", False),
        ("What CE is required for dentists prescribing controlled medications?", False),
        ("Does dental license CE include education on opioid prescribing?", True),
        (
            "Can dentists count CE for both license renewal and opioid prescribing?",
            True,
        ),
        ("What continuing education do I need?", True),
        (
            "Does the continuing education I take to renew my dentist license also count for DEA MATE training?",
            True,
        ),
        ("Does dental license CE count toward MATE training?", True),
        ("Can CE for my dental license satisfy MATE requirements?", True),
        (
            "Can CE for my Hawaii dental board license renewal also count toward DEA MATE training?",
            True,
        ),
        (
            "Does CE for my license to practice dentistry also satisfy DEA training?",
            True,
        ),
    ],
)
def test_education_questions_keep_prescriber_evidence_in_both_search_paths(
    client, db_url, seeded_provider, question, include_dental
):
    from tests.test_qa import ask, ask_body

    versions = asyncio.run(publish_education_sources(db_url))
    required = {versions["prescriber-education"], versions["dea-training"]}
    if include_dental:
        required.add(versions["board-renewal"])
    row = next(
        r for r in seeded_provider.requirements if r.name == "Hawaii dental license"
    )
    answer = ask(client, ask_body(seeded_provider, question, requirement_id=row.id))
    assert answer["topic_hint"] == "dental"
    captured, ranked = captured_and_ranked_education_sources(db_url, answer["id"])
    assert required <= captured
    assert required <= ranked


def captured_and_ranked_education_sources(db_url, run_id):
    import psycopg

    with psycopg.connect(db_url) as conn:
        captured = conn.execute(
            "SELECT version_id FROM qa_corpus_versions WHERE run_id=%s", (run_id,)
        ).fetchall()
        ranks = conn.execute(
            "SELECT version_id,keyword_rank,vector_rank FROM qa_retrieved_chunks WHERE run_id=%s",
            (run_id,),
        ).fetchall()
    return (
        {version for (version,) in captured},
        {version for version, keyword, vector in ranks if keyword and vector},
    )


@pytest.mark.parametrize(
    "question,provider_type,eligible_keys",
    [
        (
            "Which continuing education do I need to renew my dental hygienist license?",
            "Dental Hygienist",
            {"board-renewal"},
        ),
        (
            "As a dentist, which education does the DEA require for renewal?",
            "Dentist",
            {"prescriber-education", "dea-training"},
        ),
    ],
)
def test_education_search_respects_qualified_license_and_profession_only_mentions(
    client, db_url, seeded_provider, question, provider_type, eligible_keys
):
    from app.models import StoredProvider
    from tests.fixtures.current_database import configure_catalog
    from tests.test_provider_creation import body, create
    from tests.test_qa import ask, ask_body

    provider = seeded_provider
    if provider_type != seeded_provider.provider_type:
        template = configure_catalog(
            provider_type, ["Professional license"], url=db_url
        )
        provider = StoredProvider.model_validate(
            create(client, body(provider_type_id=template.id))
        )
    versions = asyncio.run(publish_education_sources(db_url, provider_type))
    answer = ask(client, ask_body(provider, question))
    assert answer["provider_type"] == provider_type
    captured, ranked = captured_and_ranked_education_sources(db_url, answer["id"])
    expected = {versions[key] for key in eligible_keys}
    assert captured == expected
    assert ranked == expected
