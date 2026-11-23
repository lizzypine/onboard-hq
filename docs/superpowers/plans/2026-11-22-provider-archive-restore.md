# Provider Archive and Restore Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Managers can archive and restore the selected provider without losing or resetting their checklist or history.

**Architecture:** Reuse `providers.archived_at`, existing Active/Archived lists, and archived write guards. Serialize lifecycle changes with the existing provider row lock. Add a small browser controller for inline actions and reconcile unconfirmed responses by reading current state without replaying a write.

**Tech Stack:** Existing FastAPI, Pydantic, raw PostgreSQL, native JavaScript, pytest and Playwright.

**Spec:** `docs/database-design.md`, “Archive, restoration, and permanent deletion”; direct user instruction to implement inline Archive/Restore and skip further design review. Permanent deletion remains deferred.

## Global Constraints

- Manager mode is simulated and enforced on the server; default Proposer cannot archive or restore.
- Only synthetic provider records and administrative updates are permitted.
- Archiving preserves the assigned template, standard and additional rows, statuses, dates, deadlines, versions, original updates, suggestions, decisions, and manual history.
- Restore clears only archived_at; it does not reinitialize a checklist or use a newer template.
- No schema migration, new columns/tables, model calls, archive-event history, deletion controls, or changes to docs/proposal.md.
- Automated tests use disposable PostgreSQL and TestModel with real requests disabled; never Neon.
- Work on a feature branch in the existing checkout, per the user's established preference. Open a non-draft PR, watch checks, and never merge it.

## Review Focus

- A repeated archive request must retain its original archive timestamp; repeated restore must leave progress unchanged. Pin in API tests.
- An archive that waits for the provider lock must not interleave with checklist edits; pin actual lock blocking and post-archive edit refusal.
- A lost response must be reconciled with a GET, with no automatic second POST; pin browser request counts and actual state.
- A failed post-save refresh must clear stale editable data and permit Refresh data recovery; pin browser controls and saved values.
- Switching between empty Active/Archived lists must remain possible and give accurate empty-state text; pin browser list transitions.

## Builder choices

- Put Archive provider / Restore provider beside Refresh data in Select a provider, visible only for Manager and the matching selected state.
- Confirm archive with a native browser confirmation naming the provider, explaining preservation and restoration, and warning that unsaved changes are discarded. Restore is a direct reversible action.
- On success switch to Archived after archive, or Active after restore, keep that provider selected, clear unsent update/editor drafts, and load its saved checklist/history coherently. Restore useful keyboard focus.
- Use explicit desired-state endpoints, never a toggle: POST /providers/{id}/archive and POST /providers/{id}/restore. Return StoredProvider, 403 for Proposer, 404 for missing records, 422 for invalid paths/roles, and safe 503 for database failures.
- Archive uses COALESCE(archived_at, now()); restore sets NULL. The same provider lock used by existing writes establishes ordering. Previously claimed analysis may finish storing its evidence after archive; new submissions and checklist/review changes remain blocked.
- On an unconfirmed write, read the provider and load the actual state. Never automatically replay the action. If reconciliation fails, clear the stale snapshot and show Refresh data recovery.

### Task 1: Complete inline Archive/Restore slice

**Files:**
- Create `app/provider_lifecycle.py`: authorization and lifecycle orchestration, no HTTP/model code.
- Create `app/repository/provider_lifecycle.py`: locked archived_at-only transaction.
- Modify `app/rules/provider_state.py`: pure Manager authorization alongside existing archived write guard.
- Modify `app/main.py`: route wiring and safe error mapping only.
- Create `app/static/provider-lifecycle.js`: action visibility, confirmation, POST, reconciliation, status and focus handling.
- Modify `app/page.py` and `app/static/onboarding.js`: inline controls, coherent selection/reload callbacks, role/busy state, accurate empty-list text, cache version.
- Modify `AGENTS.md`, `README.md`, `docs/database-design.md`: implemented scope and module ownership; retain deferred Delete/sign-in.
- Add `tests/test_provider_lifecycle.py`, `tests/test_provider_lifecycle_races.py`, `tests/e2e/test_provider_lifecycle.py`.

**Interfaces:**
- Consumes `lock_provider(conn, provider_id)`, `fetch_provider(conn, provider_id)`, `require_active(provider)`, and existing coherent `initialize(id)`/`clearSnapshot()` browser operations.
- Produces `ProviderLifecycleRepository.set_archived(provider_id: int, archived: bool) -> StoredProvider`, `change_archive_state(repository, provider_id, archived, role) -> StoredProvider`, and `setupProviderLifecycle({api, roleSelect, setBusy, onChanged, onUnavailable})` with `render(provider)`, `setBusy(value)`, and `syncRole()`.

- [ ] Write unit/API tests for Manager/default/invalid role, missing/invalid IDs, repeated/concurrent desired states, archived read/write behavior, and exact graph/template/additional-row/history preservation after restore. Test missing configuration/schema safely.
- [ ] Write an observed PostgreSQL provider-lock race test and browser tests for archive confirmation/cancel, restore and restart, original progress, role visibility, last-provider list transitions, double click, lost responses, failed refresh, and recovery without duplicate writes.
- [ ] Run new tests before implementation. Expected: missing rules/endpoints/buttons fail; record RED evidence.
- [ ] Implement pure authorization, transaction, orchestration and routes. Expected: targeted unit/PostgreSQL tests pass with no schema changes.
- [ ] Implement the controller and page wiring. Expected: browser tests pass, saved checklist/history remains unchanged, and uncertainty disables stale writes.
- [ ] Update only affected documentation and agent layout. Run Ruff, mypy, JavaScript syntax, git diff --check, and `bash scripts/test.sh uv run pytest --tb=short -q`. Expected: all checks pass.
- [ ] Commit the working slice, obtain one independent whole-branch review, grade findings, and fix important findings with RED→GREEN regression tests and a green complete suite. Defer minor polish; do not request a second review.
- [ ] Open a non-draft PR with Summary citing the original proposal and subsequent lifecycle section, Test plan, and one code-verified Mermaid diagram. Run `gh pr checks --watch`; report final results. Keep merging with the user.
