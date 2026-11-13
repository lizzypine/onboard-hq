# Checklist-Style Manager Review Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let managers compare and edit each proposed change in a highlighted checklist-style row before independently approving or rejecting it.

**Architecture:** Keep the saved checklist and review API unchanged. Move the manager editor into a focused browser module that renders one requirement row and derives preserve/set/clear date actions from direct field edits. Existing onboarding orchestration supplies the saved requirement, suggestion, busy state, and decision callback.

**Tech Stack:** Existing FastAPI page shell, native JavaScript modules, pytest/Playwright, disposable PostgreSQL, and deterministic TestModel. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-11-12-checklist-review-editor-design.md`, approved by the user; canonical `docs/proposal.md` Human Review and date/monitoring rules.

## Global Constraints

- The affected row stays inside each suggestion; the saved checklist changes only after approval.
- Only Status and Requirement date are editable. Requirement name and Deadline stay read-only. No draft monitoring/readiness calculation.
- Retain original updates, supporting text, model proposals, date wording/inference, warnings, role enforcement, stale checks, and saved-operation retry behavior.
- Highlight actual differences from the saved requirement, with text as well as color. Manager corrections remain identifiable against the original proposal.
- Preserve all existing server review contracts and business rules, including inferred-date confirmation reset after edits.
- Tests use TestModel with real requests disabled and disposable loopback PostgreSQL; no Neon writes or live model requests.
- Work natively on the existing feature branch in this checkout, preserving the user's established execution preference. The approved design authorizes implementation; do not request the same authorization again.

## Review Focus

1. No proposed date with an existing saved date must preserve that saved date on unedited approval.
2. Reverting a proposed status to its saved value removes change highlighting but still records a correction to the original proposal.
3. An emptied date means clear; an invalid partially entered date must not silently clear a date or enable approval.
4. Editing or clearing an inferred date resets confirmation; rejection must remain available even when approval is invalid or stale.
5. Editing one suggestion must never mutate the saved checklist, monitoring counts, original proposal, or another suggestion's decision.

## Files and Responsibilities

- `app/static/review.js` (new): comparison cells, draft input validation, date action derivation, and decision callbacks for one manager editor.
- `app/static/onboarding.js`: provider/history orchestration and display; imports the editor, removing its old form implementation.
- `app/page.py`: load the browser entry point as a module and style accessible comparison tables/highlights.
- `tests/e2e/test_checklist_review.py` (new): real-browser comparison and direct-edit regressions.
- `tests/e2e/test_review_workflow.py`: adapt the existing explicit-date-clear case to direct input; retain all other workflow assertions.
- `docs/proposal.md`, `README.md`, `AGENTS.md`: approved Human Review behavior, usage, and actual module responsibilities.

### Task 1: Editable Comparison Row and Browser Regression Coverage

**Interfaces:**
- `renderReviewControls(card, suggestion, current, {busy, onDecide})` exported from `app/static/review.js`. `card` is the suggestion element; suggestion/current are unchanged saved JSON records (current may be missing for a stale suggestion); `onDecide(suggestion, body)` is the existing asynchronous decision function.
- Preserve accessible names `Reviewed status`, `Reviewed date`, `Confirm inferred date`, and all three decision buttons. Add a table named `Review <requirement>` with Requirement, Status, Requirement date, Deadline headers. Give comparison cells `data-review-field="status"` / `"date"` and a `review-change` class only when the reviewed value differs from the saved value.
- Untouched effective date => omit date_action (preserve); changed nonempty date => `date_action: "set", corrected_date: value`; changed empty date => `date_action: "clear"`. Compute approval-versus-correction from differences against the original proposed status/effective initial date, separately from change highlighting against saved values.

- [ ] **Step 1: Write failing browser cases.** Add `test_review_row_highlights_proposed_status_and_keeps_evidence`: assert the four headers, Saved: Scheduled, editable Completed, Originally proposed: Completed, highlighted status/unhighlighted empty date, read-only requirement/deadline, and unchanged saved Scheduled/counts while editing. Add `test_return_to_saved_status_is_a_correction_without_highlight`: set Reviewed status to Scheduled, assert no status highlight, Approve disabled/Approve with corrections enabled, approve, and assert original Completed evidence plus corrected Scheduled history.
- [ ] **Step 2: Add date regressions.** `test_no_date_proposed_preserves_saved_date` seeds drug date `2026-11-20`, deadline `2026-11-30`, verifies prefilled unhighlighted date, approves unedited, and checks both dates remain. `test_date_edits_set_clear_and_restore_comparison` checks Nov 29 highlights and produces a corrected approval; a separate parameter case clears a saved Nov 20 date and verifies Not set while Nov 30 deadline survives. Returning the input to Nov 20 before approval removes the highlight and permits unedited approval. Retain inferred-date confirmation/reset coverage and add clearing an inferred date: approval disabled, Reject enabled, saved date unchanged after rejection.
- [ ] **Step 3: Add safety/layout checks.** In Proposer mode no editor appears. For Manager, saved HTML-like status remains literal text; no injected DOM/script executes. At 390px the document does not overflow, the manager table scrolls internally, and native tab order reaches editable fields and decision buttons. Retain existing stale, multiple-suggestion, restart, lost-response and failed-refresh regressions. Adapt the old Date change select test to empty Reviewed date directly.
- [ ] **Step 4: Run browser RED.** `bash scripts/test.sh uv run pytest tests/e2e/test_checklist_review.py -v`. Expected: missing comparison table/highlight assertions fail against the old editor. Save the output in this plan's ignored workspace.
- [ ] **Step 5: Implement the browser module and page styles.** Extract the editor responsibility to `review.js`; render saved values, editable fields, comparison labels, and original proposals using textContent. Keep current version/stale validation and independent callbacks. Preserve fields disabled while busy. Validate date.checkValidity even for empty inputs and require a nonempty confirmed inferred date. Render a table with internal scrolling and text-labeled changed cells. Remove the Date change dropdown and old review-grid form; retain read-only proposed fields in Proposer/completed history, avoiding duplicate proposed paragraphs in an active Manager editor.
- [ ] **Step 6: Run browser GREEN.** `bash scripts/test.sh uv run pytest tests/e2e/test_checklist_review.py tests/e2e/test_review_workflow.py tests/e2e/test_monitoring.py -v`. Expected: all focused and retained scenarios pass. Inspect desktop/narrow screenshots saved under pytest temp paths. If a browser limitation prevents entering a partial date deterministically, document it and retain native checkValidity plus inferred-empty and explicit-clear coverage.
- [ ] **Step 7: Synchronize documentation.** Update proposal Human Review with the approved row, highlighted current/proposed comparison, direct date editing, read-only Deadline and inferred confirmation. Describe the UI in README and list the new browser module in AGENTS.md. No schema/model/server changes.
- [ ] **Step 8: Verify and commit.** Run `node --check app/static/onboarding.js`, `node --check app/static/review.js`, `uv run ruff check`, `uv run mypy`, and `bash scripts/test.sh uv run pytest`. Expected: all pass, no skips or ignored checks. Commit `feat: review suggested changes in editable checklist rows`.

## Completion

- [ ] Self-check every approved design requirement against the diff.
- [ ] One fresh whole-branch read-only reviewer, including the five Review Focus cases; resolve material findings with regression coverage.
- [ ] Open a PR citing proposal Human Review, maintain one code-verified Mermaid diagram via pr-diagram, push/watch CI, and leave merging to the user.

## Execution Handoff

Execute natively under the user's preserved method and approved design. Plan self-review: one task owns all browser interfaces, every design constraint maps to its tests or implementation step, and server/storage contracts remain unchanged.
