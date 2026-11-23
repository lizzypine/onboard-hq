# Inline Checklist Suggestions Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Display each pending suggestion beneath its saved checklist requirement,
retain completed decisions in Review history, and label the basic role Non-manager.

**Architecture:** The saved-view controller builds pending suggestion DOM grouped
by requirement and renders terminal history separately. The checklist accepts a
callback returning those existing DOM nodes, so local manual-editor redraws retain
review drafts without adding loading or review calls to the checklist module.

**Tech Stack:** Existing native HTML/CSS/JavaScript, FastAPI, pytest/Playwright,
TestModel, and disposable PostgreSQL.

**Spec:** `docs/superpowers/specs/2026-11-22-inline-checklist-suggestions-design.md`

## Global Constraints

- Original proposal, database schema, API, model, dates, and permissions stay unchanged.
- Only an authorized save changes saved checklist values and monitoring.
- Pending proposals retain original updates, evidence, warnings, and independent decisions.
- Keep `proposer` as the internal role value; show **Non-manager**.
- Preserve disclosure state, provider isolation, manual draft recovery, safe text,
  keyboard access, and contained narrow-screen scrolling.

## Review Focus

- Multiple updates for one requirement retain separate proposals in newest-first order.
- Opening/canceling a manual editor retains an unsaved suggestion correction.
- Manual saves make conflicting proposals stale while permitting rejection.
- Provider/role changes redraw the correct proposals with appropriate permissions.
- Decisions transfer cards into collapsed history without leaving duplicate cards.

### Task 1: Place proposals under saved requirements and separate history

**Files:** Modify `app/page.py`, `app/static/onboarding.js`,
`app/static/checklist.js`, `tests/e2e/test_review_workflow.py`,
`tests/e2e/test_checklist_edits.py`, and related affected browser selectors;
create `tests/e2e/test_inline_suggestions.py`; update `README.md` and `AGENTS.md`.

**Interfaces:**
- Consumes existing dashboard, update/decision, checklist edit, and review APIs.
- Produces optional `requirementDetails(requirement)` callback in `setupChecklist`:
  returns an existing DOM node or null; the checklist places it below the saved row.
  The saved-view controller supplies nodes and owns review orchestration.

- [ ] Add browser tests for pending placement, unchanged saved values, evidence,
  terminal history placement, label/count changes, repeated proposals, manual
  redraw draft retention, provider scoping, warnings, and narrow layout.
- [ ] Run `bash scripts/test.sh uv run pytest tests/e2e/test_inline_suggestions.py -x`;
  expect a placement assertion failure before implementation.
- [ ] Implement grouped pending DOM, checklist detail slots, separate terminal
  cards, pending count relocation, role copy, and analysis success copy. Update
  browser helpers to target saved rows and explicitly open terminal history.
- [ ] Update README usage and AGENTS module responsibilities/visible role guidance.
- [ ] Run Ruff, mypy, changed JavaScript syntax checks, and
  `bash scripts/test.sh uv run pytest`; expect all checks and tests to pass.
- [ ] Review the whole branch with a fresh reviewer, resolve material findings,
  commit on the feature branch, create the PR with the required diagram and
  proposal citation, and watch all CI checks. Leave merging to the user.
