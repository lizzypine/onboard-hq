# Requirement History Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Open item-specific saved history from checklist names and move provider-wide history into section 2, removing section 4.

**Architecture:** Project read-only activity from the existing coherent provider/update/edit snapshot. A native dialog owns filtering and navigation; separate modules select events and render immutable evidence. Pending review controls remain in the checklist.

**Tech Stack:** Existing FastAPI, Pydantic, PostgreSQL, browser JavaScript/CSS, pytest and Playwright; no new dependencies.

**Spec:** `docs/superpowers/specs/2026-11-25-requirement-history-design.md`

## Global Constraints

- Keep `docs/proposal.md` unchanged. No schema migration, attribution collection, model gateway changes, or production data writes.
- Use **simulated Manager** for stored review/manual-edit attribution; do not invent an update submitter.
- Preserve immutable original evidence, role/archive guards, deadline ordering, retry identities, and existing drafts.
- History uses exact provider/requirement IDs and performs no writes. Pending entries in the dialog are read-only.
- Tests use disposable PostgreSQL and disabled real model requests. Run Ruff, mypy, full pytest and PR CI.

## Review Focus

1. Late review of an older update must sort by review time, not submission time.
2. Pending history must not duplicate editable review controls or destroy a draft.
3. Unmatched, failed and unfinished updates must remain accessible without guessed item associations.
4. Refresh failures must retain the last coherent history and selected filter.
5. Provider changes and same-named requirements must never show another provider's history.

## Task 1: Replace section 4 with requirement history

**Files:**
- Create `app/static/history-events.js`: pure `historyEvents(providerId, updates, edits, requirementId = null)` projection and stable newest-first ordering.
- Create `app/static/history-render.js`: safe shared original-update/suggestion evidence and read-only event rendering.
- Create `app/static/requirement-history.js` and `app/static/history.css`: native dialog, current values, exact filter, refresh/close/focus behavior; no HTTP or storage calls.
- Modify `app/page.py`, `app/static/onboarding.js`, `app/static/checklist.js`: dialog markup, coherent snapshot wiring, requirement-name buttons, removal of old disclosure/history rendering and updated messages.
- Modify `AGENTS.md`: describe the new browser responsibilities.
- Create `tests/e2e/test_requirement_history.py`; adapt existing history consumers in `tests/e2e/`.

**Interfaces:**
- `historyEvents(providerId, updates, edits, requirementId = null)` returns `{kind, id, at, record, update?}` entries; kinds are edit, suggestion, update. Record shapes remain existing API shapes.
- `setupRequirementHistory({dialog, trigger, onRefresh})` exposes `render(provider, updates, edits)`, `setBusy(value)`, and `open(requirementId, opener)`.
- `setupChecklist` receives `onHistory(requirement, opener)`; it owns name buttons but no history loading/rendering.
- `history-render.js` exports `renderUpdateEvidence`, `renderSuggestionEvidence`, and `renderHistoryEntry`; onboarding reuses evidence helpers for pending cards.

- [ ] Write new real-browser cases before implementation. Assert exact item/provider filtering, immutable manual/review before/after values and attribution, late-review ordering, multi-item evidence, rejection, read-only pending history, empty/all-update states, draft preservation, modal keyboard/narrow layout, provider reset and failed/successful refresh. Existing endpoints and test repository helpers create real saved records.
- [ ] Run `bash scripts/test.sh uv run pytest tests/e2e/test_requirement_history.py -q`; expect failure because requirement-name/history buttons do not yet exist.
- [ ] Implement the interfaces above. Use existing IDs and timestamps, sorted copies, safe DOM text, native dialog focus handling, and an explicit Refresh history action calling the controller's coherent snapshot loader.
- [ ] Adapt existing browser tests to open/close history only when inspecting saved evidence; pending review actions continue using checklist cards. Replace disclosure state assertions with dialog visibility, retained filter, and provider-context assertions.
- [ ] Run focused history and existing history-consumer browser cases; expect all passing. Inspect desktop and narrow screenshots.
- [ ] Run `uv run ruff check`, `uv run mypy`, and `bash scripts/test.sh uv run pytest`; expect no lint/type errors and a green full suite.
- [ ] Request one fresh whole-branch review against the spec and Review Focus. Address material findings with regression tests; rerun relevant/full checks as required.
- [ ] Commit the verified change on its feature branch, publish a PR with Summary, one code-verified Mermaid change diagram and checked Test plan, then watch CI. Never merge it.
