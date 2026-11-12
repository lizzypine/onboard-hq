# Persistent Manager Review Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Persist the synthetic provider's checklist, extracted suggestions, and manager decisions in Neon, with dbmate migrations and automated unit, integration, and browser tests.

**Architecture:** PostgreSQL stores provider types/templates separately from individual checklists and immutable update evidence. Psycopg repositories own short transactions; plain Python rules decide review eligibility and values; FastAPI transports Pydantic contracts. Model extraction happens outside transactions, and the browser reloads saved state after decisions.

**Tech Stack:** Existing Python 3.13+/FastAPI/Pydantic AI; Pydantic 2.14.1; Psycopg 3.3.8 with binary distribution; psycopg-pool 3.3.3; dbmate 2.38.1; PostgreSQL 18; pytest-playwright 0.10.0; Playwright 1.65.1 with Chromium. Pin Python additions in `pyproject.toml`/`uv.lock`; pin the dbmate download/checksum and CI installation. Keep the existing dependencies otherwise.

**Spec:** [Persistent Review with Neon and dbmate](../specs/2026-11-11-persistent-review-design.md), together with [the project proposal](../../proposal.md).

## Global Constraints

- Anyone can propose an update; a manager approves changes.
- A simulated role is sufficient for now. Do not add sign-in or user accounts.
- Keep the existing single synthetic dentist and five checklist requirements as the initial fixture.
- Individual checklist exceptions remain undecided; do not add exception controls, new clinical requirements, or a dental-hygienist production fixture.
- Changing a template must not silently add, remove, or change existing checklist entries.
- Model extraction, requirement scope filtering, and incomplete-date inference retain their existing contracts. Do not use today's date as a fallback reference.
- A drug-screen appointment date is distinct from its deadline: applying a proposed date must never overwrite a deadline.
- All automated model work uses `TestModel` with real model requests disabled, including the server process used by end-to-end tests.
- Use a separate `TEST_DATABASE_URL`; never migrate, truncate, or roll back the Neon application database in automated tests.
- Use `DATABASE_URL` for the app and `DATABASE_URL_UNPOOLED` for dbmate. No credentials in code, command-line URL arguments, logs, model inputs, or browser responses.
- No automatic migrations/seeding on app startup. Neon receives only forward migrations and the explicit synthetic seed during final verification.
- Run Ruff, mypy, and the complete pytest suite after each task. No skipped tests, ignored type/lint errors, or weakened checks.
- Local/cloud OpenCode routing remains future work; preserve the injectable agent factory.
- Use a dedicated implementation branch. Open a PR, apply the PR-diagram skill, and watch CI; the user merges.

## Review Focus

1. A retried request ID with different text/provider must conflict; an identical completed/failed request must not call the model again (Task 3).
2. Two managers reviewing the same suggestion, or two suggestions for a changed requirement, must not overwrite newer state or create duplicate decisions (Task 4).
3. Editing/clearing a date must preserve omission semantics and inferred-date confirmation, without changing deadlines (Tasks 2, 4, 5).
4. Seed reruns/template changes must not backfill or overwrite an established checklist; mismatched type/template links must fail (Tasks 1, 2).
5. A missing database, interrupted extraction, or invalid model response must leave honest saved state and safe errors, never fabricated success or secret-bearing exceptions (Tasks 1, 3, 5).

## Files and Responsibilities

| File | Responsibility |
| --- | --- |
| `db/migrations/20261111000100_create_onboarding_records.sql`, `db/schema.sql` | Seven application tables, constraints/indexes, and a generated schema-only dump. |
| `scripts/install-dbmate.sh`, `scripts/test.sh` | Pinned dbmate installation; isolated PostgreSQL test environment and cleanup. |
| `app/database.py` | Validated connection settings, bounded async pool, safe configuration/unavailable exceptions. |
| `app/models.py` | Shared existing extraction-context contracts plus typed database/read/write/review contracts. |
| `app/agent.py`, `app/updates.py` | Retain model-specific extraction and deterministic processing; import shared contracts from models. |
| `app/repository/providers.py`, `app/repository/updates.py`, `app/repository/reviews.py` | Provider reads/initialization, saved analysis lifecycle, atomic review SQL. |
| `app/seed.py` | Explicit idempotent synthetic fixture command, using type templates. |
| `app/rules/review.py`, `app/reviews.py` | Pure review decisions and saved-analysis/review orchestration. |
| `app/main.py`, `app/page.py`, `app/static/onboarding.js` | HTTP wiring, page markup, and browser interaction, respectively. |
| `tests/__init__.py`, `tests/database.py`, existing `tests/conftest.py` | Unambiguous local test-helper imports, guarded disposable test database, TestModel overrides, fixture setup/cleanup. |
| `tests/test_database.py`, `tests/test_migrations.py`, `tests/test_models.py`, `tests/test_repository.py`, `tests/test_saved_updates.py`, `tests/test_review_rules.py`, `tests/test_reviews.py` | Unit and PostgreSQL integration contracts. |
| `tests/e2e/__init__.py`, `tests/e2e/server.py`, `tests/e2e/conftest.py`, `tests/e2e/test_review_workflow.py` | Importable test-only server with TestModel, real browser/app/PostgreSQL workflow. |
| `README.md`, `.env.example`, `.github/workflows/tests.yml`, `AGENTS.md` | Actual setup/commands, placeholder settings, PostgreSQL/browser CI, current module layout. |

The repository package replaces the design's suggested single `repository.py` by responsibility. Update AGENTS.md as modules are created. Keep source-template IDs and versions out of model instructions unless required for the existing context; SQL metadata is not model evidence.

## Task 1: Migrations and an Isolated PostgreSQL Test Environment

**Files:** Create the migration/schema, `app/database.py`, `scripts/install-dbmate.sh`, `scripts/test.sh`, `tests/__init__.py`, `tests/database.py`, `tests/test_database.py`, `tests/test_migrations.py`. Modify `pyproject.toml`, `uv.lock`, `.env.example`, `README.md`, `.github/workflows/tests.yml`, `AGENTS.md`.

**Interfaces:**
- `app.database.database_url() -> str`: read/validate PostgreSQL `DATABASE_URL` without printing it; raise `DatabaseConfigurationError` with safe text.
- `app.database.DatabasePool = AsyncConnectionPool[AsyncConnection[dict[str, Any]]]` and `create_pool(url: str) -> DatabasePool`: Psycopg `dict_row` at the SQL boundary, `open=False`, `min_size=0`, `max_size=4`, `connect_timeout=10`, checkout `timeout=10`; explicitly open/close in app lifespan later. Repository results must be validated into the typed models in Task 2. Wrap database failures as `DatabaseUnavailable` at the repository boundary.
- `tests.database.require_disposable_database(test_url: str, application_url: str | None) -> None`: accept only loopback PostgreSQL databases named `onboard_hq_test_*`; reject malformed URLs, the application target, and remote hosts. Compare normalized database identity, including Neon pooled/direct host equivalence, without exposing credentials.
- `tests.database.migrate_test_database(url: str) -> None`: validated target only, pass URL by child environment, not command argument. All new database fixtures call the guard before any write.
- `bash scripts/test.sh uv run pytest`: use an existing validated `TEST_DATABASE_URL`, or start PostgreSQL 18 in a temporary cluster bound to loopback, set its test URL for the child, and clean up on success/failure. Never load `.env` as test credentials.

- [ ] **Step 1: Write failing database/migration tests.** Unit tests reject missing/invalid settings and an application URL supplied as a test URL; assert secret-like sentinel passwords do not appear in exceptions. Integration tests on an isolated database assert the seven tables, FK/unique/CHECK constraints, no duplicate review, cross-provider suggestion rejection, and type/template consistency. For example:

```python
def test_test_database_guard_rejects_neon_application_url():
    url = "postgresql://user:sentinel-secret@ep-demo-pooler.neon.tech/app"
    with pytest.raises(ValueError) as error:
        require_disposable_database(url, url.replace("-pooler", ""))
    assert "sentinel-secret" not in str(error.value)
```

- [ ] **Step 2: Run `uv run pytest tests/test_database.py tests/test_migrations.py -v`.** Expect failure from missing database code/migration, not a live Neon access attempt. Existing tests remain unchanged.
- [ ] **Step 3: Install the pinned driver/pool dependencies and dbmate.** Use official dbmate 2.38.1 release assets with a checked-in checksum; make the installer fail on mismatch. Install PostgreSQL 18 tools alongside the machine's current PostgreSQL 14 tools, without replacing/stopping its service. Use a private temporary local cluster for test data. Neon was read-only verified as PostgreSQL 18.6; a PostgreSQL 18 `pg_dump` is required for its schema dump. Document the PATH/tool setup and placeholder-only URL examples.
- [ ] **Step 4: Implement the schema and configuration/test helpers.** Use application-generated UUID PKs and `timestamptz` audit times. Define:
  - `provider_types(id, name UNIQUE)`; `requirement_templates(id, provider_type_id FK, name, UNIQUE(provider_type_id, name))`.
  - `providers(id, provider_type_id FK, name, proposed_start_date)`; `requirements(id, provider_id, provider_type_id, source_template_id NULL, name, status, deadline NULL, scheduled_date NULL, version DEFAULT 0, UNIQUE(provider_id, name))`.
  - Enforce matching types with composite parent keys/FKs: requirement `(provider_id, provider_type_id)` references providers, and nullable `(source_template_id, provider_type_id)` references templates. Restrict referenced-row deletion. Add `UNIQUE(id, provider_id)` to requirements and updates for the suggestion FKs below.
  - `updates(id, request_id UNIQUE, provider_id FK, original_text, provider_snapshot JSONB, processing_state, message, ambiguities JSONB, failure_category NULL, created_at, completed_at NULL)`; states are `processing/completed/failed`, warnings are JSON arrays, and original message is nonblank.
  - `suggestions(id, update_id, requirement_id, provider_id, requirement_version, proposed_status, proposed_date NULL, supporting_text, date_text NULL, date_inferred, date_explanation NULL, date_requires_confirmation, created_at)`; composite FKs to update and requirement enforce one provider. Model output/evidence is not overwritten by review.
  - `review_decisions(id, suggestion_id UNIQUE FK, outcome, previous_status, previous_scheduled_date NULL, applied_status NULL, applied_scheduled_date NULL, reviewer_role, reviewed_at)`; outcomes `approved/corrected/rejected`, reviewer role `manager`. Rejections have no applied values; previous values always reflect the actual checklist at decision time.
  - Nonblank names/statuses, nonnegative versions, required FKs, and indexes for provider update chronology, update suggestions, and review lookups. Down migration removes application tables in reverse dependency order, only for disposable verification.
- [ ] **Step 5: Run migration verification on disposable PostgreSQL.** `migrate` creates the schema; a second run is a no-op. On a separate disposable database, rollback/reapply restores the schema. Generate and commit `db/schema.sql` from the isolated PostgreSQL 18 database, excluding records/credentials. Add a PostgreSQL 18 service and `TEST_DATABASE_URL` to CI; no application database secret is needed.
- [ ] **Step 6: Run `uv run ruff check`, `uv run mypy`, and `bash scripts/test.sh uv run pytest`; commit `feat: add dbmate schema and isolated PostgreSQL tests`.** All existing tests plus migration/configuration tests pass; no skipped tests.

## Task 2: Typed Stored Records, Provider Reads, and Safe Seeding

**Files:** Create `app/models.py`, `app/repository/__init__.py`, `app/repository/providers.py`, `app/seed.py`, `tests/test_models.py`, `tests/test_repository.py`. Modify `app/agent.py`, `app/updates.py`, `app/main.py`, `tests/conftest.py`, README/AGENTS as needed.

**Interfaces:**
- Move existing `Requirement`, `ProviderContext`, `AnalyzeUpdateRequest`, `SuggestedChange`, and `AnalyzeUpdateResponse` unchanged to `app/models.py`; keep explicit re-exports in `app/agent.py` for current callers. Model-specific `MentionedDate`, `ExtractedSuggestion`, `ExtractionResult`, and agent construction remain there.
- `StoredRequirement(Requirement)`: add `id: UUID`, `provider_id: UUID`, `source_template_id: UUID | None`, `scheduled_date: date | None`, `version: int` (nonnegative).
- `ProviderSummary`: `id: UUID`, `name: str`, `provider_type: str`, `proposed_start_date: date | None`; `StoredProvider(ProviderSummary)` adds `requirements: list[StoredRequirement]`.
- `to_provider_context(provider: StoredProvider) -> ProviderContext`: serialize UUID as provider ID string and map only current requirement fields required by extraction.
- `ProviderRepository(pool)` with `async list_providers() -> list[ProviderSummary]`, `async get_provider(provider_id: UUID) -> StoredProvider`, and `async initialize_provider(provider: ProviderSummary, provider_type_id: UUID, initial_values: dict[str, Requirement]) -> bool`. Initialization copies that type's templates exactly once in one transaction; true means newly created. Raise `RecordNotFound` for unknown IDs.
- `async seed_synthetic(pool) -> None` in `app/seed.py`; command `uv run --env-file .env python -m app.seed`. Stable IDs use UUID5 with `NAMESPACE_URL` and `onboard-hq:type:dentist`, `onboard-hq:provider:kekoa-ejemplo`, and `onboard-hq:template:dentist:<canonical name>` / `onboard-hq:requirement:kekoa-ejemplo:<canonical name>`. Export `KEKOA_ID` for tests.
- `GET /providers` returns summaries; `GET /providers/{provider_id}` returns `StoredProvider`. `get_repository` is an overridable FastAPI dependency. Lifespan owns the pool; importing app or requesting HTML does not connect.
- Extend `tests/conftest.py` with a `seeded_provider: StoredProvider` fixture, initialized in the guarded test database. DB-backed `client` instances use that database; unit tests do not request these fixtures.

- [ ] **Step 1: Write failing model/repository/HTTP tests.** Verify typed UUID/date serialization, distinct provider-type checklists from synthetic test templates, and source-template type rejection. Seed twice, change a saved status, add a new template, then seed again: the saved status and checklist membership must remain unchanged. Template renaming must not alter existing instance names. Unknown provider returns 404; unavailable schema/database produces safe 503; `GET /` remains available without DB settings.

```python
def test_provider_read_uses_stored_checklist(client, seeded_provider):
    response = client.get(f"/providers/{seeded_provider.id}")
    assert response.status_code == 200
    data = response.json()
    assert data["provider_type"] == "Dentist"
    assert {r["name"]: r["status"] for r in data["requirements"]}["Drug screening"] == "Scheduled"
    assert len(data["requirements"]) == 5
```
- [ ] **Step 2: Run `bash scripts/test.sh uv run pytest tests/test_models.py tests/test_repository.py -v`; expect failures for missing interfaces.** Keep unit validation tests runnable without PostgreSQL.
- [ ] **Step 3: Implement the contracts, provider SQL, and seed.** Add direct `pydantic==2.14.1` dependency because application models import it. Preserve the existing fixture exactly: Dr. Kekoa Ejemplo, Dentist, start `2026-12-01`; Offer letter Signed, Hawaii dental license Received, Drug screening Scheduled, State NED license Outstanding, Insurance credentialing Pending. Deadlines and scheduled dates start unset. Insert missing reference templates, but initialize all requirements only when creating a provider; never backfill an established checklist. Do not add a hygienist fixture or real clinical rules.
- [ ] **Step 4: Add the read routes/pool lifespan and map repository rows through Pydantic.** Use parameterized SQL/dictionary rows and scoped connections; errors reveal no DSN/driver exception. Existing analysis remains supported until Task 3 upgrades its transport.
- [ ] **Step 5: Run all three checks using Task 1's verification commands; commit `feat: load typed provider checklists from PostgreSQL`.**

## Task 3: Persist Analysis Requests and Suggestions

**Files:** Create `app/repository/updates.py`, `app/reviews.py`, `tests/test_saved_updates.py`. Modify `app/models.py`, `app/main.py`, page submission code, `tests/conftest.py`, `tests/test_updates.py`, `tests/test_skeleton.py`.

**Interfaces:**
- `SubmitUpdateRequest`: `provider_id: UUID`, `request_id: UUID`, `update_text: str` (trimmed/nonblank), `extra="forbid"`. Do not accept browser-supplied provider context.
- `SavedSuggestion(SuggestedChange)`: add `id: UUID`, `requirement_id: UUID`, `requirement_version: int`, `decision: ReviewDecision | None`. Define `ReviewDecision` fields matching the stored decision schema now; Task 4 produces rows.
- `SavedUpdate`: `id`, `request_id`, `provider_id` UUIDs; original `update_text`, `provider_snapshot: StoredProvider`, `processing_state: Literal["processing", "completed", "failed"]`, `message`, `suggestions: list[SavedSuggestion]`, `ambiguities: list[str]`, `failure_category: Literal["configuration", "timeout", "model"] | None`, `created_at`, `completed_at`.
- `UpdateClaim`: `created: bool`, `update: SavedUpdate`. `UpdateRepository(pool)` supplies `async claim(request: SubmitUpdateRequest) -> UpdateClaim`, `async complete(update_id: UUID, result: AnalyzeUpdateResponse) -> SavedUpdate`, `async fail(update_id: UUID, category: Literal["configuration", "timeout", "model"]) -> SavedUpdate`, `async get(update_id: UUID) -> SavedUpdate`, `async list_for_provider(provider_id: UUID) -> list[SavedUpdate]`.
- `app.reviews.AgentFactory = Callable[[], Agent[None, ExtractionResult]]`; `async submit_update(repository: UpdateRepository, request: SubmitUpdateRequest, agent_factory: AgentFactory) -> SavedUpdate` owns claim/extract/save, using the existing `process_update` on the captured snapshot. No database connection remains checked out during model work.
- `POST /updates/analyze` now accepts `SubmitUpdateRequest` and returns `SavedUpdate` for successful completed analysis. `GET /providers/{provider_id}/updates` returns saved updates; `GET /updates/{update_id}` returns one. Replace agent construction dependency with `get_agent_factory`, returning a callable so configuration failures can be saved after claiming.

- [ ] **Step 1: Write failing service/API integration tests using TestModel.** A valid submission stores original text, snapshot, suggestions and inference metadata but leaves the checklist unchanged. Mix known/unknown requirements, empty output, and unsupported dates; preserve warnings. With start `2027-01-15`, stated day `18` remains inferred `2026-12-18`, including confirmation metadata. Read results through a new app connection after submission.

```python
def test_submission_is_saved_without_mutating_checklist(client, seeded_provider, extraction_model):
    extraction_model.custom_output_args = {"suggestions": [{"requirement": "Drug screening", "proposed_status": "Completed", "supporting_text": "Drug screening completed."}], "ambiguities": []}
    body = {"provider_id": str(seeded_provider.id), "request_id": str(uuid4()), "update_text": "Drug screening completed."}
    response = client.post("/updates/analyze", json=body)
    assert response.status_code == 200
    saved = response.json()
    assert saved["processing_state"] == "completed"
    assert saved["suggestions"][0]["proposed_status"] == "Completed"
    assert client.get(f"/updates/{saved['id']}").json() == saved
    checklist = client.get(f"/providers/{seeded_provider.id}").json()["requirements"]
    assert next(r for r in checklist if r["name"] == "Drug screening")["status"] == "Scheduled"
```

Add a reusable `saved_suggestion` fixture which posts that deterministic case and returns its first saved suggestion, retaining the `seeded_provider` fixture for checklist assertions.
- [ ] **Step 2: Add request lifecycle tests, then run `bash scripts/test.sh uv run pytest tests/test_saved_updates.py -v` expecting missing-interface failures.** Count model calls with a counting test factory: identical completed/failed requests do not call again; different text/provider with the same ID conflicts; concurrent identical requests make one model call and one update. Keep an extraction paused using synchronization events, not sleeps; read the saved update as `processing`, with no reviewable suggestions. A valid DB snapshot is unaffected by a changed/fabricated browser context (the latter is rejected with 422).
- [ ] **Step 3: Implement claim/complete/fail and orchestration.** Claim ID uniqueness and provider/checklist snapshot creation occur in one short transaction. Snapshot reads must be internally consistent. Map names to IDs/versions from that captured snapshot, never current post-extraction rows. Store all suggestions/warnings/completion together. Unknown provider is 404; mismatched/repeated-processing claims return 409. Existing completed/failed claims return their saved result without modifying evidence.
- [ ] **Step 4: Implement safe failure handling and transport.** Persist failure categories and map configuration/timeout/model failures to 503/504/502 respectively, with saved update ID in the safe error envelope. Same-ID retries reproduce that saved failure. A storage outage returns 503; an interrupted/persistence-failed extraction may remain `processing`, visibly unfinished, and has no review candidates. No background recovery/retry loop or successful-looking placeholder. Prove model work has no held DB transaction with another connection acquiring a requirement lock while the test model is paused.
- [ ] **Step 5: Upgrade the existing page minimally to read its selected provider from `/providers`, send provider/request IDs, and render returned suggestions.** Keep the old date-only confirmation behavior temporarily; it remains clearly unsaved until Task 5 replaces it with manager review. Generate one request ID per logical submission and retain it for a network retry of that submission. Update existing endpoint tests to inject the test factory/database while keeping pure `process_update` tests context-based.
- [ ] **Step 6: Run all checks and commit `feat: persist onboarding analysis and pending suggestions`.**

## Task 4: Atomic Manager Decisions with Validation and Conflict Checks

**Files:** Create `app/rules/review.py`, `app/repository/reviews.py`, `tests/test_review_rules.py`, `tests/test_reviews.py`. Modify `app/models.py`, `app/reviews.py`, `app/main.py`.

**Interfaces:**
- `DemoRole = Literal["proposer", "manager"]`; missing `X-Demo-Role` defaults to proposer, invalid values return 422. This header is simulated, not authentication.
- `ReviewRequest` uses `extra="forbid"`, `action: Literal["approve", "correct", "reject"]`, `corrected_status: str | None = None`, `date_action: Literal["preserve", "set", "clear"] = "preserve"`, `corrected_date: date | None = None`, `date_confirmed: StrictBool = False`. Only `correct` accepts correction fields, and it requires a corrected status or a set/clear date action. `set` requires a date; `clear/preserve` reject a supplied corrected date. Reject blank statuses, malformed dates, and forged server-owned fields.
- `ReviewChange`: `outcome: Literal["approved", "corrected", "rejected"]`, `applied_status: str | None`, `applied_scheduled_date: date | None`. `require_manager(role: DemoRole) -> None` and `resolve_review(requirement: StoredRequirement, suggestion: SavedSuggestion, request: ReviewRequest) -> ReviewChange` are pure rules. Failures use typed `ReviewForbidden`, `ReviewConflict`, or `ReviewValidationError` exceptions; no HTTP/SQL imports.
- `ReviewRepository(pool).async decide(suggestion_id: UUID, request: ReviewRequest) -> ReviewDecision` locks/loads rows and atomically persists the resolved result. `async review_suggestion(repository: ReviewRepository, suggestion_id: UUID, request: ReviewRequest, role: DemoRole) -> ReviewDecision` checks manager role before repository mutation.
- `POST /suggestions/{suggestion_id}/review`: 200 decision, 403 valid Proposer attempt, 404 unknown suggestion, 409 already decided/stale, 422 invalid input or missing required date confirmation, 503 storage failure.

- [ ] **Step 1: Write failing unit tests for decision rules and Pydantic requests.** Approve uses original proposed values; corrected approval retains original suggestion; reject has no applied values. No proposed date preserves the saved scheduled date. A corrected `clear` explicitly sets it to null. `date_action="preserve"` on an unedited approval means use the proposal's date if present, otherwise preserve the checklist date. For a corrected approval, preserve follows the same proposal-or-current rule; set/clear are explicit overrides.

```python
def test_invalid_confirmation_is_not_coerced():
    with pytest.raises(ValidationError):
        ReviewRequest(action="approve", date_confirmed="true")
```

- [ ] **Step 2: Cover inferred-date and version decisions, and run `uv run pytest tests/test_models.py tests/test_review_rules.py -v` expecting missing-interface failures.** Keeping/setting an inferred date requires explicit confirmation of a valid date. Clearing a date is supported when no inference confirmation is required; an inferred-date suggestion cannot use clear as a shortcut around the design's valid-date confirmation rule. An unresolved date may leave its warning while the status is approved. Reject may dismiss a stale suggestion; approval/correction must match the captured version. No decision changes `deadline` or original model evidence. If the proposal itself has already been decided, every action conflicts.
- [ ] **Step 3: Implement pure rules, then run `uv run pytest tests/test_models.py tests/test_review_rules.py -v` to pass.** Keep schema/field validation in Pydantic and role/version/value decisions in plain Python. Corrections are terminal approvals, not new model outputs.
- [ ] **Step 4: Write failing PostgreSQL/API tests.** Both roles can propose, but only Manager can review. Approval increments version once and stores actual before/after values; rejection changes no checklist/version. Concurrent duplicate decisions produce one decision and one conflict. A second suggestion for the same old requirement version cannot overwrite the first approved result. Induce an insertion failure in the isolated test DB after a requirement update and verify transaction rollback leaves both requirement/version and decision count unchanged. Test malformed UUIDs, Proposer forgery, and unknown fields.

```python
def test_only_manager_can_apply_saved_suggestion(client, saved_suggestion):
    path = f"/suggestions/{saved_suggestion['id']}/review"
    assert client.post(path, json={"action": "approve"}).status_code == 403
    decision = client.post(path, json={"action": "approve"}, headers={"X-Demo-Role": "manager"})
    assert decision.status_code == 200
    assert decision.json()["outcome"] == "approved"
    assert decision.json()["previous_status"] == "Scheduled"
    assert decision.json()["applied_status"] == "Completed"
    assert client.post(path, json={"action": "approve"}, headers={"X-Demo-Role": "manager"}).status_code == 409
```
- [ ] **Step 5: Implement row locks and atomic decision writes.** Lock suggestion first, check unique existing decision, then lock its requirement; check captured version and apply pure rules. Write version/status/scheduled date and decision within one transaction; rejection writes only its decision. Return typed Pydantic rows and translate errors at the HTTP boundary. Read history with its unchanged proposal plus stored decision.
- [ ] **Step 6: Run all checks and commit `feat: apply manager decisions atomically with review history`.**

## Task 5: Saved Review UI and Automated End-to-End Coverage

**Files:** Create `app/page.py`, `app/static/onboarding.js`, `tests/e2e/__init__.py`, `tests/e2e/server.py`, `tests/e2e/conftest.py`, `tests/e2e/test_review_workflow.py`. Modify `app/main.py`, `pyproject.toml`, `uv.lock`, README/AGENTS, `.github/workflows/tests.yml`, existing page tests.

**Interfaces:**
- `app.page.PAGE` replaces the page constant in `main.py`; mount `/static` for `onboarding.js`. `GET /` remains the shell.
- Browser reads Task 2's provider endpoints and Task 3's saved-update endpoints, and posts Task 4's review contract/header. Keep provider IDs and request IDs separate from displayed names. Render supporting text/warnings using text nodes, never HTML interpolation.
- Test-only `tests.e2e.server.create_test_app(test_database_url: str, scenario: str) -> FastAPI` builds the real app with an isolated pool and deterministic agent-factory override. Guard the test URL before starting. Its process-wide `override_allow_model_requests(False)` remains active through server shutdown. Do not expose a production test-model switch or fixture-control endpoint.
- pytest browser fixtures start/stop Uvicorn in a child process with only required test environment variables, choose an available loopback port, wait for HTTP readiness, and retain the test DB across a requested app restart. Scenario selection is a test-runner startup argument, not production behavior.
- The `app_server` browser fixture exposes `url: str` and `restart() -> None`, retaining the same URL/database and waiting for readiness. Use accessible labels `Simulated role` and `Original update`, an `Analyze update` button, and a table named `Onboarding checklist`. The default scenario proposes Drug screening Completed from the original Scheduled fixture.

- [ ] **Step 1: Add pinned `pytest-playwright==0.10.0` and `playwright==1.65.1` to dev dependencies, install matching Chromium, and write failing browser tests.** Start in Proposer mode; propose an update; refresh and find pending suggestions; switch to Manager and approve; verify checklist/history after refresh and server restart. Use `get_by_role`/`get_by_label` and Playwright assertions, not arbitrary delays or brittle markup snapshots. Run `bash scripts/test.sh uv run pytest tests/e2e -v`; expect missing review-control/workflow assertions to fail.

```python
def test_manager_approval_survives_restart(page, app_server):
    page.goto(app_server.url)
    page.get_by_label("Original update").fill("Drug screening completed.")
    page.get_by_role("button", name="Analyze update").click()
    expect(page.get_by_text("Drug screening completed.", exact=True).first).to_be_visible()
    page.reload()
    page.get_by_label("Simulated role").select_option("manager")
    page.get_by_role("button", name="Approve", exact=True).click()
    checklist_row = page.get_by_role("table", name="Onboarding checklist").get_by_role("row").filter(has_text="Drug screening")
    expect(checklist_row).to_contain_text("Completed")
    app_server.restart()
    page.reload()
    expect(checklist_row).to_contain_text("Completed")
```
- [ ] **Step 2: Implement the role switch and review/history UI.** Both roles can propose and view history. Manager mode has Approve, Approve with corrections, and Reject per pending suggestion. Include editable status/date, an explicit clear-date choice, and inferred-date confirmation which resets when edited. Save decisions only on the manager's final action. Reload saved provider/updates after success or 409; never optimistically mutate the checklist. Disable duplicate submissions and prevent stale responses from restoring old state.
- [ ] **Step 3: Add focused browser scenarios.** Corrected approval and rejection leave original supporting text/proposed values visible in history. Exercise inferred-date confirmation, explicit date clearing, status-only warnings, two independently reviewable suggestions, and switching roles with pending work. Verify Proposer cannot apply a decision even through an HTTP request; endpoint integration is the authority. Cover empty output, failed model/database requests, unfinished processing, `<script>`-like supporting text, keyboard operation, and narrow/desktop layouts.
- [ ] **Step 4: Run the browser suite to pass and wire it into the default full pytest run and CI.** CI installs PostgreSQL 18, pinned dbmate, and `uv run playwright install --with-deps chromium`. Retain browser traces on failures. Missing browser/test DB setup fails with instructions; do not skip E2E or rely on Neon credentials. Existing pure unit tests remain independently runnable without those services.
- [ ] **Step 5: Update user-facing documentation and copy.** Explain the simulated role and saved state; remove temporary-date-only claims. Document app setup, dbmate migrate, explicit seed, isolated test commands, URL roles, dependency versions, and safe errors. Update the actual module layout in AGENTS.md and replace stale current-behavior claims in README. Keep the proposal's existing historical first-extraction scope paragraphs; add the implemented persistence/review behavior only where needed, with no approval logs.
- [ ] **Step 6: Run Ruff, mypy, and `bash scripts/test.sh uv run pytest`; commit `feat: complete saved review workflow with browser tests`.** All three test layers run; no real local/cloud model requests.

## Completion and Neon Verification

- [ ] Self-review against every section of the design. Check all seven table relationships, retained audit evidence, role simulation, seed/template boundaries, date semantics, no held model-time transactions, and deterministic test isolation.
- [ ] Recheck `DATABASE_URL` and `DATABASE_URL_UNPOOLED` target the same intended application DB without printing either. Run `dbmate --no-dump-schema -e DATABASE_URL_UNPOOLED migrate`, explicit synthetic seed, and a typed/read-only record check on Neon. Verify running forward migration/seed again preserves data. Do not roll back, drop, truncate, or run the automated suite against Neon.
- [ ] Generate the final schema-only dump using compatible PostgreSQL 18 tools, compare it with migrations, and inspect the complete branch diff for credentials or synthetic test-runner exposure.
- [ ] Run final local Ruff, mypy, and the full unit/integration/E2E suite once on the final code; retain output. Inspect the real page against deterministic output and confirm stored state survives app restart.
- [ ] Request a fresh whole-branch review, resolve material findings, and run checks after any fixes. Open the implementation PR against its verified base with Summary/Test plan, apply the code-backed PR-diagram skill, push, and run `gh pr checks --watch`. Never merge it.

## Plan Self-Review

Spec coverage: Task 1 owns migrations/configuration/isolation; Task 2 owns typed provider types/templates/checklists and seed; Task 3 owns captured context, saved extraction, warnings, and errors; Task 4 owns validated manager decisions, evidence, and concurrency; Task 5 owns the saved browser workflow and automated E2E. Completion owns forward Neon verification, final schema, whole-branch review, PR, and CI. The five Review Focus conditions have explicit tests in their owning tasks.

All later-task signatures/types are defined above before use. `ReviewDecision` is defined alongside saved records in Task 3 and populated in Task 4. Existing extraction contracts remain callable while only the public analysis transport changes. The tests establish application correctness with deterministic model output, not real-model extraction quality. Provider exceptions, additional real-world checklist content, and semantic routing remain outside this implementation.
