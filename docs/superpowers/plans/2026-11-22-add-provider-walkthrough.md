# Add Provider Walkthrough Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. The user prefers native inline execution with one final independent review.

**Goal:** Ship the approved five-step Add Provider modal, provider-only additional requirements, and Expected completion date help in the actual application.

**Architecture:** Extend the existing relational checklist and transactional creation operation. Keep the modal's editable draft separate from a frozen submitted/recoverable request; reuse existing dashboard, analysis, review, and audit operations for every saved row. Preserve standard template provenance while allowing explicitly provider-only rows.

**Tech Stack:** Existing Python/FastAPI/Pydantic, raw PostgreSQL/psycopg, dbmate, native JavaScript/HTML/CSS, pytest, and Playwright; no new dependencies or framework.

**Spec:** `docs/superpowers/specs/2026-11-22-add-provider-walkthrough-design.md`

## Global Constraints

- Keep `docs/proposal.md` unchanged; synchronize `docs/database-design.md` and AGENTS.md with implemented behavior.
- Use synthetic records only, simulated Manager enforcement on the server, TestModel, and disabled real model requests.
- Automated tests use disposable local/CI PostgreSQL, never the configured Neon application database.
- Use a forward-only migration with an empty down section and `DBMATE_NO_DUMP_SCHEMA=true`. Do not apply it to Neon during implementation.
- Standard rows start Outstanding with unset dates. Additional rows use reviewed initial values. Every new row starts at version 0.
- Only final Add provider writes; Save requirement and step navigation update a browser draft.
- Use Expected completion date throughout visible UI, retaining the SQL/API name `scheduled_date` and existing inference/approval rules.
- Never commit to main or merge a PR. Open the implementation PR after required checks and one whole-branch review.

## Review Focus

1. A provider-only name already exists in another checklist: reuse the canonical definition without changing the other provider; Task 2 tests shared-name creation across types.
2. A shared catalog changes after preview, including membership under the same unassigned header: reject final save and require a new review; Tasks 2 and 4 test both forms of change.
3. Creation succeeds but its response/reload is lost, followed by a page reload or role change: recover one frozen request without duplicate creation or automatic writes; Task 4 tests this sequence.
4. Changing provider type turns an existing addition into a standard duplicate or invalidates its selected status: preserve the draft and block save until resolved; Task 4 tests both cases.
5. Date help or a long/custom name is used in a narrow modal: preserve focus, readable help, safe text rendering, and contained scrolling; Tasks 4 and 5 test these conditions.

## File and responsibility map

- `db/migrations/20261122000100_add_provider_requirements.sql`: nullable row provenance, direct FKs, initial receipt columns/CHECK, immutable receipt trigger. `db/schema.sql`: explicit schema-only snapshot generated from isolated PostgreSQL.
- `app/provider_models.py`: creation/addition inputs and configured catalog metadata. `app/rules/catalog.py`: pure normalized names and deterministic membership digest.
- `app/rules/providers.py`: creation authorization, template comparison, additional validation, immutable retry equality.
- `app/repository/providers.py`: provider reads and creation transaction orchestration. `app/repository/provider_creation.py`: creation lookup/receipt reconstruction and row insertion. `app/repository/catalog.py`: shared definition resolution in deterministic order.
- `app/models.py` and `app/repository/snapshots.py`: nullable immutable requirement template provenance in saved/captured records.
- `app/rules/statuses.py`, `app/rules/checklist.py`, `app/rules/monitoring.py`, `app/monitoring.py`: shared provenance-aware vocabulary and monitoring.
- `app/static/providers.js`: creation network/role/busy/reload orchestration, preserving its existing integration contract and duplicate-name labels.
- `app/static/provider-wizard.js`: safe DOM rendering, five steps, addition editor, draft validation and review.
- `app/static/provider-recovery.js`: sessionStorage validation and persistence of frozen submitted attempts; no HTTP requests.
- `app/static/date-help.js` and `app/static/provider-wizard.css`: accessible shared date explanation and scoped modal styles.
- `app/page.py`, `app/static/onboarding.js`, `app/static/checklist.js`, `app/static/review.js`: dialog shell/integration and visible date wording/help.
- Existing unit/integration/browser tests plus `tests/test_provider_additions.py`, `tests/test_provider_addition_constraints.py`, and `tests/e2e/test_provider_wizard.py`: meaningful feature, upgrade, concurrency, and recovery coverage.

---

### Task 1: Provider-only schema and provenance-aware status rules

**Files:** Create the migration, `tests/test_provider_addition_constraints.py`; modify `app/models.py`, `app/rules/statuses.py`, `app/rules/checklist.py`, `app/rules/monitoring.py`, `app/monitoring.py`, `app/repository/snapshots.py`, `tests/test_normalized_constraints.py`, and focused status/dashboard tests.

**Interfaces:**
- `StoredRequirement.checklist_template_id: RecordId | None` is required but nullable. Null exclusively identifies a provider-only row.
- Extend `known_statuses`, `status_choices`, `classify_completion`, and `status_tone` with keyword-only `is_additional: bool = False`. Existing callers default to the original standard-row behavior.
- `GENERIC_ADDITIONAL_STATUSES = ("Outstanding", "Pending", "Scheduled", "Incomplete", "Completed")`. Configured provider/name vocabularies take precedence; generic completion applies only to additions.

- [ ] Write failing integration tests for null-template additions referencing missing providers/definitions, duplicate provider/name pairs, invalid initial receipt combinations, immutable initial values/origin, and provider deletion preserving shared definitions. Assert original composite FK protection on standard rows still works.
- [ ] Write failing pure tests: generic Completed is finished only for additions; generic Scheduled remains unfinished; unfamiliar standard rows/types and unfamiliar saved values remain Needs review. Include a configured-name addition using its existing vocabulary.
- [ ] Run `uv run pytest tests/test_provider_addition_constraints.py tests/test_monitoring_rules.py tests/test_checklist_rules.py`; observe failure from missing schema/provenance behavior.
- [ ] Implement the migration exactly as specified: nullable template ID, direct provider CASCADE/definition RESTRICT FKs, optional initial fields, CHECK tying their presence to origin, and immutable initial values in `preserve_requirement_owner`. Preserve both composite FKs and existing indexes/unique constraints. Read every SQL line against the user's eleven-point schema checklist before using a disposable migration test.
- [ ] Propagate nullable provenance through stored/captured records and pass `is_additional=r.checklist_template_id is None` through dashboard/manual-save rules. Preserve verbatim unknown statuses and captured evidence.
- [ ] Run focused tests, Ruff, mypy, and the full suite. Update FK-count assertions only to reflect the two additional explicit relationships, preserving ownership checks.
- [ ] Commit `feat: support provider-only checklist rows and status rules` after checks pass.

### Task 2: Reviewed-template creation, additional inputs, and retry receipts

**Files:** Create `app/rules/catalog.py`, `app/repository/provider_creation.py`, `tests/test_provider_additions.py`; modify `app/provider_models.py`, `app/rules/providers.py`, `app/repository/providers.py`, `app/repository/catalog.py`, `db/seed.py`, creation fixtures/tests, and `app/main.py` error wiring only if a focused validation exception is needed.

**Interfaces:**
- `AdditionalRequirementInput(BaseModel)`: extra forbid; `name: NonBlank`, `status: NonBlank`, `scheduled_date: date | None = None`, `deadline: date | None = None`.
- `CreateProviderRequest`: retain creation UUID/profile fields; require `checklist_template_id: RecordId`, `template_fingerprint: str` validated as a SHA-256 hex digest; `additional_requirements: list[AdditionalRequirementInput] = []` via default factory.
- Catalog `ProviderTypeTemplate` retains existing fields and returns `template_fingerprint`, `additional_statuses`, and `configured_statuses` (normalized requirement name to allowed statuses). Compute this server-side rather than storing metadata columns.
- `normalize_name(value: str) -> str` mirrors `lower(btrim(name))` for surrounding spaces; `template_fingerprint(type_id: int, template_id: int, version: int, names: Sequence[str]) -> str` hashes deterministic JSON encoding of identity and sorted normalized membership using SHA-256.
- Preserve `ProviderRepository.create_from_template(request, *, initial_status)` and `initialize_provider(request, initial_values)` so orchestration/seed remain focused. Both use the expanded reviewed contract; seeds explicitly supply their catalog metadata.
- `require_additions(template: ProviderTypeTemplate, additions: Sequence[AdditionalRequirementInput]) -> None` validates unique applicable names and authoritative initial statuses; no DB calls.
- Move `existing_creation(conn, request) -> StoredProvider | None`, `insert_provider(conn, request, template) -> int`, and `initialize_checklist(conn, provider_id, template, values) -> None` to the focused creation repository. Add `initialize_additions(conn, provider_id: int, template: ProviderTypeTemplate, additions: Sequence[AdditionalRequirementInput]) -> None`. Their `conn` is the caller's `AsyncConnection[dict[str, Any]]`; none starts a separate transaction.
- `resolve_definitions(conn, names: Sequence[str]) -> dict[str, int]` in the catalog repository resolves/creates canonical definitions in normalized-name order and returns normalized name to definition ID; both catalog membership and creation helpers use it.

- [ ] Write failing unit tests for blank/extra/invalid date inputs, duplicate normalized names, generic/configured allowed statuses, digest stability/change, and order-insensitive retry comparison including changed initial date/deadline/status conflicts.
- [ ] Write failing PostgreSQL/HTTP tests for two reviewed additions plus unchanged standard defaults, shared canonical definition reuse across providers/types, atomic rollback, Manager enforcement, and no fabricated update/review/edit records.
- [ ] Add tests for stale template IDs and changed same-header membership, with no provider/definition residue. Preserve and extend existing catalog lock race tests rather than deleting them.
- [ ] Add concurrent equal-UUID/different-UUID tests, reordered retry tests, and retry-after-progress/archive/new-template tests proving current values are never reset. Assert snapshots and independently approved/manual edits work for additional rows and remain provider-scoped.
- [ ] Run `uv run pytest tests/test_provider_rules.py tests/test_provider_additions.py tests/test_catalog_races.py`; observe the expected missing-contract/behavior failures.
- [ ] Implement the pure contracts/metadata and transaction helpers. Under the retry lock, reconstruct existing creation input from the immutable profile, assigned immutable membership, and additional initial fields before consulting today's catalog or status rules.
- [ ] For a new attempt, lock type/header, compare reviewed ID and digest, validate additions, resolve definitions in normalized-name order shared with catalog configuration, insert provider and standard/additional rows atomically, and return the saved provider. Additions never enter `template_requirements`.
- [ ] Update existing request-building test helpers and the seed to supply actual catalog identity/digest. Preserve all existing behavioral coverage except expectations explicitly superseded by the approved wizard contract.
- [ ] Run focused tests, Ruff, mypy, and the complete suite. Commit `feat: create providers with reviewed additional requirements`.

### Task 3: Reusable date help and visible wording

**Files:** Create `app/static/date-help.js`; modify `app/page.py`, `app/static/onboarding.js`, `app/static/checklist.js`, `app/static/review.js`, and affected browser tests.

**Interfaces:**
- `addDateHelp(parent: HTMLElement): HTMLButtonElement` appends an independently labeled help button; `setupDateHelp(): void` installs the shared hover/focus/click/Escape/outside-click behavior once.
- `EXPECTED_DATE_HELP` uses the spec's exact explanation. Add static helper hooks to table headings and dynamic controls without placing a button inside an input's label.

- [ ] Add failing browser assertions for Expected completion date in checklist/manual editor/suggestion comparison/history and for hover, focus, tap toggle, Escape-only-help dismissal, and narrow viewport help bounds.
- [ ] Run `uv run pytest tests/e2e/test_checklist_edits.py tests/e2e/test_checklist_review.py` with the new assertions; observe missing wording/help failures.
- [ ] Implement help using safe DOM text and a popover in the active dialog's accessibility scope or document body. Keep it hoverable, keyboard readable, and dismissible. Replace visible wording consistently while preserving SQL/API `scheduled_date`, inference, history values, and unrelated rules.
- [ ] Run the focused browser tests, JavaScript module syntax checks, Ruff, mypy, and full pytest. Commit `feat: clarify expected completion dates with accessible help`.

### Task 4: Five-step modal, staged additions, and creation recovery

**Files:** Create `app/static/provider-wizard.js`, `app/static/provider-recovery.js`, `app/static/provider-wizard.css`, `tests/e2e/test_provider_wizard.py`; modify `app/page.py`, `app/static/providers.js`, `app/static/onboarding.js`, and `tests/e2e/test_provider_creation.py` helpers/assertions.

**Interfaces:**
- Preserve `setupProviderCreation({api, roleSelect, setBusy, onCreated})` and its controller methods `setBusy(value)`, `syncRole()`, `onProviderLoaded(id)` plus existing `providerLabel` export.
- `createProviderWizard({dialog, onSubmit, onCancel})` owns unsent draft/UI state and returns `open(types)`, `close()`, `setBusy(value)`, `showError(message)`, `showRecovery(attempt, message)`, and `replaceCatalog(types)` (preserving/revalidating drafts and returning to Requirements).
- `readCreationAttempt()`, `writeCreationAttempt(attempt)`, `clearCreationAttempt()` in the recovery module validate/session-store `{payload: CreateProviderRequest, savedId: integer | null}` without HTTP or automatic submission.
- Recovery storage key `onboard-hq:provider-creation:v1`. Treat malformed stored data as unavailable and block automatic replay. If persistence fails, do not start a save whose recovery record cannot be retained; show an actionable message.

- [ ] Update creation test helpers to navigate name, type dropdown, optional start, Requirements, Review. Keep original provider isolation, safe-name rendering, first-provider creation, archived-view selection, restart, and failure-reload tests.
- [ ] Add failing wizard tests asserting zero POSTs through step navigation and Save requirement; saved additions enter the combined list only after Save; Edit/Cancel preserves prior draft values; Remove affects only the draft; new editors start blank/Outstanding; pending edits block Review.
- [ ] Add tests for duplicate standard/additional names, invalid dates, optional dates, type-change duplicate/status revalidation, review Edit return paths, empty/missing catalogs, long/HTML-like names, keyboard focus trapping/Escape restoration, mobile scrolling, and Scheduled badge dimensions matching other badges.
- [ ] Add failure tests: double-click final save; lost response plus reload plus explicit Manager retry; Proposer mode cannot replay; confirmed save with list/dashboard/history reload failure; catalog conflict retains draft and requires another Review. Assert one provider, the same UUID/payload, and unchanged later progress.
- [ ] Run `uv run pytest tests/e2e/test_provider_wizard.py`; observe failures from the missing dialog/flow.
- [ ] Implement the native dialog shell with green + Add provider opener and a final Add provider button without plus. Scope step-indicator selectors independently of status badge classes to avoid the preview's Scheduled spacing collision.
- [ ] Implement safe DOM draft rendering and single-addition editing with server-supplied vocabulary. Back retains drafts; type changes retain and revalidate additions; closing an unsent draft discards it. Never concatenate submitted names into HTML.
- [ ] Implement frozen final submission and explicit recovery using the existing API/busy/coherent-selection callbacks. Distinguish definitive no-commit validation/catalog errors from unconfirmed transport/server outcomes. A stale catalog reloads while keeping user-entered details. Recovered/uncertain attempts retain their identity through close/reopen/reload and role changes.
- [ ] Close and clear recovery only after the correct saved provider loads coherently. Preserve active/archived transitions, update-text clearing, and empty history. Bump static import/cache versions together so old inline-form code cannot run against new markup.
- [ ] Run the targeted creation/wizard/browser tests, all JS module syntax checks, Ruff, mypy, and full pytest. Commit `feat: ship the Add Provider walkthrough modal`.

### Task 5: Integration, documentation, final review, and implementation PR

**Files:** Modify `AGENTS.md`, `docs/database-design.md`, `db/schema.sql`, affected operational documentation, and any tests needed for integration regressions. Keep the original proposal unchanged.

**Interfaces:** No new product interfaces. The migration and app ship in the same PR; live database application remains a separately authorized rollout step.

- [ ] Add/run an isolated upgrade test from migration four with existing provider progress, original updates, suggestions, decisions, and manual history. Assert exact data preservation and a repeatable seed after migration five.
- [ ] Run a full real-browser flow against isolated PostgreSQL: create a synthetic provider with Scheduled and Completed additions, edit one afterward, analyze/review another with TestModel, refresh/restart, and verify counts/history plus the original provider's untouched records.
- [ ] Generate the schema-only snapshot explicitly from a disposable migrated database, with no credentials or sample rows. Keep `DBMATE_NO_DUMP_SCHEMA=true` for automatic dbmate operations. Verify five applied migrations and Pending: 0 only against that disposable database.
- [ ] Synchronize implemented database documentation and AGENTS.md responsibility/scope guidance. Explain the rollout ordering so a merge alone is not presented as an applied Neon migration.
- [ ] Run `uv run ruff check`, `uv run mypy`, JavaScript syntax checks, `git diff --check`, and `bash scripts/test.sh uv run pytest`; all must pass, with zero skips or real model requests.
- [ ] Use requesting-code-review for one fresh whole-branch reviewer against main, the spec, this plan, and execution ledger. Fix Important/Critical findings with a failing regression test followed by green verification; record minor deferrals and rulings.
- [ ] Commit the verified final changes, push this implementation branch, and open a non-draft PR with Summary citing the proposal/design and a checked Test plan. Use pr-diagram for one code-verified Mermaid flow, then `gh pr checks --watch` and report the result. Leave merging to the user.
- [ ] Report the implementation PR and exact local launch/branch instructions. Clearly identify the unapplied Neon migration as the remaining rollout step; do not claim the running Neon-backed app is updated before that authorized migration and matching server restart.
