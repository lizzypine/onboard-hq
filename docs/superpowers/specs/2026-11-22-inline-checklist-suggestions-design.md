# Pending Suggestions in the Onboarding Checklist

## Intent and Scope

Show pending suggestions directly beneath their matching saved checklist
requirement so users can review an update where they inspect onboarding progress.
Rename section 4 to **Review history** and the simulated role's visible
**Proposer** option to **Non-manager**. This presentation change follows
`docs/proposal.md`'s Human Review and Status and Deadline Monitoring requirements;
the proposal remains unchanged.

## Approaches

- **Under each matching requirement — selected by the user.** Keeps each proposal
  beside its saved row, including when several updates propose changes to the
  same requirement. Requires coordinating suggestion placement with checklist
  redraws and manual editors.
- **One panel below the checklist table — considered.** Reuses the existing
  grouped presentation more directly but separates proposals from affected rows.

## Interaction and Constraints

- Insert a clearly labeled pending-suggestion area beneath each affected
  requirement. Show separate proposals newest first; never combine or silently
  discard competing suggestions for the same requirement.
- Keep original update text, submission time, supporting text, date wording and
  inference, and update warnings available with each proposal. Both roles can
  view pending suggestions; only Managers see existing review controls. Archived
  providers remain viewable with write controls disabled.
- Retain independent Approve, Approve with corrections, and Reject actions,
  inferred-date confirmation, and stale-version checks. Saved status, dates,
  monitoring, and counts change only after a successful authorized save.
- After a decision and coherent reload, remove that pending proposal from the
  checklist and show its immutable evidence and result in Review history.
  Pending proposals must not also appear as reviewable cards in Review history.
- Keep saved updates, processing/failure notices, warnings, completed decisions,
  and manual checklist edits in Review history. Updates with no completed
  decisions can state that pending suggestions are in the checklist without
  duplicating their cards. Preserve the native disclosure's current default and
  user toggle behavior.
- Move the pending-suggestion count into the checklist section and direct the
  successful analysis message there. Keep it distinct from monitoring's Needs
  review count.
- Show **Non-manager** in the simulated role selector. Preserve the internal
  `proposer` value and existing API permissions; this is a display-label change.
- Preserve manual edit drafts and save recovery while rows redraw. Keep provider
  switching coherent and evidence safely rendered as text. Contain scrolling
  within the checklist on narrow screens and preserve keyboard access.

## Implementation Boundaries and Verification

Use the existing page, checklist renderer, and suggestion review controls, with
an orchestration callback or focused presentation module as needed. No database,
model, extraction, date-resolution, API, or authorization changes are required.
Update agent layout guidance only if module responsibilities change.

Use deterministic TestModel browser tests and disposable local PostgreSQL to
verify placement, repeated proposals for one requirement, independent decisions,
history transfer, evidence/warnings, role labels and permissions, provider
switching, stale reviews after manual saves, refresh/restart persistence,
keyboard operation, and narrow layout. Run Ruff, mypy, JavaScript syntax checks,
and the full existing pytest suite; open a PR and watch CI without merging.
