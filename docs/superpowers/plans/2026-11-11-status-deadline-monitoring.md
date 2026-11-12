# Status and Deadline Monitoring Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Show server-derived completion, deadline indicators, and four counts for the selected synthetic provider, backed by unit, PostgreSQL integration, and browser tests.

**Architecture:** Pure Python rules classify the saved checklist. An additive read service returns the unchanged StoredProvider and monitoring derived from that exact fetched model with one Hawaii as-of date. The browser renders that coherent dashboard alongside the existing update/review history; no write workflow or persisted snapshot changes.

**Tech Stack:** Existing Python 3.13+, FastAPI, Pydantic 2.14.1, Psycopg 3/PostgreSQL 18, pytest, and Playwright/Chromium. Use standard-library `datetime`/`zoneinfo`; retain current locked dependencies and CI setup.

**Spec:** [Status and Deadline Monitoring](../specs/2026-11-11-status-deadline-monitoring-design.md), together with [the project proposal](../../proposal.md), especially **Data Use > Status and Deadline Monitoring**, **Human Review**, and **Testing Strategy**.

## Global Constraints

- Derive completion from the saved status using requirement-specific rules. Do not add a separate manager-controlled completion field.
- Preserve the original status, requirement date, deadline, and original update/review evidence.
- Support the existing canonical Dentist type and five canonical requirement names. Other types or requirements need review even when their statuses match.
- Compare status text using surrounding-whitespace trimming and case folding, without altering the stored value. No substring matching, LLM, fuzzy matching, or inferred synonyms.
- Use the requirement's saved `deadline` only. Its `scheduled_date` and the provider's proposed start date cannot substitute for a missing deadline.
- Use `Pacific/Honolulu`. Equality with today is not overdue. This clock does not change incomplete-date inference or introduce a today fallback there.
- Remaining includes known unfinished and Needs review. Overdue and Needs review are subsets of Remaining.
- No schema migration, new dependency, Neon mutation, or model invocation is needed for this slice. No deadline editor, inferred deadlines, seed overwrite, polling, authentication, or readiness judgment.
- All automated tests use isolated loopback PostgreSQL and deterministic `TestModel` where extraction is exercised; real model requests remain disabled in pytest and the browser server. Never load `.env` into tests or use Neon for verification.
- Preserve saved-analysis/failed-refresh retry IDs, independent manager decisions, existing read/write contracts, and clock-free stored context snapshots.
- Run Ruff, mypy, and the complete pytest suite after each task. No skipped tests, ignored errors, weakened checks, or commits to main. Open a PR, apply the PR-diagram skill, watch checks, and leave merging to the user.

## Review Focus

1. Negated or qualified completion wording such as `Not completed`, `Completed?`, or `Not received` must not silently finish a requirement (Task 1).
2. An unfamiliar status with a past deadline must keep the passed deadline visible without inflating confirmed Overdue counts (Tasks 1, 3).
3. An approval committed during a dashboard read must not mix checklist values from one read with monitoring from a second read (Task 2).
4. UTC/Hawaii midnight and browser date-only parsing must not move the as-of day or mark a due-today item overdue (Tasks 2, 3).
5. A lost dashboard refresh after successful analysis/review must remain honest about the saved operation, retain a whole prior snapshot or clear it, and prevent duplicate extraction on retry (Task 3).

## Files and Responsibilities

| Files | Responsibility |
| --- | --- |
| Create `app/monitoring_models.py` | Dashboard response contracts and monitoring type aliases, separate from stored/extraction contracts. |
| Create `app/rules/monitoring.py` | Pure completion/deadline classification and aggregate counts; no clock, SQL, HTTP, or model client. |
| Create `app/monitoring.py` | Hawaii clock boundary and one-fetch dashboard orchestration. |
| Modify `app/main.py` | Add the typed read route and its date/repository dependencies. |
| Modify `app/page.py`, `app/static/onboarding.js` | Accessible counts, Monitoring column, as-of copy, atomic dashboard/history loading, and safe failure display. |
| Create `tests/test_monitoring_rules.py`, `tests/test_monitoring.py`, `tests/test_dashboard.py` | Pure rules, clock/service, and actual PostgreSQL/API coverage, respectively. |
| Create `tests/e2e/test_monitoring.py`; modify `tests/e2e/server.py`, `tests/e2e/conftest.py`, `tests/e2e/test_review_workflow.py` | Controlled test-only clock, saved-record/browser scenarios, and retained review/retry regressions. |
| Modify `AGENTS.md`, `README.md` | Actual new module responsibilities and implemented monitoring/date/unknown-state behavior. |

Keep `app/models.py`, repositories, migrations, seeds, extraction rules, and dependency files unchanged unless an actual discovered defect requires a recorded ruling. No compatibility re-exports are needed for the new monitoring modules. The proposal already records the product decisions; update it only if a new decision actually changes them.

## Pre-flight

- [ ] Confirm the approved design/proposal are present, the implementation branch is separate from main, and the checkout is clean. Honor the user's existing preference for a branch in this checkout and native execution; do not ask again about worktrees or execution method.
- [ ] Run `uv run ruff check`, `uv run mypy`, and `bash scripts/test.sh uv run pytest` as the clean baseline. Expected: both static checks pass and the existing 131 tests pass. Use `UV_CACHE_DIR=/private/tmp/onboard-uv-cache` locally when needed by the sandbox; keep the same commands inside the test wrapper.

## Task 1: Typed, Pure Monitoring Rules

**Files:** Create `app/monitoring_models.py`, `app/rules/monitoring.py`, `tests/test_monitoring_rules.py`; update the actual module layout in `AGENTS.md`.

**Interfaces:**
- Consumes unchanged `StoredProvider` / `StoredRequirement` from `app.models`, with nullable `deadline`, separate `scheduled_date`, and stable requirement IDs.
- Produces `Completion = Literal["finished", "outstanding", "needs_review"]` and `DeadlineState = Literal["not_set", "upcoming", "due_today", "past"]` in `app.monitoring_models`.
- `RequirementMonitoring(BaseModel)`: `requirement_id: UUID`, `completion: Completion`, `deadline_state: DeadlineState`.
- `MonitoringCounts(BaseModel)`: nonnegative integer `total`, `finished`, `remaining`, `overdue`, `needs_review`.
- `ProviderMonitoring(BaseModel)`: `as_of_date: date`, `time_zone: Literal["Pacific/Honolulu"] = "Pacific/Honolulu"`, `requirements: list[RequirementMonitoring]`, `counts: MonitoringCounts`.
- `ProviderDashboard(BaseModel)`: `provider: StoredProvider`, `monitoring: ProviderMonitoring`. Do not add computed fields to StoredProvider or persist these DTOs.
- `classify_completion(provider_type: str, requirement_name: str, status: str) -> Completion`, `classify_deadline(deadline: date | None, as_of_date: date) -> DeadlineState`, and `monitor_provider(provider: StoredProvider, *, as_of_date: date) -> ProviderMonitoring` in `app.rules.monitoring`.

- [ ] **Step 1: Write the four agreed failing rule cases.** In `tests/test_monitoring_rules.py`, make a pure test helper `provider_with(name, status, deadline, *, provider_type="Dentist", scheduled_date=None, proposed_start_date=None) -> StoredProvider` with one requirement and UUIDs. It must not request a database fixture. Parameterize `test_confirmed_monitoring_scenarios` with these exact values; assert row completion/deadline classification and the single-row Finished/Remaining/Overdue/Needs review counts.

```python
AS_OF = date(2026, 11, 11)
# name, status, deadline, completion, deadline_state, finished, overdue
CASES = [
    ("Offer letter", "Signed", date(2026, 11, 10), "finished", "past", 1, 0),
    ("Drug screening", "Scheduled", date(2026, 11, 18), "outstanding", "upcoming", 0, 0),
    ("Drug screening", "Completed", date(2026, 11, 10), "finished", "past", 1, 0),
    ("Insurance credentialing", "Incomplete", date(2026, 11, 10), "outstanding", "past", 0, 1),
]
@pytest.mark.parametrize("name,status,deadline,completion,deadline_state,finished,overdue", CASES)
def test_confirmed_monitoring_scenarios(name, status, deadline, completion, deadline_state, finished, overdue):
    result = monitor_provider(provider_with(name, status, deadline), as_of_date=AS_OF)
    assert result.requirements[0].completion == completion
    assert result.requirements[0].deadline_state == deadline_state
    assert result.counts.finished == finished
    assert result.counts.remaining == 1 - finished
    assert result.counts.overdue == overdue
    assert result.counts.needs_review == 0
```

- [ ] **Step 2: Run `uv run pytest tests/test_monitoring_rules.py -v`.** Expected: collection/test failure from the missing monitoring interface, not database configuration or a model request.
- [ ] **Step 3: Write the remaining failing rule cases using these exact mappings.**

| Dentist requirement | Finished | Known unfinished |
| --- | --- | --- |
| Offer letter | Signed | Pending, Outstanding, Incomplete |
| Hawaii dental license | Received | Pending, Outstanding, Incomplete |
| Drug screening | Completed | Scheduled, Pending, Outstanding, Incomplete |
| State NED license | Received | Outstanding, Pending, Incomplete |
| Insurance credentialing | Approved | Pending, Submitted, Outstanding, Incomplete |

Parameterize every mapped status from the table. Add `test_completion_matches_status_only_after_trim_and_casefold` (`" completed "` / `"COMPLETED"` finish drug screening); `test_negated_and_qualified_statuses_need_review` (`"Not completed"`, `"Completed?"`, license `"Not received"`, credentialing `"Submitted; awaiting approval"`); and `test_type_and_requirement_boundaries` (other type + Drug screening/Completed, unknown requirement, or Offer letter/Completed all need review). Add `test_deadline_boundaries` for None and Nov 10/11/12 with the fixed Nov 11 date; scheduled dates and missing/changed proposed start dates must not affect results. Add `test_unknown_past_deadline_keeps_uncertainty` asserting `completion == "needs_review"`, `deadline_state == "past"`, `overdue == 0`, `remaining == needs_review == 1`. Add mixed counts (one finished, one overdue, one unknown past: total 3, finished 1, remaining 2, overdue 1, needs_review 1), empty-list counts, and a Completed→Incomplete reversal; assert raw provider/status/date/version values are unchanged. These tests are written while the monitoring interfaces are still missing, before implementation. The mapping table above supplies their exact configured values.

- [ ] **Step 4: Implement the contracts and rules.** Match canonical type/name exactly and normalize status only with `strip().casefold()`. Use the exact rule table above. Unknown type, name, empty status, misleading/other wording returns Needs review. Determine deadline state independently; count confirmed Overdue only for outstanding + past. Keep row order aligned with the passed provider's requirements, include each ID, and calculate Remaining as total minus finished. An empty list produces zero counts.
- [ ] **Step 5: Run `uv run pytest tests/test_monitoring_rules.py -v`, then `uv run ruff check`, `uv run mypy`, and `bash scripts/test.sh uv run pytest`.** Expected: all focused tests pass without a database; Ruff/mypy and `bash scripts/test.sh uv run pytest` pass without skips.
- [ ] **Step 6: Commit `feat: derive typed checklist monitoring with pure rules`.** Include only Task 1 files and AGENTS.md layout updates.

## Task 2: Coherent Read-Only Dashboard API and Hawaii Clock

**Files:** Create `app/monitoring.py`, `tests/test_monitoring.py`, `tests/test_dashboard.py`; modify `app/main.py` and `AGENTS.md`.

**Interfaces:**
- Consumes Task 1's `monitor_provider` and `ProviderDashboard`, plus existing `ProviderRepository.get_provider(provider_id: UUID) -> StoredProvider` (async) and existing safe error handlers.
- Produces `hawaii_date_at(instant: datetime) -> date`, `get_monitoring_date() -> date`, and `async get_dashboard(repository: ProviderRepository, provider_id: UUID, *, as_of_date: date) -> ProviderDashboard` in `app.monitoring`.
- `hawaii_date_at` requires an aware instant; reject naive values with ValueError instead of applying the host's time zone. `get_monitoring_date` captures `datetime.now(UTC)` once and converts through `ZoneInfo("Pacific/Honolulu")`.
- `GET /providers/{provider_id}/dashboard` returns ProviderDashboard, using `Depends(get_repository)` and `Depends(get_monitoring_date)`. It has no browser-controlled date/status/checklist argument. Existing `GET /providers/{id}`, provider list/history endpoints, stored snapshots, and all write responses stay unchanged.

- [ ] **Step 1: Write failing clock/service and HTTP tests.** `test_hawaii_date_boundary` asserts `hawaii_date_at(datetime(2026,11,11,9,59,59,tzinfo=UTC)) == date(2026,11,10)` and at `10:00:00 UTC` equals Nov 11; an aware non-UTC representation of the same instant must agree. Add naive-instant rejection and `get_monitoring_date` using a patched aware clock. In `tests/test_dashboard.py`, override the exact imported `get_monitoring_date` dependency with Nov 11 on the existing client and restore overrides afterward. Assert 200, unchanged provider data, metadata date/time zone, stable row IDs, and seed counts `total=5, finished=2, remaining=3, overdue=0, needs_review=0` (seed deadlines remain null). Also assert raw `/providers/{id}` still has no monitoring fields. Add `test_browser_query_values_do_not_override_saved_monitoring`: `?as_of_date=1900-01-01&status=Completed` leaves the server date Nov 11, the saved Scheduled status, and the seed counts unchanged.
- [ ] **Step 2: Write read-consistency and read-only tests.** `test_dashboard_uses_one_provider_and_date_snapshot` wraps the real repository fetch: after its first saved model is read, change drug status on another guarded DB connection before returning that model. Assert the response contains the original status and matching original monitoring, and the provider/date dependencies were each used once; a subsequent request reflects the committed change coherently. `test_dashboard_reads_do_not_modify_records_or_snapshots` compares all seven application tables before/after repeated dashboard GETs, including versions and stored context JSON. Add an unknown synthetic type with a matching requirement/status (Needs review), an empty checklist (zero counts), and 404/422/503 tests, including missing config/schema and no URL/raw-driver details in errors.
- [ ] **Step 3: Write failing approval-lifecycle coverage.** `test_monitoring_changes_only_after_approved_status_updates` uses the existing TestModel client and a past drug-screen deadline in the disposable DB. Assert pending Completed suggestions leave monitoring unchanged, rejection also leaves it unchanged, approval changes the row to finished without an overdue warning, and a later corrected approval to Incomplete returns it to Remaining/Overdue. Create each proposal with a new request ID; retain original suggestions and context. Use existing review API/model-override patterns from `tests/test_reviews.py`, without changing production review code. Add saved unknown/past, due-today, and missing-deadline endpoint cases matching Task 1's exact results.
- [ ] **Step 4: Run `bash scripts/test.sh uv run pytest tests/test_monitoring.py tests/test_dashboard.py -v`.** Expected: missing clock/service imports or 404 for the unimplemented dashboard route; no Neon or real model access.
- [ ] **Step 5: Implement the clock, service, and route.** Capture the date at the dependency boundary and await the provider read once. Derive monitoring from that exact returned model after the repository releases its connection. Return the unchanged provider alongside its monitoring. Keep all comparisons out of routes and all clock/SQL access out of pure rules. Preserve 404, malformed-ID 422, and safe database/configuration/schema 503 mapping. Extraneous query values such as `?as_of_date=1900-01-01&status=Completed` cannot override saved inputs or the server date.
- [ ] **Step 6: Run `bash scripts/test.sh uv run pytest tests/test_monitoring.py tests/test_dashboard.py -v`, `uv run ruff check`, `uv run mypy`, and `bash scripts/test.sh uv run pytest`.** Expected: focused/static/full checks pass, no skips or writes outside guarded tests.
- [ ] **Step 7: Commit `feat: serve a coherent read-only monitoring dashboard`.** Include Task 2 files and layout updates.

## Task 3: Dashboard Display and Browser Acceptance Coverage

**Files:** Modify `app/page.py`, `app/static/onboarding.js`, `tests/e2e/server.py`, `tests/e2e/conftest.py`, `tests/e2e/test_review_workflow.py`, `README.md`, `AGENTS.md`; create `tests/e2e/test_monitoring.py`.

**Interfaces:**
- Consumes the Task 2 dashboard JSON `{provider, monitoring: {as_of_date, time_zone, requirements, counts}}`; the browser joins row indicators by `requirement_id` to the provider returned in that same response. No separate checklist fetch or browser date/completion/count calculation.
- Preserve existing `loadState()` / `renderChecklist()` entry points and saved-operation handlers. Add `state.monitoring`, committed together with `state.provider` and history only after both dashboard and history reads succeed and the current generation/provider check passes.
- For deterministic test servers, extend `create_test_app(test_database_url: str, scenario: str, as_of: date = date(2026,11,11))` to override `get_monitoring_date`. Add test-only CLI `--as-of` parsed as an ISO date. Extend `AppServer(database_url, log_path, *, as_of: date = date(2026,11,11))`; retain it across restarts and pass only that synthetic date in subprocess arguments. Preserve TestModel request guards and the child environment's exclusion of model/application credentials. No production date override.

- [ ] **Step 1: Write browser RED cases before adding page controls.** Freeze the test server clock as above. Create a synchronous `monitoring_records` fixture in the new browser test module using existing `seeded_provider` and `configured_test_url()` guards; alter only disposable records. Baseline: offer Signed/deadline Nov 10; Hawaii license Received/no deadline; drug Scheduled/deadline Nov 18; NED Outstanding/no deadline; insurance Incomplete/deadline Nov 10. Parameterize `test_monitoring_acceptance_cases` over the four agreed cases, adjusting the target row's status/deadline before navigation. Assert its exact label and summary values: baseline Finished 2, Remaining 3, Overdue 1, Needs review 0; drug Completed/deadline Nov 10 gives 3/2/1/0. Require an accessible `Monitoring summary` region and column header `Monitoring`.
- [ ] **Step 2: Add workflow, uncertainty, clock, and empty-state browser cases.** `test_monitoring_approval_reversal_and_restart`: set a past drug deadline, propose Completed without changing counts, approve as Manager, propose again and correct to Incomplete, then restart/reload and assert matching saved status/indicators/counts. Rejecting another proposal and switching roles must leave them unchanged. `test_unknown_past_status_is_visible_and_text_safe`: store an HTML-like unfamiliar status in the guarded DB; assert raw text, Needs review count, combined passed-deadline label, no injection, and no extra confirmed Overdue count. `test_due_today_and_date_label_use_server_day` covers Nov 11/Nov 12/null deadlines and the exact date label, independent of browser time zone. `test_empty_checklist_has_zero_counts_without_readiness_claim` checks the explicit empty message. Write narrow-layout, keyboard-access, and no-document-overflow assertions for inspection during the GREEN step.
- [ ] **Step 3: Retain and extend failure/retry coverage.** Preserve all existing review workflow assertions. Extend `test_saved_analysis_with_failed_refresh_reuses_request_on_retry` to parameterize failure of history versus `/providers/*/dashboard`: a successful POST followed by failed refresh retains the request ID; retry leaves one saved update. Add `test_saved_review_with_failed_dashboard_refresh_is_reported_honestly`: after a successful decision, a failed dashboard refresh shows the saved-operation message and no mixed new/old checklist/indicator snapshot; restoring reads + Refresh data shows the saved change. Initial dashboard failure clears/hides indicators and disables submission without fallback zeros. Retain missing-schema, lost-response, and stale-review behavior, adapting request interception only where paths actually change. Use controlled routes/events instead of arbitrary waits.
- [ ] **Step 4: Run `bash scripts/test.sh uv run pytest tests/e2e/test_monitoring.py -v`.** Expected: browser assertion failures for missing summary/monitoring labels. Do not replace real app/PostgreSQL with mocked dashboard JSON as proof of the main workflows.
- [ ] **Step 5: Implement the page and coherent loading.** Above the checklist, render four labeled counts plus `As of 2026-11-11 · Hawaii (Pacific/Honolulu)` using the returned date-only string (do not parse it as UTC with `new Date`). Add the Monitoring column and concise explanations that Remaining includes uncertain items and Needs review concerns completion rules. Render labels from the server's completion/deadline states: Finished; Outstanding; Outstanding — due today; Overdue; Needs review; Deadline passed — needs review. Finished always displays Finished. Use textContent for all dynamic content and text alongside color. Preserve scrolling inside the checklist on narrow viewports. On valid empty data show zero counts and `No checklist requirements are saved for this provider.`; before successful loading or after cleared errors, do not fabricate zero counts. Clear provider description, summary/as-of, and rows together when no provider is available. No preview date picker, scenario buttons, readiness claim, or deadline editor.
- [ ] **Step 6: Run focused browser coverage to GREEN and document the implemented behavior.** Run `bash scripts/test.sh uv run pytest tests/e2e/test_monitoring.py tests/e2e/test_review_workflow.py -v`. Expected: all scenarios pass with deterministic dates, real app/DB, and blocked real models. Inspect desktop/narrow output and keyboard access; keep screenshots under this implementation plan's ignored workspace or pytest temp paths, not the prior plan's directory. Update README's monitoring counts, synthetic rule scope, unfamiliar-status meaning, Hawaii/as-of/refresh behavior, and saved-deadline-only boundary; update AGENTS.md for actual modules. Keep dependency/CI configuration unchanged because normal pytest already discovers these tests.
- [ ] **Step 7: Run `node --check app/static/onboarding.js`, `uv run ruff check`, `uv run mypy`, and `bash scripts/test.sh uv run pytest`.** Expected: syntax/static checks and the complete unit/integration/browser suite pass without skips.
- [ ] **Step 8: Commit `feat: display checklist monitoring with browser acceptance tests`.** Include only the Task 3 files.

## Completion Verification

- [ ] Self-check every design section against the implementation. Confirm exact mappings, raw statuses/snapshots preserved, one fetched checklist/date per dashboard, uncertainty/count semantics, no clock in rules, and no application-data mutation or new dependencies.
- [ ] Use one fresh whole-branch reviewer under the chosen native execution workflow; include this plan's five Review Focus lines and the design. Resolve material findings with regression tests and rerun required checks. Do not dispatch extra plan-review agents; plan self-review belongs to this author.
- [ ] Inspect the complete PR diff for credentials and unintended production test switches. Open/refresh the implementation PR against the verified current base, cite the proposal sections, maintain one code-backed change diagram via the PR-diagram skill, and run `gh pr checks --watch` after pushing. Report actual results and leave the PR unmerged.

## Execution Handoff

The user has already selected **native execution**. Hand off this saved, self-reviewed plan for review before implementation, then use executing-plans with that preserved method. Writing the plan changes no application or database records.
