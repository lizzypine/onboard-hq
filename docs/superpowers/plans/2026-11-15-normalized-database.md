# Normalized Database Cutover Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task using the established native execution method. Steps use checkbox (`- [ ]`) syntax. Review this plan with the user before implementation.

**Goal:** Convert the eight-table UUID/JSON implementation to the twelve-table PostgreSQL design while preserving supported saved data and keeping the existing provider, analysis, review, monitoring, and manual-edit flows working.

**Architecture:** One coordinated, maintenance-window schema/application cutover. A transactional forward migration maps existing records to integer identities, derives immutable whole-checklist versions, and normalizes captured state. Matching Python and browser changes ship in the same release. No mixed old/new application workers and no automatic Neon migration at startup.

**Tech Stack:** Existing PostgreSQL 18, dbmate 2.38.1, raw SQL, Psycopg, FastAPI, Pydantic/Pydantic AI, vanilla JavaScript, pytest, and Playwright. No new runtime dependencies or ORM.

**Spec:** `docs/database-design.md`; preserve `docs/proposal.md` unchanged. Legacy application baseline: commit `3f498780ab4703ec04363a6c0eafaac2db4c8430`.

## Global Constraints

- The target contains exactly the twelve application tables in the design. Every non-junction table uses `id integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY`; the two junctions use their stated composite primary keys.
- Follow the design's required/nullable columns, normalized unique names, fixed-value checks, explicit foreign-key deletion actions, indexes, row-purpose comments, and immutable references. Store no parent-name copies or relationship/warning lists in columns.
- Preserve provider profiles, actual checklist membership, verbatim statuses, dates, deadlines, change counters, original messages, supporting evidence, warnings, processing states, decisions, audit values, and event times. Do not reset, reseed, union differing checklists, or silently discard legacy information.
- Preserve old provider UUIDs as `creation_request_id`, old manual-edit UUIDs as `operation_id`, and existing update `request_id` values. Integer resource IDs are new identities, not replacements for request retry keys.
- HTTP response lists, derived parent labels, and reconstructed snapshot objects are allowed; the storage prohibition concerns persistent columns. Keep the existing readable API information and LLM context.
- Use synthetic data only, `TestModel`, and `override_allow_model_requests(False)` at every test layer. Automated tests use guarded disposable loopback `onboard_hq_test_*` databases, never Neon or `.env` credentials.
- Keep `DBMATE_NO_DUMP_SCHEMA=true`, disable credentialed automatic dumps, and generate `db/schema.sql` only from passwordless disposable local PostgreSQL.
- Keep the current model gateway, incomplete-date policy, Hawaii monitoring clock, requirement-specific status vocabulary, independent review decisions, and simulated roles. No authentication/password tables or real employee data.
- Do not edit existing applied migrations. Do not apply the new migration to Neon during implementation. Keep the branch unmerged and undeployed until the complete application and migration pass review.
- Run Ruff, mypy, and the full pytest suite for each completed task; do not skip tests, weaken validation, or raise complexity limits. Tests may change fixtures/contracts to match the approved redesign, but retain their behavior assertions.

## Scope and proposed implementation decisions

This plan implements the schema and adaptation of existing workflows. The new `archived_at` field is returned and respected as read-only state, including server write guards and a readable archived-provider view. Archive/Restore/Delete action endpoints and buttons are a separate follow-up feature, as is managed sign-in. Database cascades and their audit exception are still tested here.

These engineering decisions require review with this plan:

1. **Atomic cutover with a maintenance window.** Stop/drain old workers before schema conversion. Reload browsers onto the new assets. This avoids extra permanent compatibility tables/columns and old UUID code writing to the integer schema.
2. **Forward conversion with backup-based rollback.** The target does not retain every old UUID. A truthful SQL `down` cannot reconstruct them after new writes. The new `down` refuses to run without changing target data; recovery uses a verified pre-cutover backup and the old application. Do not promise a reversible ID conversion or retain unapproved permanent mapping tables.
3. **Safe handling of unsupported legacy data.** Preflight aborts atomically with actionable, credential-free diagnostics when the target cannot represent a record faithfully. No automatic data cleanup or guesses. The operator resolves such cases before retrying.
4. **Browser upgrade recovery.** Recover already-committed legacy saves through preserved UUID retry identities. Keep unresolvable drafts visible until explicit dismissal; do not guess new requirement IDs or automatically replay ambiguous old drafts.
5. **In-flight analysis.** Archive guards reject new claims and new progress mutations. An analysis claimed while active may finish saving its evidence after archiving, without applying progress. If the provider/update was deleted, completion/failure returns missing-record behavior and never recreates it.

Before a later Delete interface is implemented, separately settle delayed creation retries after permanent erasure: deleting a provider also erases its creation retry key. Do not add a receipt/tombstone table or promise deduplication after full erasure without that decision. No such interface or extra persistent table is introduced by this plan.

## Review Focus

1. Legacy type/name collisions, nullable template provenance, empty actual checklists, and checklists that differ from today's catalog must not cause silent merging, resets, or lost context.
2. Failed conversion, an attempted SQL downgrade, or a cutover failure must preserve data; backup restore is verified before traffic or new writes are enabled.
3. Archiving/deleting while analysis or a checklist save is running must not apply archived progress, resurrect deleted records, or deadlock on inconsistent lock order.
4. A browser carrying a frozen UUID-era save must not silently lose the draft, replay it onto a different integer ID, or duplicate an already-committed change.
5. A newer checklist version or an archived provider must not change the result of a committed creation/edit retry; duplicate display names and integer DOM values must still select the correct provider.

---

## File and responsibility map

| Files | Responsibility |
| --- | --- |
| `db/migrations/20261115000100_normalize_checklists.sql` | Preflight, transactional conversion, twelve-table constraints/indexes/immutability, guarded downgrade |
| `db/queries.py` | Keep one typed `fetch_provider` query, joining immutable definitions/version metadata |
| `db/seed.py`, `app/seed.py` | Explicit idempotent synthetic seed and compatible CLI entry point |
| `app/models.py`, `app/provider_models.py`, `app/checklist_models.py`, `app/monitoring_models.py` | Integer resource contracts, UUID retry keys, derived labels, captured-context contracts |
| `app/repository/catalog.py` | Programmatic catalog/version configuration for seeding and tests, without a new administration UI |
| `app/repository/snapshots.py` | Save/load normalized captured requirement state |
| `app/repository/providers.py`, `updates.py`, `reviews.py`, `checklist.py` | Adapt existing persistence operations, retry identities, ownership/version locks, and joined histories |
| `app/rules/provider_state.py` | Pure archived-state write rejection shared by existing operations |
| `app/main.py`, `app/providers.py`, `app/checklist.py`, `app/reviews.py`, `app/monitoring.py` | Integer path IDs, existing operation orchestration, archived guards, HTTP error mapping |
| `app/rules/providers.py`, `app/rules/checklist.py` | Separate UUID retry-key comparisons from integer resource comparisons |
| `app/static/providers.js`, `onboarding.js`, `checklist.js`, `review.js`, `app/page.py` | Integer-ID UI boundaries, current retry payloads, archived read-only display, existing review interactions |
| `app/static/checklist-recovery.js` | Focused recovery of legacy stored attempts; no model calls or new save identities |
| `tests/fixtures/legacy_database.py` | Hand-checked UUID-era data and isolated migration-prefix helpers |
| `tests/test_database_upgrade.py`, `test_catalog.py`, `test_provider_state.py` | Conversion, schema integrity, catalog isolation, and archived-state regression tests |
| Existing unit/integration/browser tests and fixtures | Preserve current acceptance coverage under the new contracts |
| `tests/e2e/test_database_upgrade.py`, `tests/e2e/conftest.py` | Real-browser old-to-new cutover and isolated restore rehearsal |
| `docs/database-cutover.md`, `README.md`, `AGENTS.md`, `.github/workflows/tests.yml` | Operational gates, layout/setup guidance, and CI rehearsal coverage |

## Task 1: Atomic schema and existing-application conversion

This task is intentionally one coordinated unit: a migrated database cannot be independently shipped with the current UUID repositories, fixtures, or browser ID handling. Intermediate RED states remain on the feature branch; commit the task only once the full application suite is green.

**Files:**
- Create: the new migration, `app/repository/catalog.py`, `app/repository/snapshots.py`, `app/rules/provider_state.py`, `tests/fixtures/__init__.py`, `tests/fixtures/legacy_database.py`, `tests/test_database_upgrade.py`, `tests/test_catalog.py`, `tests/test_provider_state.py`.
- Modify: all Python and current-browser files named in the map above except the separate recovery module; `tests/conftest.py`, `tests/database.py`, `tests/e2e/conftest.py`; existing model/rule/provider/repository/update/review/checklist/monitoring/query/migration/deletion/browser tests; `db/schema.sql`, `README.md`, `AGENTS.md`.
- Preserve: `.env`, `docs/proposal.md`, all three applied migrations, the real-model request block, and unrelated extraction/date rules.

**Interfaces:**
- `RecordId = Annotated[int, Field(strict=True, gt=0)]` in shared models for JSON record IDs. HTTP path parameters use positive integer parsing appropriate to string paths; a strict JSON-only integer type must not reject valid `/providers/1` paths.
- `CreateProviderRequest`: `creation_request_id: UUID`, `name: NonBlank`, `provider_type_id: RecordId`, `proposed_start_date: date | None`. No client-supplied integer primary key.
- `ChecklistEditRequest`: `operation_id: UUID` replaces request `id`; retain exact current expected-version, status, requirement-date, and deadline validation.
- `ProviderSummary`: integer `id`, UUID `creation_request_id`, derived `provider_type`, `checklist_template_id`, `template_version`, optional `proposed_start_date`/`archived_at`, and name. `StoredProvider` adds actual requirements.
- `StoredRequirement`: integer record/provider/template/definition IDs, derived name, status, dates, and change counter. Remove `source_template_id` from the target DTO.
- `CapturedProvider`: fixed provider/profile/version fields plus captured requirement states; exclude current `archived_at`. `SavedUpdate.provider_snapshot` becomes this reconstructed DTO, not a JSON storage column. `to_provider_context` accepts `StoredProvider | CapturedProvider` and still returns the existing extraction contract with string context ID.
- All other resource IDs in saved suggestions, decisions, edits, dashboards, and routes become positive integers. UUIDs remain only retry identities. `ChecklistEdit` adds `operation_id` and keeps `requirement_name` as a derived response field.
- `ProviderTypeTemplate`: integer type `id`, name, current `checklist_template_id`, `template_version`, and readable `requirements: list[str]` for preview.
- `fetch_provider(conn: AsyncConnection[dict[str, Any]], provider_id: int) -> StoredProvider` remains the single query function in `db/queries.py`.
- `CatalogRepository.ensure_version(provider_type_name: str, requirement_names: Sequence[str], *, template_version: int) -> ProviderTypeTemplate`: normalize/reuse catalog names; return an identical existing version; reject conflicting contents; no overwrite or new HTTP route.
- `ProviderRepository.list_providers(state: Literal['active', 'archived', 'all'] = 'active') -> list[ProviderSummary]`; keep `get_provider`, `list_provider_types`, and `create_from_template` returning current typed DTOs with integer keys.
- `ProviderRepository.initialize_provider(request: CreateProviderRequest, initial_values: dict[str, Requirement]) -> StoredProvider` is seed-only initialization with exact template-name matching and existing-key recovery before catalog checks.
- `save_snapshot(conn, update_id: int, provider: StoredProvider) -> None` and `load_snapshot(conn, update_id: int) -> CapturedProvider` in `app/repository/snapshots.py`; caller owns their transaction.
- Existing `UpdateRepository.claim/complete/fail/get/list_for_provider`, review, and manual-edit signatures use integer entity IDs and the new DTOs; their return behaviors and atomicity stay intact.
- `require_active(provider: ProviderSummary) -> None` raises `ProviderArchivedConflict`; map it to HTTP 409. Existing request-key/event retries that return committed evidence remain read-only recoveries, even when archived.
- `seed_synthetic(pool: DatabasePool) -> StoredProvider`; expose `KEKOA_CREATION_REQUEST_ID` using the existing KEKOA UUID as retry key, not a numeric PK constant. Resolve generated type/provider IDs from queries/returned rows. Preserve both seed CLIs.
- `migrate_legacy(url: str) -> None` and `seed_legacy_graph(url: str, scenario: str = 'representative') -> LegacyGraph` in test utilities. `LegacyGraph` exposes `provider_key: UUID`, `request_key: UUID`, and `operation_key: UUID`, plus the hand-checked expected history values. Validate disposable URLs; use only the three original migrations and hand-checked historical payloads, never current target models to manufacture expected legacy data.

- [ ] **Write migration and contract tests first.** Add these cases before the new SQL or application implementation:
  - `test_populated_uuid_upgrade_preserves_history`: fixture current Drug screening state is Completed, date 2026-10-29, deadline 2026-11-02, version 7; captured state remains Scheduled, date 2026-10-22, deadline 2026-11-01, version 3. Verify all values, original text, warning rows, pending/final suggestions, audit values, and timestamps after conversion.
  - Verify old provider UUID becomes its creation key, old edit UUID its operation key, and update request UUID stays unchanged. Read the new provider by its retained key; assert a positive integer ID and correct linked records, without assuming IDs are contiguous or always 1.
  - `test_legacy_membership_versions_preserve_empty_and_old_checklists`: one type has an empty saved checklist, a three-item historical checklist, and the current five-item catalog. They remain distinct; catalog membership is the greatest version; no saved provider receives extra items.
  - `test_normalized_collision_or_unrepresentable_snapshot_aborts_atomically`: same-provider case-only duplicate requirements with conflicting states, conflicting type-alias catalogs, malformed/blank-warning snapshots, missing captured requirement parents, or changed fixed snapshot profiles fail without changing old rows or applied versions.
  - `test_target_identity_membership_and_immutability_constraints`: auto-generated integer keys; explicit ID insertion rejected; two junction pairs cannot duplicate; positive versions/counters; all fourteen declared FKs match the design; normalized names cannot duplicate; wrong-provider/version references fail; all required indexes/comments exist.
  - `test_new_migration_down_refuses_without_target_data_loss`: rollback fails with the backup-restore instruction and leaves target rows and migration state intact.
  - Add request-contract tests: JSON record IDs reject booleans, floats, zero, negatives, and UUID strings; valid integer IDs and UUID retry keys succeed. HTTP integer path strings work; an unused positive integer ID returns 404.

  Example outcome assertions inside the upgrade test, after migration, using an async dictionary-row connection and the returned `graph`:

  ```python
  provider = await (await conn.execute(
      'SELECT id FROM providers WHERE creation_request_id = %s',
      (graph.provider_key,),
  )).fetchone()
  assert provider is not None
  assert type(provider['id']) is int and provider['id'] > 0
  drug = await (await conn.execute(
      '''SELECT r.status, r.scheduled_date, r.deadline, r.version
         FROM requirements r JOIN requirement_definitions d
           ON d.id = r.requirement_definition_id
         WHERE r.provider_id = %s AND d.name = 'Drug screening' ''',
      (provider['id'],),
  )).fetchone()
  captured = await (await conn.execute(
      '''SELECT s.status, s.scheduled_date, s.deadline, s.requirement_version
         FROM update_requirement_snapshots s
         JOIN updates u ON u.id = s.update_id
         JOIN requirements r ON r.id = s.requirement_id
         JOIN requirement_definitions d ON d.id = r.requirement_definition_id
         WHERE u.request_id = %s AND d.name = 'Drug screening' ''',
      (graph.request_key,),
  )).fetchone()
  assert drug is not None and captured is not None
  assert tuple(drug.values()) == (
      'Completed', date(2026, 10, 29), date(2026, 11, 2), 7,
  )
  assert tuple(captured.values()) == (
      'Scheduled', date(2026, 10, 22), date(2026, 11, 1), 3,
  )
  ```

- [ ] **Run the new tests and inspect RED.** Run `uv run pytest tests/test_database_upgrade.py tests/test_models.py -v`. Expected: missing target tables/integer contracts, not a fixture or connection error. No migration is applied to Neon.

- [ ] **Implement the transactional forward migration.** Review every line against the design checklist before executing it, including in tests. Follow this conversion contract:
  1. Lock the legacy application tables for the cutover transaction, then validate supported source shapes and conflicts before losing any source information. Reject unexpected dependent objects rather than dropping them incidentally.
  2. Stage the eight legacy tables and their indexes in an isolated migration-only schema so final public names and identity/constraint names are available. Fail if that staging namespace already exists. Do not UPDATE/DELETE legacy audit rows or disable their protection.
  3. Create the twelve public tables with the design's exact column types, requiredness, checks, FKs, unique keys, indexes, and row-purpose comments. Keep identifier maps transaction-local; no mapping columns/tables remain in the final schema.
  4. Normalize type/definition identity keys with the same trim/lower rule as the unique indexes. Choose canonical display labels deterministically from existing catalog rows, then actual requirements when absent from the catalog. Preserve status/evidence strings verbatim. Merge type aliases only when their current catalog membership agrees; conflicting aliases stop conversion.
  5. For each normalized type, derive distinct actual checklist membership sets plus the current catalog set. Assign positive version numbers deterministically, reserving the greatest number for the current catalog set. Reuse a set if it equals the catalog. Preserve empty historical sets; an empty latest catalog makes that type unavailable for new creation rather than inventing requirements.
  6. Copy providers and progress to generated integer IDs, preserving the retained UUID retry keys and every saved value. Initially set `archived_at` to NULL. Resolve nullable old template provenance from the actual saved checklist; do not discard a row because its old source ID is NULL.
  7. Convert every valid full JSON context into snapshot rows and ambiguity rows. Verify captured provider IDs, fixed profile values, requirement ownership, normalized names, dates, and counters. Never reconstruct old states from today's statuses or silently discard unsupported JSON members.
  8. Remap suggestion/decision/edit links; preserve event times, inferred-date flags, rejection/correction values, empty/cleared dates, and terminal-decision uniqueness. Check counts and per-record values before removing legacy storage.
  9. Install historical-reference guards: immutable used type/definition labels; immutable template identity/membership once assigned; fixed provider profile/retry key; fixed requirement ownership/membership; audit UPDATE/DELETE protection with root provider-deletion exception. Serialize membership mutation and provider assignment on the template header, so concurrent changes cannot redefine an assigned version. Catalog labels may be treated as immutable from insertion because renaming is outside scope.
  10. Remove temporary maps and drop legacy tables in explicit child-to-parent order using restrictive drops, then remove the empty staging namespace. Do not use a broad schema CASCADE that could remove unrecognized objects. Commit with exactly twelve application tables and no old JSON/name-copy columns.
  11. New `down` raises an actionable error requiring restoration of the verified pre-cutover backup. It does not drop target data or fabricate old UUIDs. The first three migration files remain byte-for-byte unchanged.

- [ ] **Implement the contracts, queries, seeding, and existing browser conversion together.** Use the interface block above. Reconstruct readable names, snapshot DTOs, warnings, and history with joins; query-time aggregation for HTTP responses is allowed, stored JSON arrays are not.
  - Provider creation chooses/locks the latest configured template only on first creation. A matching creation-key retry returns the original provider/version before consulting a newer catalog; conflicting profile/type input remains 409.
  - Manual saves query by `operation_id`, generate their integer audit ID in PostgreSQL, derive history names by joins, and preserve stale/no-op/verbatim-status checks. Analysis request identity remains its UUID `request_id`.
  - Use retry-identity advisory locks before row locks. Then use provider → update/suggestion → requirement order. Completion/failure first resolve ownership without retaining a child lock, then acquire locks in that order. Never hold a transaction over model I/O.
  - Block new archived claims, reviews (including rejection), and manual mutations. Read/recovery of committed evidence is allowed. An already-claimed analysis can finish evidence after archive; after provider deletion it returns missing-record behavior without new rows. Add deterministic thread/barrier tests for both races and for archive versus an in-progress manual save.
  - Return integer resource IDs in JSON, including saved-update IDs in error details. Keep UUID request keys distinct. Preserve extraction-only slug/string context IDs and pure date/completion behavior.
  - Convert DOM option values to/from integer state deliberately. Replace UUID string slicing and `localeCompare` assumptions with full integer references and deterministic timestamp/kind/numeric-ID history ordering. Keep duplicate names distinct. Add an Active/Archived viewing filter and archived read-only rendering; no lifecycle action buttons/endpoints are added.
  - New browser save attempts use `operation_id` and a versioned session-storage format. Preserve the existing legacy storage key for Task 2; do not delete or automatically replay it during parsing. Cache-bust changed page/module assets for the cutover.
  - The seed first recovers the existing sample by its creation key and returns it unchanged, including archive/progress/version. On an empty catalog configure Dentist v1 with the existing five names/statuses and start date 2026-12-01. If the sample is absent but an existing catalog conflicts with that fixture, fail without modifying it. Never rename a used definition, overwrite a version, create extra production types, or backfill an existing checklist.

- [ ] **Port existing fixtures and keep their assertions.** Use returned integer IDs, not hardcoded sequence values. Keep UUIDs where they are request keys. Replace template-renaming tests with new-version/new-definition scenarios; replace UUID-generation collision monkeypatches with a real controlled insert failure to keep rollback coverage.
  - Update `tests/test_models.py`, `test_provider_rules.py`, `test_checklist_rules.py`, `test_review_rules.py`, `test_monitoring_rules.py`, and their fixtures for typed IDs, retaining all status/date/version assertions.
  - Update provider/repository/query/update/review/checklist/dashboard/monitoring tests and browser fixtures to the new contracts and twelve-table schema. Extend `db_url` truncation to all target tables; keep guards and model disabling.
  - Move the old three-migration rollback tests onto the isolated legacy-prefix helper. Keep their old rollback/reapply assertions, and separately test the new guarded-down behavior. Upgrade fixtures must contain valid full legacy contexts, not `{}` placeholder snapshots; add an explicit test proving invalid contexts fail preflight.
  - Expand complete provider-cascade tests to include snapshots/warnings and verify another provider and every shared catalog/version remain. Keep direct audit UPDATE/DELETE and requirement-delete bypass tests.
  - Test case-normalized catalog reuse, latest versus assigned versions, immutable used membership, concurrent version assignment, creation retry after a new version or archive, and repeat seed after progress. This covers Review Focus 1, 3, and 5.

- [ ] **Verify and commit the atomic task.** First run the focused migration/catalog/model/provider/update/review/checklist tests; expected all PASS. Regenerate `db/schema.sql` only from passwordless disposable PostgreSQL. Update affected layout/contract documentation in `AGENTS.md`/`README.md`, not the proposal. Run `uv run ruff check`, `uv run mypy`, and `uv run pytest`; expected all checks pass, no skips, and every former behavior assertion retained. Commit `feat: migrate checklists to the normalized integer schema` only after the full suite is green.

## Task 2: Preserve browser retry safety across the cutover

**Files:** Create `app/static/checklist-recovery.js`, `tests/e2e/test_upgrade_recovery.py`; modify `app/static/checklist.js`, `onboarding.js`, `app/page.py`, and existing checklist/provider browser tests.

**Interfaces:**
- `inspectLegacyAttempt(storage) -> object | null`: validates and retains the old UUID-era pending object without treating its parent UUIDs as current resource IDs.
- `recoverLegacyAttempt({api, attempt}) -> Promise<{kind, provider, event}>`: uses `GET /providers?state=all` to match `creation_request_id`, then the existing provider checklist-history endpoint to match the saved `operation_id`. No new endpoint, table, POST, or ID mapping by display name.
- `kind` is `saved`, `unresolved`, or `unavailable`. Only a matched committed event supplies new integer provider/requirement IDs. Rendering and storage updates stay in the checklist controller.

- [ ] **Write browser regressions first.** Use literal legacy session-storage objects and target rows whose creation/operation keys retain those UUIDs:
  - A save committed before migration but with a lost response resolves through `operation_id`, displays its saved values, and issues zero new save POSTs. Later progress is not overwritten.
  - A pending legacy attempt with no matching saved event remains readable until explicit dismissal; no guessed requirement ID or automatic replay. Say the saved operation is unavailable, not that it definitely never happened.
  - A missing/deleted provider does not get recreated or selected by a duplicate display name. Archived matches open the archived read-only view. A mismatched saved operation produces a conflict notice rather than confirmation.
  - Current integer-ID attempts still freeze one UUID operation key across role/provider switches, reload, response loss, and failed view refresh. Browser-storage failure retains in-memory recovery.
- [ ] **Run `uv run pytest tests/e2e/test_upgrade_recovery.py -v` and inspect RED.** Expected failure is the missing legacy recovery behavior, not a live model/network dependency.
- [ ] **Implement the recovery module and controller integration.** Retain the original storage entry until its committed operation is resolved or the user explicitly dismisses the draft. A resolved event can become a confirmed integer-era attempt; clear it only after a coherent saved snapshot loads. For an unresolved draft show provider name and submitted status/date/deadline values, with an explicit dismissal action; never infer a requirement from the name/counter or generate a second operation UUID silently. Keep retry behavior for new attempts unchanged.
- [ ] **Run the focused browser tests, then Ruff/mypy/full pytest.** Expected all PASS. This covers Review Focus 4 and the browser portion of Focus 5. Commit `fix: recover checklist saves safely after the ID cutover`.

## Task 3: Rehearse release and backup-based recovery

**Files:** Create `tests/e2e/test_database_upgrade.py`, `docs/database-cutover.md`; modify `tests/e2e/conftest.py`, `.github/workflows/tests.yml`, `README.md`, and the current-versus-target description in `docs/database-design.md` only when implementation is complete.

**Interfaces:**
- Extend `AppServer` with optional `source_root: Path = ROOT`, preserving its existing defaults. A stopped server can restart from another source root on the same port and guarded database. Its child receives only the test database, PATH/PYTHONPATH, scenario, and controlled clock; never application credentials.
- Test utilities archive the pinned legacy commit into a temporary directory without moving HEAD or reading `.env`. CI checkout uses `fetch-depth: 0` so that commit is local; no test fetches code over the network or silently skips a missing baseline.
- Test backup helpers use PostgreSQL 18 `pg_dump`/`pg_restore` on guarded loopback databases, passing connection settings through a minimal environment rather than a credential-bearing URL argument. Restore into a separate empty disposable database, not on top of target tables.

- [ ] **Write the cutover rehearsal test first.** Start the old app against the three-migration schema, create synthetic progress/history with TestModel, and produce an ambiguous committed browser save. Stop/drain the old server, then capture a verified test-only backup containing the final committed write. Apply the new migration and restart the new server on the same origin. Assert the new UI recovers the operation, shows preserved saved/captured states and history, selects duplicate names correctly, and can analyze/review/edit/create with integer IDs. Verify no connection spans model work and no archived progress mutation is possible.
- [ ] **Write recovery checks.** Guarded SQL down must leave the target unchanged. Restore the pre-cutover backup into a fresh disposable database and start the old app there; assert its original UUID links, statuses, dates, warnings, and audit values work. The rehearsal may create new target-era records, but does not claim that restoring an older backup preserves those later writes.
- [ ] **Run the new E2E tests and inspect RED**, then implement only the harness/CI changes required to run the real old-to-new and restore paths. Run all existing and new tests; expected no skips and no real model requests.
- [ ] **Write the concrete operator runbook**, covering:
  1. Review the exact committed migration line by line against all eleven design checks and verify the complete PR's tests/review. Pin old/new application revisions.
  2. Rehearse backup/restore before the maintenance window. Keep credentials out of files, command arguments, logs, and Git. Confirm the operator's intended Neon project/connection without printing its URL.
  3. Stop user traffic and old workers, drain/resolve in-flight writes, preserve frozen browser data, and ensure no old process can finish another UUID-era write. Only then take and verify the final cutover backup, including the last committed write; an earlier rehearsal backup is insufficient for rollback. Keep writes stopped through conversion and validation.
  4. Apply the reviewed migration explicitly with schema dumping disabled, start only the matching new application, and perform read-only preservation/health checks before admitting new user writes. Check applied migration state and exact target constraints; seed only a deliberately empty database.
  5. If validation fails before writes are admitted, restore the verified backup to a clean recovery database and run the old application. After new writes begin, do not automatically restore an older backup and lose them: stop traffic, preserve the new state, and use a reviewed forward fix or explicit reconciliation.
  6. Reload browser assets, confirm legacy save recovery, and retain operator rollback evidence outside the application schema. Real-model evaluation and managed login are not cutover smoke tests.
- [ ] **Finish documentation and verify.** Update the design's current-schema description only after the twelve tables/current flows actually exist; keep future lifecycle action controls and managed sign-in clearly separated. Preserve `docs/proposal.md`. Run `uv run ruff check`, `uv run mypy`, and `uv run pytest`; inspect every result. This covers Review Focus 2 and end-to-end cutover behavior. Commit `test: rehearse database cutover and backup recovery`.

## Completion and release boundary

- [ ] All three tasks are complete with observed RED→GREEN tests and green full-suite evidence. No temporary legacy schema/maps remain after successful conversion; failed conversion leaves the old database untouched.
- [ ] A fresh whole-branch code review checks this plan's five Review Focus cases, the design, and the full feature-branch diff. Address material findings with reproducing tests.
- [ ] Open one coordinated implementation PR with the required Summary, code-verified diagram, and checked Test plan; watch CI. Do not merge it.
- [ ] The person reviews/merges; Neon cutover requires separate explicit authorization and the runbook's verified backup/maintenance gates. Planning or code completion alone is not permission to alter Neon.
- [ ] Archive/Restore/Delete action endpoints/buttons and managed sign-in remain separate follow-up work; do not claim that the entire product feature set is implemented by this schema cutover.

## Plan self-review

The three tasks cover the migration/current-app dependency as one atomic unit,
legacy browser uncertainty as a separate behavior, and operational cutover/recovery
as a tested deliverable. All twelve table contracts, required indexes/checks,
version isolation, current flow preservation, and future-work exclusions map to
Task 1; the five Review Focus cases have explicit owners/tests. Contracts consistently
separate positive integer resource IDs from UUID retry keys and reconstructed
snapshot values from live progress. No production migration or implementation is
performed by creating this plan.
