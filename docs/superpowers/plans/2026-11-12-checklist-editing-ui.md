# Checklist Editing and UI Refinements Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Deliver the approved striped checklist with status dropdowns, audited Manager edits to status/date/deadline, and the requested section refinements.

**Architecture:** Share recognized status choices and completion rules in plain Python. A focused checklist-edit service/repository validates roles and locks/updates one requirement with an immutable retryable audit record. Browser checklist editing is separate from selection/history orchestration; dashboard-derived edit options drive both status dropdowns.

**Tech Stack:** Existing FastAPI/Pydantic/Psycopg/PostgreSQL/dbmate, native JavaScript, pytest/Playwright/TestModel; no new dependencies.

**Spec:** `docs/superpowers/specs/2026-11-12-checklist-editing-ui-design.md`, approved by the user's “proceed”; canonical proposal synchronized in this feature.

## Global Constraints

- Continue native execution in this checkout on feat/checklist-editing-ui; preserve prior user execution/workspace preferences. Base origin/main e344e9b; design cb57cf1. No new approval round for the plan.
- Fictional providers and synthetic updates only. TestModel with real requests disabled in all test layers; disposable local PostgreSQL only, never Neon or application .env.
- Manager-only manual saves enforced server-side; all three fields edited together explicitly, no model call or fabricated suggestion. Requirement/provider/template editing remains excluded.
- A stable UUID identifies one submitted edit. Identical retry returns original event; changed input conflicts. Any real change increments the requirement version once and atomically saves before/after evidence.
- Dropdown vocabulary matches existing canonical Dentist monitoring rules; preserve unfamiliar saved/proposed values verbatim. Other types never inherit Dentist completion semantics.
- Dates accept explicit full dates or null, no inferred date/order policy. Deadline-only saves affect monitoring and stale proposals exactly like status/date saves.
- Required gates: Ruff, mypy, Node syntax, full PostgreSQL/browser pytest; one fresh final review; feature PR with diagram; watch CI; never merge.

## Review Focus

1. Lost manual-save responses followed by altered drafts, refreshes, or later progress must never duplicate events or reset newer values.
2. Deadline-only edits and simultaneous manual edits/suggestion approvals must share the requirement version/lock and preserve coherent monitoring and history.
3. Unfamiliar/case-varied saved or proposed statuses must remain verbatim in dropdowns, with safe fallback for other provider types and no inferred finished status.
4. Disclosure state and pending counts must survive normal refresh/review while closing on provider switch, without hiding the existence of newly generated suggestions.
5. A known saved edit followed by failed dashboard/update/edit-history loading must be reported honestly and recover without mixing provider snapshots or losing operation identity.

## Files and Responsibilities

- New `app/rules/statuses.py`: shared canonical status vocabulary, choices, completion and badge tone. `app/rules/monitoring.py` consumes it without changing monitoring semantics.
- New `app/checklist_models.py`: direct edit request/event and derived requirement edit options. `app/monitoring_models.py`/`app/monitoring.py` expose options from the loaded provider.
- New `app/rules/checklist.py`, `app/checklist.py`, `app/repository/checklist.py`: pure edit/retry rules, role orchestration, and locked atomic persistence/history respectively. `app/main.py` wiring only.
- New dbmate migration `20261112000100_add_checklist_edits.sql`; regenerate schema locally; update guarded test truncation for the FK.
- New `app/static/checklist.js`: saved rows, badges, direct-edit drafts/retry controller. New `app/static/statuses.js`: native status-select/badge helpers. `onboarding.js`: complete snapshot loading and combined history/disclosure; `review.js`: dropdown correction row; `page.py`: structure/styles.
- New `tests/test_checklist_rules.py`, `tests/test_checklist_edits.py`, `tests/e2e/test_checklist_edits.py`; adapt retained browser tests to open disclosure and use dropdowns (retain behavioral assertions).
- `docs/proposal.md`, `AGENTS.md`, `README.md`: direct-save policy, actual layout/module responsibilities, migration and usage.

### Task 1: Atomic Checklist Edit API and Authoritative Status Choices

**Interfaces:**
- `ChecklistEditRequest`: extra forbidden; `id: UUID`, strict nonnegative `expected_version: int`, nonblank preserving-whitespace `status: str`, required nullable `scheduled_date: date | None`, `deadline: date | None`.
- `ChecklistEdit`: request ID `id`, provider/requirement IDs and captured requirement_name, expected_version/resulting_version, previous_status/previous_scheduled_date/previous_deadline, applied_status/applied_scheduled_date/applied_deadline, reviewer_role literal manager, created_at datetime.
- `RequirementEditOptions`: requirement_id UUID, statuses list[str], status_tone literal finished/progress/attention/unknown. `ProviderDashboard.checklist_options` supplies these without adding fields to stored snapshots.
- `status_choices(provider_type, requirement_name, *preserved) -> list[str]` returns ordered canonical choices from design plus unique verbatim preserved values; unfamiliar requirements/types start only Outstanding. `classify_completion` preserves existing normalized matching. `status_tone` uses that classification before blue/amber subgroups.
- Repository `edit(provider_id, requirement_id, request) -> ChecklistEdit`: transaction advisory lock on operation ID, existing-event identity check before row read, requirement ownership/type lookup with FOR UPDATE, pure version/status/no-op validation, UPDATE all three fields/version+1 and INSERT audit atomically. `list_for_provider(provider_id) -> list[ChecklistEdit]` requires an existing provider.
- Service `edit_checklist(repository, provider_id, requirement_id, request, role) -> ChecklistEdit` checks Manager before writes/retries. Domain forbidden/conflict/invalid map to 403/409/422; missing records404 and database/config/schema safe503.
- POST `/providers/{provider_id}/requirements/{requirement_id}/edits` returns201 event. GET `/providers/{provider_id}/checklist-edits` returns list newest first.

- [ ] **Step 1: Write unit RED.** Name tests for nonblank/verbatim status, required nullable dates, strict version/invalid dates/extra fields; choices/tones for all five requirements and unknown/case-varied statuses; Manager/no-op/stale/invalid choice and identical/conflicting retry rules. Assert literals independent of production helpers.
- [ ] **Step 2: Write integration RED.** Save three fields with exact before/after/version1/history and untouched previous provider; deadline-only monitoring boundary and clearing dates; forbid missing/Proposer; bad/missing ownership; unknown input; no-op; atomic failure via rejected audit insert; immutable DB UPDATE/DELETE; safe missing configuration/schema. Test identical retry after later progress, conflicting ID payload/path, concurrent identical/conflicting IDs, different IDs on same version, stale suggestion approval after manual save and reverse order. Assert one complete event per winning mutation, no partial writes/model calls.
- [ ] **Step 3: Run RED.** `bash scripts/test.sh uv run pytest tests/test_checklist_rules.py tests/test_checklist_edits.py -v`. Expected: missing edit API/status module failures.
- [ ] **Step 4: Implement migration/contracts/rules/service/repository/routes and derived options.** SQL constraints enforce ownership, nonblank values, role, changed row and resulting=expected+1. Reject audit UPDATE/DELETE with a trigger; tests truncate explicitly. Keep existing extraction/review contracts and locks. Synchronize proposal Provider Types and Checklists, Status and Deadline Monitoring, Human Review, Testing Strategy, and backend AGENTS layout.
- [ ] **Step 5: Focused GREEN.** Same focused command: all pass. Run Ruff/mypy, generate db/schema.sql with pg_dump from passwordless disposable DB using the migrations, verify retained integration/monitoring contracts in full suite. Expected no warnings/skips or real model requests.
- [ ] **Step 6: Commit.** Full `bash scripts/test.sh uv run pytest`, Ruff/mypy/diff checks green; commit `feat: add audited manager checklist edits and status choices`.

### Task 2: Striped Checklist Editing and Page Refinements

**Interfaces:**
- `statusSelect({label, choices, value})` and `statusBadge(value, tone)` in statuses.js return DOM nodes. Review correction consumes options from authoritative dashboard plus saved/proposed strings.
- `setupChecklist({api, roleSelect, setBusy, onSaved})` returns `render(provider, monitoring, options)`, `setBusy(value)`, `resetDraft()`, `syncRole()`, `onSnapshotLoaded()`. It owns one open editor and pending operation ID/frozen payload; no provider/history loading.
- Save callback triggers full dashboard + original updates + checklist-edits reload for the same selection. Failed loads keep/clear a whole snapshot, preserve the pending attempt, and expose retry/Refresh without fabricated current data. Retrying same operation never reapplies newer progress. Provider/role switch closes unsaved editors; an uncertain submitted operation remains recoverable without cross-provider writes.
- onboarding combines saved updates and edits newest-first in the disclosure; initial/provider-change closed, normal load/role/decision preserves user's choice. Pending summary count derives only completed undecided suggestions. Analysis success names pending suggestions and points to summary without auto-opening.

- [ ] **Step 1: Write browser RED.** Assert closed disclosure/pending summary, keyboard toggle and persistence on refresh/analysis/review, closes on provider switch/reload; Updates heading, Add provider top-right at desktop/mobile, correct stripes per requirement. Manager-only Edit, three labeled fields, requirement-specific status select (no text status input), no-op/partial dates disabled, cancel/discard, Save exact new values/history/counts/restart, safe unfamiliar values/type fallback.
- [ ] **Step 2: Add recovery RED.** Lost successful save response followed by retry, changed fields, later progress and role/provider switch; same UUID/frozen payload, one event and no rollback. Parametrize failed post-save dashboard/update/edit-history reads; honest saved wording and Refresh recovery with coherent selected provider. Stale concurrent browser edit fails then refreshes; direct deadline-only edit makes prior suggestion stale. Include keyboard/390px screenshots and safe stored text.
- [ ] **Step 3: Adapt existing workflow tests.** Open history disclosure before interacting with/relying on visible suggestions; use select_option for valid corrections instead of fill; preserve rejection/date/monitoring assertions and characterize unfamiliar proposed values as selectable options. Run new file RED, expected missing manual edit/disclosure behavior.
- [ ] **Step 4: Implement focused modules and page wiring/styles.** Keep row stripes independent of editor insertion; one labeled editor, Save/Cancel, status badges, native dropdowns, full date fields, operation identity recovery, busy guards. Retain existing monitoring column/counts and provider creation/analysis/review behavior. Use approved teal/blue/green/amber/neutral palette; red stays overdue. Never rebuild disclosure element on history rendering.
- [ ] **Step 5: Update docs and verify.** README uses direct Manager edits, before/after history, pending counts, retry/stale recovery, migration requirement; AGENTS lists final module roles. Inspect desktop/narrow screenshots and keyboard. Focused new browser file passes; full suite retains all existing scenarios.
- [ ] **Step 6: Commit.** Node syntax all browser modules; Ruff, mypy, diff check; full disposable PostgreSQL pytest suite green without skips. Commit `feat: add striped checklist editor and collapsible history`.

## Completion and Handoff

- [ ] Self-check full design/spec coverage, migration snapshot and complete diff; no credentials or production model/test switches.
- [ ] One fresh whole-branch read-only review with Review Focus verbatim; fix material findings via RED→GREEN and full checks.
- [ ] Open PR with Summary citing affected canonical proposal sections, code-verified Mermaid diagram, Test plan; push/watch checks, never merge.

Plan self-review: both tasks share exact edit/event/options contracts and operation IDs; all approved fields, disclosure semantics, colors, history, recovery and scope limits map to steps above. Native execution preserves the user's established choice and the current “proceed” authorizes implementation without another plan approval round.
