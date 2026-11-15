# Database Deliverables Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans for native task-by-task execution.

**Goal:** Supply the requested migration/seed/query/test/settings files, verify `npx dbmate status` reports Pending: 0 and `uv run pytest` passes, and prepare the change through a reviewed PR.

**Architecture:** Move the existing explicit synthetic seed and real provider/checklist SELECT into the requested db package, preserving app compatibility and behavior. Add lazy disposable PostgreSQL ownership to the test harness so bare pytest safely supplies its own database, and pin the official npm dbmate CLI for npx.

**Tech Stack:** Existing Python/FastAPI/Pydantic/Psycopg/PostgreSQL/pytest/Playwright; dbmate 2.38.1 as a development npm tool. No schema or UI change.

**Spec:** User's exact acceptance list, plus canonical `docs/proposal.md` Saved Records/Testing Strategy. Existing migrations already create all eight application tables.

## Global Constraints

- Required paths: db/migrations/, db/seed.py, db/queries.py (one query function), tests/test_queries.py, .env.example (setting names, no real values).
- Use the established synthetic fixture: Dentist, Dr. Kekoa Ejemplo, five templates and five independently saved requirements. Repeated seeding preserves progress and existing checklists; do not invent new provider types or fake model history.
- Canonical query is the existing parameterized provider-by-UUID SELECT including provider type, start date and JSON-aggregated requirements; production repositories must use this same function.
- Tests never load .env or use Neon; use guarded loopback onboard_hq_test_* databases and TestModel with real requests disabled. Manual seed/status verification of the configured development DB is distinct from automated testing.
- Bare pytest creates/cleans only its own temporary PostgreSQL cluster when no TEST_DATABASE_URL was supplied. Respect and validate explicit TEST_DATABASE_URL; focused pure tests must not start a database.
- Preserve native execution in this checkout on chore/database-deliverables. Existing user authorization covers the concrete file/check requirements; no further design/execution preference round.
- Run Ruff, mypy (app and new db package), full pytest and CI; open PR with verified diagram. Repository instructions leave merging to the person; report that remaining completion step accurately.

## Review Focus

1. Bare pytest must never load application credentials or replace an explicit unsafe test URL with a fallback database.
2. Temporary PostgreSQL must be stopped/removed after failures or interrupts without stopping externally supplied test services.
3. Both seed entry points must preserve provider progress, template snapshot isolation, and stable identities across repeated runs.
4. Moving the query must preserve production lookup behavior for missing providers, empty checklists and multiple provider/type boundaries.
5. The npx command and CI must use the pinned official dbmate; status/seed verification must not expose credentials or dump the credentialed application schema.

### Task 1: Requested Seed and Query Modules

**Files:** new db/__init__.py, db/seed.py, db/queries.py, tests/test_queries.py; modify app/seed.py, app/repository/providers.py, app/repository/updates.py, app/repository/checklist.py, AGENTS.md, docs/proposal.md, pyproject.toml.

**Interfaces:**
- `db.seed.seed_synthetic(pool: DatabasePool) -> None` async, constants KEKOA_ID/DENTIST_ID/INITIAL_STATUSES, and async main; `uv run --env-file .env python -m db.seed` is the documented explicit CLI. app.seed remains a compatibility entry point and explicit reexports.
- `db.queries.fetch_provider(conn: AsyncConnection[dict[str, Any]], provider_id: UUID) -> StoredProvider` async is the one query function. Preserve parameterized UUID lookup, alphabetical requirements, type/start fields, empty [] and RecordNotFound behavior. Repository get_provider and stored-context/manual-edit reads call it.

- [ ] Write tests/test_queries.py first: seed/query an empty migrated DB, assert literal sample identity/type/start/five requirement statuses and ownership; repeat seed after approved progress/template change without reset/backfill; isolate a second provider/type; return empty checklist; missing UUID raises RecordNotFound; execute new CLI in a subprocess with isolated DB settings.
- [ ] Run `bash scripts/test.sh uv run pytest tests/test_queries.py -v`; expected missing db.seed/db.queries failures.
- [ ] Move established implementations without changing data/SQL semantics, preserve old app.seed imports/CLI, route repository reads through db.queries, typecheck db alongside app, update layout and canonical explicit seed/query paths.
- [ ] Focused tests pass; Ruff/mypy and full disposable DB suite pass; commit `refactor: expose database seed and provider query deliverables`.

### Task 2: Exact Local Commands and Evidence

**Files:** new tests/local_postgres.py, tests/test_local_test_runner.py, package.json/package-lock.json; modify tests/database.py, tests/conftest.py, .env.example, .gitignore, README.md, scripts/test.sh and CI only where needed to share the established runner safely.

**Interfaces:**
- `local_database_url() -> str` lazily starts one passwordless temporary loopback PostgreSQL18 cluster, caches its test-only URL, cleans up on startup failure. `stop_local_database() -> None` stops/removes only this owned cluster; no-op for supplied test services.
- configured_test_url uses an explicit TEST_DATABASE_URL unchanged and guarded; otherwise lazily obtains the local URL. Session teardown always calls stop_local_database. Set default Playwright browser path for direct pytest without loading .env. Pure tests do not call the database helper.
- npm dev dependency dbmate exactly 2.38.1; node_modules ignored; npx dbmate status reads the normal developer configuration. Existing checksum-verified standalone CLI remains supported for tests/CI.

- [ ] Write a subprocess regression: clear TEST_DATABASE_URL and application/model settings, run bare Python pytest for tests/test_queries.py, verify pass; prove the owned server is gone afterward using a captured test-only URL, and preserve an explicit unsafe-URL rejection. Avoid recursive invocation of this runner test.
- [ ] Watch the bare subprocess check fail with the old configured_test_url requirement. Implement lazy owned-cluster lifecycle/default browser path; use real PostgreSQL rather than mocks for the command/lifecycle check.
- [ ] Add pinned npm package/lock and install locally; blank .env.example settings, preserve real .env, document npm ci, migrations with schema dump disabled, python -m db.seed, npx status and bare uv run pytest. CI runs the new query tests as part of its existing full suite and checks npm tool setup against its isolated DB.
- [ ] Run `uv run ruff check`, `uv run mypy`, bare `uv run pytest` with no externally provided test URL. Verify focused pure tests start no cluster. Manually run the explicit development seed and npx dbmate status; report sample row counts and Pending: 0 without printing credentials.
- [ ] Commit `chore: make database acceptance commands reproducible`.

## Completion

- [ ] Self-review exact user deliverables and documented setup; no model/UI/schema changes or credentials in git.
- [ ] One fresh whole-branch read-only review on the most capable reviewer; fix material findings with RED→GREEN tests and a green full suite.
- [ ] Push/open PR with Summary citing canonical Persistence/Testing Strategy, code-verified change diagram and Test plan; watch CI. Clearly identify the person's merge as the remaining repository requirement.

Plan self-review: the two tasks share only the explicit seed/query entry points and isolated test URL; required paths and exact commands each have direct verification. Reuse existing seed data and SELECT, rather than adding unused duplicate examples or altering onboarding behavior.
