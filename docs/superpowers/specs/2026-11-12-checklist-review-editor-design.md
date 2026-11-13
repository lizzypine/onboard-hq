# Checklist-Style Manager Review

## Intent and Scope

Make proposed checklist changes easy to compare and correct. Replace the separate
manager status/date form with an editable checklist-style row inside each pending
suggestion. The user selected this placement; the main saved checklist remains
authoritative and changes only after approval.

The canonical proposal's **Human Review**, **Data Use > Incomplete Dates**, and
**Status and Deadline Monitoring** sections govern approval, evidence, and dates.
This is a small browser presentation change using the existing review API.

## Approaches

- **Affected row inside each suggestion — selected by the user.** Keeps the draft
  beside its original update and supporting text, and retains independent review.
- **Editable proposals in the main checklist — considered.** Adds navigation and
  draft-state complexity when several saved updates affect the same requirement.

## Proposed Interaction

- Use the checklist's Requirement, Status, Requirement date, and Deadline columns.
  Display only the affected requirement in the manager's review row.
- Status and Requirement date are editable. Requirement name and Deadline are
  read-only. Do not introduce a deadline editor or an editable monitoring result.
- Prepopulate Status with the model's proposed status. Prepopulate Requirement date
  with the proposed date, or the current saved date when no date was proposed.
- Show the saved values and retain the original proposed values as read-only
  evidence. Highlight cells whose reviewed values differ from the current saved
  values. Pair the highlight with text identifying a proposed change or manager
  correction; do not depend on color alone. Update the comparison while editing.
- Replace the Date change dropdown with direct date editing. An untouched field
  preserves the proposed/current date. A changed nonempty field sets that date;
  clearing it explicitly removes the date. Show a clear-date explanation where
  relevant. Keep the existing server review contract and date validation.
- Preserve Approve, Approve with corrections, and Reject as independent decisions
  for each suggestion. Enable the appropriate approval action based on edits.
- Keep inferred-date confirmation and reset it after a date edit. An inferred-date
  suggestion cannot be approved with a missing or unconfirmed date.
- Preserve original updates, supporting text, date wording/inference, warnings,
  completed decisions, stale-version behavior, role enforcement, and retry IDs.
- The saved Monitoring column and counts refresh only after the existing saved
  review workflow succeeds; this draft row makes no monitoring/readiness claim.
- Keep the row readable and keyboard-operable, with internal table scrolling on
  narrow screens. Keep Proposer mode read-only with no manager decision controls.

## Implementation and Verification

Use `app/page.py` and `app/static/onboarding.js`, splitting browser responsibilities
only if the review renderer becomes too large. No schema, model, repository,
authorization, or review-rule changes are expected. Update **Human Review** in
`docs/proposal.md` with the approved presentation and direct-date-editing behavior.

Use real-browser tests with the existing deterministic TestModel and disposable
PostgreSQL to cover highlighted status/date changes, direct corrections and date
clearing, inferred confirmation reset, independent decisions, stale suggestions,
safe text rendering, narrow layout, role switching, and unchanged saved values
until approval. Retain existing unit/integration coverage and run Ruff, mypy,
JavaScript syntax checks, and the full suite locally and in CI.
