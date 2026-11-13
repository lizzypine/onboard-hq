# Provider Creation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Managers can add fictional providers from configured type templates and immediately use their independent, all-Outstanding checklists.

**Architecture:** Add validated type-catalog/creation contracts, pure role/identity rules, and a small creation service over an atomic repository operation. The browser gets a focused creation-form module; onboarding orchestration owns selected-provider snapshots and recovery. Reuse the existing schema, simulated role header, and review/extraction workflow.

**Tech Stack:** Existing FastAPI/Pydantic/Psycopg/PostgreSQL, native browser modules, pytest/Playwright and deterministic TestModel. No dependencies or migrations expected.

**Spec:** `docs/superpowers/specs/2026-11-12-provider-creation-design.md` (approved), plus canonical proposal Data Use > Provider Types and Checklists, Human Review, Incomplete Dates, and Testing Strategy.

## Global Constraints

- Manager-only creation, including server enforcement with `X-Demo-Role`; the switch is simulated, not authentication.
- Copy only the chosen stored type's configured requirements. Every new requirement starts Outstanding, scheduled_date/deadline null, version 0. No copied provider progress.
- Preserve existing provider records, checklists, context snapshots, updates and decisions; no template backfill.
- Name is required/nonblank, stored type ID is required, proposed start date is optional with no fallback. Duplicate display names are allowed and must be distinguishable in the picker.
- Use a stable creation UUID as the provider ID. Identical retries return current saved data without reinitializing; conflicting reused IDs return 409.
- Synthetic records only; no new type fixtures, template editor, deadline editing, provider editing/deletion, multi-provider updates, model changes or model calls during creation.
- All tests use isolated loopback PostgreSQL and TestModel with real model requests disabled. Never load .env into tests or use Neon for verification.
- Continue native execution on feat/provider-creation in this checkout, as previously selected. The approved design authorizes implementation without another permission round.

## Review Focus

1. Lost POST responses and post-save list/dashboard/history failures must preserve creation identity and recover the created selection without duplicate records or mixed snapshots.
2. A retry after template changes or approved progress must return the existing checklist without resets/backfill.
3. Simultaneous same-ID requests must create exactly one complete provider/checklist; different payloads under that ID must conflict.
4. Creating the first provider must work with configured templates even though no current provider exists and analysis is disabled.
5. The new provider's context, updates and approvals must never use or mutate the previous provider's data; duplicate names must not merge identities.

## Files and Responsibilities

- New `app/provider_models.py`: CreateProviderRequest and ProviderTypeTemplate contracts.
- New `app/rules/providers.py`: Manager role, initial status, nonempty-template and reused-ID rules/domain errors.
- New `app/providers.py`: creation orchestration, no HTTP or model calls.
- `app/repository/providers.py`: type catalog and locked, atomic template-based creation; preserve seed initialize_provider behavior.
- `app/main.py`: typed GET /provider-types and POST /providers, dependencies, safe 403/409 mapping.
- New `app/static/providers.js`: form lifecycle, type preview, stable creation ID, provider-label disambiguation and save/recovery callbacks.
- `app/static/onboarding.js`: coherent selection/loading, busy and role wiring, new-provider recovery; keep analysis/review contracts and retry IDs.
- `app/page.py`: Manager-only Add provider action, inline form/preview, synthetic-data copy and responsive styles.
- New `tests/test_provider_rules.py`, `tests/test_provider_creation.py`, `tests/e2e/test_provider_creation.py`; existing tests stay active.
- `AGENTS.md`, `README.md`, `docs/proposal.md`: actual module roles and approved creation behavior.

### Task 1: Atomic Manager-Only Creation API

**Interfaces:**
- `CreateProviderRequest(BaseModel)` in provider_models: extra forbidden; `id: UUID`, `name: NonBlank`, `provider_type_id: UUID`, `proposed_start_date: date | None = None`.
- `ProviderTypeTemplate(BaseModel)`: `id: UUID`, `name: str`, `requirements: list[str]`.
- `INITIAL_REQUIREMENT_STATUS = "Outstanding"`; pure `require_creation_manager(role)`, `require_same_creation(existing, requested)`, and `require_templates(names)` with ProviderCreationForbidden/ProviderCreationConflict errors.
- Repository `list_provider_types() -> list[ProviderTypeTemplate]` returns only nonempty templates, sorted by type/name; `create_from_template(request, *, initial_status: str) -> StoredProvider` serializes same-ID requests with transaction advisory locking, checks identity before any template read/reset, creates the provider and copied requirements atomically, and returns current saved data.
- Service `add_provider(repository, request, role) -> StoredProvider`: require Manager, pass the trusted initial status. Main GET /provider-types returns catalog; POST /providers returns StoredProvider with 201 for creation/identical retry; default role Proposer, forbidden 403, identity/empty-template conflicts 409, unknown type 404, malformed input 422, safe DB/config/schema 503.

- [ ] **Step 1: Write failing unit tests.** Name trimming, blank/invalid UUID/date/extra requirement-status fields rejected; absent date stays None; only Manager allowed; identical profile accepted, changes to name/type/start date under the same ID conflict; empty template rejected; initial status literal Outstanding.
- [ ] **Step 2: Write failing integration cases.** Assert catalog's five canonical Dentist requirement names; create Dr. Avery Example for 2027-01-15 and verify exact type/source IDs, all Outstanding/null dates/version 0, no updates, seed provider unchanged, dashboard counts 0/5/0/0. Missing/Proposer role returns 403 with no writes. Unknown/empty types fail without records; extra/blank/invalid input is 422. A separate synthetic type copies only its requirement and does not gain Dentist completion rules.
- [ ] **Step 3: Add transaction/retry cases.** Same request twice and two concurrent requests create one record/checklist. Reused ID with a changed name/type/date conflicts. Approve a TestModel update for the new provider, change its type template, then retry creation: approved progress and original requirement set survive; a different new provider gets the current template. Force a requirement-ID collision after the first insert via a patched UUID generator and verify rollback of provider and partial checklist. Missing configuration/schema endpoints return safe 503 errors.
- [ ] **Step 4: Run RED.** `bash scripts/test.sh uv run pytest tests/test_provider_rules.py tests/test_provider_creation.py -v`. Expected: missing imports/routes, no real model/Neon access.
- [ ] **Step 5: Implement contracts/rules/service/repository/routes.** Keep seed initialization unchanged; use transactional advisory lock keyed from UUID for same-ID serialization plus SQL identity constraints. Read/copy authoritative templates once per creation. Never reset an existing provider on retry. Add AGENTS layout entries and canonical Provider Types and Checklists creation rules.
- [ ] **Step 6: Verify and commit.** Focused tests, Ruff, mypy, then `bash scripts/test.sh uv run pytest` must pass without skips. Commit `feat: create providers atomically from configured templates`.

### Task 2: Provider Creation Form and Selection Recovery

**Interfaces:**
- `setupProviderCreation({api, roleSelect, setBusy, onCreated})` from providers.js wires the static form and returns `setBusy(value)`, `syncRole()`, `onProviderLoaded(id)`; export `providerLabel(provider, providers)` for unique duplicate-name labels.
- `onCreated(id)` in onboarding stores a preferred recovery ID, clears the previous provider's update draft/request ID, and calls `initialize(id)`. That function returns success/failure, clears the old snapshot before changing the selected option, loads dashboard/history atomically and keeps preferred ID on failure. Refresh data recovers that selection; successful load notifies the form.
- The form keeps one UUID until success/cancel/new form, including failed/lost save responses. POST body contains only id/name/type/start date. A known saved-but-unloaded result remains recoverable with an honest status; failed data loads show no mixed checklist or invented counts.

- [ ] **Step 1: Write browser RED cases.** Proposer sees no Add provider; Manager opens inline form with required fictional name, single Dentist label and optional empty start date. Preview five Outstanding/null-date rows. Cancel/blank name/partial date creates no provider. Add Dr. Avery Example, assert selected saved ID and 0/5/0/0 counts, old update text cleared and original checklist unchanged. Role switch hides form/creation controls.
- [ ] **Step 2: Add scope/persistence cases.** With another synthetic configured type, selecting it updates preview and creates only its own requirements. Duplicate names remain distinct selectable records. With providers deleted but templates retained, Manager can add the first provider. Missing templates gives a safe disabled creation state. Restart/reload preserves new records; analyze/approve for the new provider using TestModel and verify original provider/history unchanged (including proposed-start anchoring if inferred scenario used).
- [ ] **Step 3: Add recovery cases.** Lose a successful POST response, retry the same form and assert only one new provider. Fail each post-save read (provider list, dashboard, history), assert saved-operation wording and cleared/disabled snapshot, restore reads and Refresh data to select the new provider. No previous provider values may appear under the new name. Reused UUID edited payload must not overwrite an existing record. Verify keyboard access, safe name/template text and 390px layout/screenshots.
- [ ] **Step 4: Run browser RED.** `bash scripts/test.sh uv run pytest tests/e2e/test_provider_creation.py -v`; expected missing Add provider/form assertions.
- [ ] **Step 5: Implement form and selection wiring.** Use native controls and textContent; hide/disable conflicting controls according to role/busy, allow first-provider creation, support nonempty configured types, and preserve operation ID until deliberate new form. Do not expose a single-option type picker. Disambiguate duplicate names using type/start date and a uniquely extended short UUID reference only where needed.
- [ ] **Step 6: Verify browser behavior and docs.** Run focused new browser tests plus retained review/monitoring tests. Inspect desktop/narrow output and keyboard. Update README, proposal creation/role behavior and AGENTS module responsibilities, including safe recovery and synthetic-only use.
- [ ] **Step 7: Final checks and commit.** Node syntax checks for browser modules, Ruff, mypy, and complete disposable-DB pytest suite all pass without skips. Commit `feat: add manager provider creation and selection recovery`.

## Completion

- [ ] Self-check design/spec/constraints and complete diff for unintended production test switches or credentials.
- [ ] One fresh whole-branch read-only reviewer with all five Review Focus cases. Fix material findings with RED→GREEN regressions and full checks.
- [ ] Open PR citing Provider Types and Checklists/Human Review, maintain one code-verified diagram, push/watch CI and leave merging to the user.

## Execution Handoff

Native execution, preserving the user's established preference. Plan self-review found every design section covered, both tasks share the exact catalog/create contracts and saved selection ID, and no new migration/model/dependency is required.
