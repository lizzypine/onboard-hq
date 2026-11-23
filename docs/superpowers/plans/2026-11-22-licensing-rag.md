# Licensing RAG Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** Let both simulated roles ask Hawaii Dentist licensing questions and receive retained, precisely cited evidence from Manager-published sources.

**Architecture:** Store versioned source content, passages, full-text indexes, and pgvector embeddings in the existing PostgreSQL database. A separate read-only Pydantic AI agent receives a bounded hybrid-retrieval snapshot; validated answers and citations are saved independently of progress review. Native dialogs provide compact asking and source-management workflows.

**Tech Stack:** Python 3.13, FastAPI, Pydantic AI, psycopg, PostgreSQL 18, pgvector 0.8.7, pypdf, vanilla JavaScript, Playwright.

**Spec:** `docs/superpowers/specs/2026-11-22-licensing-knowledge-design.md`, Ask AI/source/retrieval sections; `docs/database-design.md`, Licensing substeps and knowledge section.

## Global Constraints

- Keep `docs/proposal.md` unchanged. This plan implements RAG only; saved licensing substeps remain a separate target.
- Both simulated roles may ask; only `manager` may edit/publish/withdraw guidance. The API retains `proposer` as the Non-manager value. This is not authenticated access control.
- Preserve free-text updates, parent review, dates, Add provider, lifecycle, and checklist membership. Ask AI never changes progress or calls mutation tools.
- No original internal business addresses, site names, named staff, or staff email addresses in committed source content or fixtures. Use main office and functional contact roles; missing locations remain unanswered.
- Use controlled configured source identifiers, not arbitrary fetch/upload routes. Include initial dental, renewal/CE, NED/PDMP, DEA, and a sanitized internal draft.
- Use exact cosine search plus PostgreSQL full-text search over identical eligible versions, reciprocal rank fusion, retained section context, and a bounded context budget. No approximate index, graph database, or external vector service.
- The default embedding space is `text-embedding-3-small`, version `1`, dimensions `1536`; use the existing gateway/token without changing generation configuration. Different spaces never mix.
- Release database connections before embedding/generation/fetch work. Store original bytes/text and exact locators; published evidence and publication audit are immutable.
- Preserve distinct integer resource IDs and UUID operation/request IDs. Relational ownership, scopes, candidates, claims, and citations; no JSON relationship collections.
- Publish only complete indexed versions, atomically supersede, retain withdrawals, and increment a corpus revision. Recheck revision before returning generated answers; outdated evidence requires explicit re-asking.
- Outcomes are Supported answer, More information needed, Conflicting guidance, Cannot answer from the available information, and Service unavailable. Validate supplied passage IDs and exact quoted character spans; invalid model output must not become a supported answer.
- Automated tests use disposable local PostgreSQL, deterministic embeddings and `TestModel` with real requests disabled. Independently block real fetch/embedding requests. Never migrate/seed/test against configured Neon during implementation.
- Run Ruff, mypy, and the full offline pytest suite before each task commit. No weakened checks, skipped tests, noqa, or type ignores.

## Review Focus

- Publication/withdrawal races and lost responses: retained retry identity and corpus revision prevent stale evidence from appearing current (Tasks 1–2).
- Provider changes and modal close while generation runs: answers and frozen requests remain scoped to their captured provider and reconcile by reads (Tasks 2–3).
- Malicious question/source text and fabricated citation spans: plain-text DOM, no tools, validation failure, and no progress writes (Tasks 2–3).
- Applicable-period/type mismatches and rule exceptions: both retrieval paths filter the same snapshot; section expansion preserves qualifications (Task 2).
- Failed source reindex, stale draft edit, or incomplete embeddings: previous publication survives and Manager sees a recoverable failure (Tasks 1, 3).

## File boundaries

`app/knowledge_models.py` owns source/publication and passage contracts; `app/embeddings.py` owns the embedding adapter; `app/knowledge_sources.py` owns controlled fetching/extraction/chunking and its CLI. `app/knowledge.py` orchestrates Manager edits/indexing/publication with pure rules in `app/rules/knowledge.py`; `app/repository/knowledge.py` owns source transactions.

`app/qa_models.py` owns QA contracts, `app/qa_agent.py` generation, `app/retrieval.py` fusion/context selection, `app/qa.py` request orchestration, `app/rules/qa.py` citation/scope validation, and `app/repository/qa.py` captured requests/search/audit transactions. `app/knowledge_routes.py` and `app/qa_routes.py` only wire dependencies/errors; share pool dependency through a focused module if needed while preserving existing test overrides.

`app/static/ask-ai.js`, `app/static/knowledge-manager.js`, and `app/static/knowledge.css` own native dialogs and source/answer presentation. `onboarding.js` only passes coherent selected-provider/role context. Update AGENTS Layout as modules are added.

### Task 1: Versioned sources, embeddings, and Manager publication

**Files:** Create the knowledge/source/embedding modules above, `db/migrations/20261122000200_knowledge_sources.sql`, `scripts/install-pgvector.sh`, a bounded source manifest under `knowledge/`, a sanitized internal guide, `tests/test_knowledge.py`, `tests/test_knowledge_sources.py`, `tests/knowledge_fixtures.py`. Modify `app/main.py`, `AGENTS.md`, `.env.example`, README, database design/schema, test cleanup/upgrade expectations, and CI/local provisioning as required.

**Interfaces:**
- `EmbeddingClient` protocol: `model: str`, `version: str`, `dimensions: int`, `async embed(texts: list[str]) -> list[list[float]]`. `get_embedding_client()` is the FastAPI override point; default uses gateway embeddings with timeout, finite/nonzero/dimension/count validation, and sanitized errors. Deterministic implementation belongs in tests.
- `KnowledgeRepository(pool)` exposes `list_documents()`, `get_version(version_id)`, and `corpus_snapshot(provider_type: str, jurisdiction: str, as_of: date)` returning revision, active space, eligible versions, and immutable scoped chunks. Name returned Pydantic types `KnowledgeDocument`, `KnowledgeVersion`, `KnowledgeChunk`, `EmbeddingSpace`, `CorpusSnapshot`. `KnowledgeChunk` includes id/version_id/text/section/page/char_start/char_end; scope membership is relational. Document/version metadata include source kind, original URL, title, publisher, stated revision, retrieval/review/effective dates, checksum and retained original bytes.
- Source HTTP: `GET /knowledge/documents`; `GET /knowledge/versions/{id}`; `GET /knowledge/versions/{id}/original`; `POST /knowledge/documents/{id}/drafts`; `PUT /knowledge/versions/{id}`; `POST /knowledge/versions/{id}/publish`; `POST /knowledge/versions/{id}/withdraw`; `GET /knowledge/operations/{operation_id}`. Writes carry `X-Demo-Role`, distinct `operation_id`, and optimistic draft revision where applicable. Draft creation/edit bodies expose text/revision/scopes and review issues; publish explicitly confirms review, excludes unresolved issues, and indexes outside transactions before committing. Publish/withdraw retry responses reconcile by operation ID; conflicting reuse is 409.
- CLI `uv run python -m app.knowledge_sources list` and `... ingest SOURCE_ID` uses only allowlisted manifest sources and stores drafts; it never auto-publishes. Optional internal draft import is explicit. No fetch/seed at startup.

- [ ] Write failing tests for draft role enforcement, source locator correctness, no address/contact leakage, immutable published evidence, complete-vector gate, atomic supersession, withdrawal retention, stable operation retries/conflicts, draft concurrency, reindex failure, independent embedding/fetch network guards, and real vector dimension constraints. Tests exercise source routes, not only mocks.
- [ ] Run the focused tests and record the expected RED output before implementation.
- [ ] Add pgvector 0.8.7 provisioning for PostgreSQL 18, with pinned/checksummed source and appropriate CI service image. Install locally only as needed for disposable tests. Never touch Neon. Add source relations from the database design plus a singleton `knowledge_state` corpus revision/active-space record; add real FK/delete policies, audit immutability, and vector-space checks. Model changes create inactive spaces; reindex all eligible source versions before atomic activation (expose explicit CLI activation command).
- [ ] Implement retained PDF/page and HTML-heading extraction, bounded section-aware chunks with exact spans, source provenance, independent embedding adapter, versioned drafts and publication. Configure the full initial inventory from the design, including HRS/HAR, CE waiver/sponsors, NED attestations/education/help, PDMP destinations, DEA registration/manual/training/FAQ. Source collection is bounded; preserve unknown dates, and never infer them from URLs. Internal draft has unresolved contact/PDMP issues and cannot publish until reviewed.
- [ ] Verify focused tests and full `bash scripts/test.sh uv run pytest`, Ruff and mypy. Regenerate `db/schema.sql` only from disposable local schema. Update database design to distinguish implemented sources from pending QA/substeps. Commit source foundation without pushing.

### Task 2: Hybrid retrieval, cited answers, and persistent QA

**Files:** Create the QA/retrieval modules above, `db/migrations/20261122000300_knowledge_answers.sql`, `tests/test_retrieval.py`, `tests/test_qa.py`, `tests/fixtures/licensing_questions.json`. Modify main/router wiring, knowledge repository only for clearly needed read contracts, database design/schema, AGENTS, fixtures, and README.

**Interfaces:**
- Consume Task 1's `EmbeddingClient`, `CorpusSnapshot`, source contracts, and `get_embedding_client()`; inspect Task 1 report for exact finalized field names.
- `AskRequest`: UUID `request_id`, positive integer `provider_id`, optional positive `requirement_id`, nonblank bounded `question`. `SavedAnswer` exposes id/request identity/provider/type/context/question, state (`processing`, `completed`, `failed`), explicit outcome, ordered claims/citations, missing facts/conflict explanation, failure message, captured corpus revision/space/model, created_at, and `outdated`/historical-source warning.
- Model `AnswerDraft` contains explicit outcome, ordered claims with citation references `(chunk_id, quote, start, end)`, missing facts, and conflicts. Only source-supported claims may be returned as supported. Server owns URL/metadata resolution. `build_qa_agent(model=None)` accepts `TestModel`; `get_qa_agent_factory()` is the FastAPI override.
- `POST /qa/ask` claims a UUID before outbound work and returns `SavedAnswer`; `GET /qa/requests/{request_id}` reconciles by UUID; `GET /qa/{answer_id}` returns a retained result; `GET /providers/{provider_id}/answers` lists captured answers separately from Review history. Read-only generation remains available for archived providers. Parent context belongs to selected provider; type/jurisdiction cannot be forged in request.

- [ ] Write failing real-database tests for exact acronym keyword hits, semantic-only hits, rank fusion/deduplication, complete section/exception expansion, strict shared eligibility/type/effective-period filtering, no-evidence abstention, source outage versus abstention, missing-personal-facts, explicit type mismatch, malicious source/question, forged quote/IDs/spans, no progress writes, retained citations after withdrawal, and publish-during-generation outdated handling.
- [ ] Add UUID identical retry/conflicting reuse/in-flight tests, scoped requirement validation, no connection held across model/embedding work, terminal sanitized failure, and independent no-network guards in all automated layers. Record RED before product code.
- [ ] Implement exact cosine plus full-text queries over captured eligible version IDs, rank up to 20 per path with RRF constant 60, at most 12 final passages and 24,000 characters including adjacent same-section context. Persist both-path ranks and fused order before generation. Avoid presenting unrelated nearest vectors as evidence; use reviewed retrieval outcomes and model abstention rather than claiming score thresholds prove correctness.
- [ ] Persist `qa_runs`, `qa_corpus_versions`, `qa_retrieved_chunks`, `qa_claims`, `qa_citations` with relational ownership/immutability and stable request identity. Claim before outbound calls, release connections for embedding/generation, then validate/persist atomically against corpus revision. Invalid generated references/spans produce Service unavailable; supported claims require citations. No mutation/network tools on the answer agent and no automatic model retries/replay of a saved request.
- [ ] Convert every representative question in the spec into source-version-bound evaluation cases with required facts, quotes/locators, exceptions, and prohibited claims. Use short official-source excerpts with exact provenance and deterministic embeddings/TestModel offline; never commit original private contact/address data. Distinguish these structural/retrieval checks from a real-model semantic quality evaluation, which is not an automated test. Do not claim live quality has been measured if it has not.
- [ ] Verify focused/full tests, Ruff, mypy; regenerate schema locally and update database design implemented QA/remaining substeps, record new route contracts in report for Task 3. Commit without pushing.

### Task 3: Compact Ask AI and source-management dialogs

**Files:** Create `app/static/ask-ai.js`, `app/static/knowledge-manager.js`, `app/static/knowledge.css`, `tests/e2e/test_ask_ai.py`, `tests/e2e/test_knowledge_manager.py`; modify `app/page.py`, `app/static/onboarding.js`, browser test server overrides, README, AGENTS, spec as needed.

**Interfaces:**
- Consume source and QA endpoints/contracts finalized in reports from Tasks 1–2. No source/QA loading or persistence calls go in `checklist.js`, `review.js`, or `providers.js`.
- `setupAskAI({api, getProvider, getRole})` returns `syncProvider(provider)`, `setBusy(value)`, and optional `open(requirementId)`; the controller owns dialog/request state and read-only reconciliation. Integration calls sync on coherent provider selection and clear. Source manager gets role/provider scope through callbacks, independently handles frozen publication operations and read-only reconciliation.

- [ ] Write browser tests first for initially closed modal, button/Escape/Close/focus return/autofocus, both roles/archived access, citations with exact quote/locator/original view, separate saved-answer history, unsupported/missing/conflict/unavailable outcomes, stale corpus warning, and no checklist progress mutation. Record RED.
- [ ] Write tests for switching provider during a delayed answer, close/reopen while processing (one POST, read reconciliation), reload/history retrieval, changed-input UUID safety, keyboard behavior, safe malicious text, 390px overflow/scroll, and Manager-only source draft edit/preview/publish/withdraw/retry. Add explicit regression checks for Original update and Add provider.
- [ ] Implement compact heading button with decorative three-sparkle icon and native `dialog`, escaped plain text/Markdown preview, suggested questions, structured outcome/claims/citations, and independently collapsible answer history. Scope generation tokens to provider; never automatically replay a write after an uncertain response. Keep source/editor dialogs equally accessible. Show no source claim that draft internal instructions are available to Ask AI.
- [ ] Fix source section padding with 20px card padding, no duplicate first-row separator, centered naturally sized badges, and phone wrapping. No persistent AI panel, no per-step UI in this RAG task. Backend unavailability must not break parent checklist/loading/update/creation.
- [ ] Run focused browser tests then full suite, Ruff/mypy, inspect real screenshots desktop/390px. Update README setup/ingest/publish/reindex/operator instructions and accurately state separate Neon migration approval, published-source prerequisites, remaining substeps, and unmeasured live quality. Commit without pushing.

## Completion

- [ ] Whole-branch review and fixes using the required review skill; run remaining checks only when changes or concerns justify them.
- [ ] Audit new commit content for private addresses, site names, and staff emails. Preserve the approved main-office wording. Do not rewrite existing published history.
- [ ] Refresh existing PR #29 title/Summary/Test plan and one validated code-backed Mermaid diagram; cite `docs/proposal.md` and the exact database-design section. Push this feature branch, watch PR checks, report their actual result. Never merge.
- [ ] Prepare concrete application migration/ingestion instructions and identify any activation approval needed. Do not apply schema changes or ingest/publish into Neon during this implementation.
