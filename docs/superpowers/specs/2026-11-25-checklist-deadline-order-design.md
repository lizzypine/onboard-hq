# Checklist deadline order

## Intent and scope

Show the earliest deadlines first when building a provider's checklist and when
viewing an existing provider, so staff can see time-sensitive requirements first.
This refines the centralized tracker and deadline monitoring described in
`docs/proposal.md` under **Up to Three Core Features**. The proposal is unchanged.

## Display rules

- Sort all requirements by deadline ascending, including past deadlines and
  finished requirements. Expected completion date and status do not affect order.
- Put requirements without a deadline after every dated requirement.
- Use alphabetical requirement names for equal deadlines and for undated items.
  This tie-breaker is an implementation choice that keeps both views consistent.
- Apply the same order to the wizard's Requirements preview, final Review table,
  frozen creation review, and the saved provider checklist in either simulated
  role, including archived providers.
- In the wizard, reorder after **Save requirement** updates the browser draft.
  For existing providers, use saved deadlines; typing in an editor does not move
  rows. A successful save and coherent refresh shows the new order.
- Keep inline editors, pending suggestions, and requirement question actions
  attached to their own requirement IDs. Preserve existing editor focus and
  review drafts when question actions arrive asynchronously.

## Approach and constraints

Use a shared browser ordering helper returning a sorted copy. Both the wizard
and saved checklist render through it. Refresh saved-row detail nodes by
requirement ID rather than positional correspondence with the original array.

An alternative is to order saved API responses in SQL and implement a separate
draft sort in the browser. Shared presentation ordering avoids duplicating this
display policy and keeps captured snapshots, retry identities, and stored
checklist membership independent of display order. No schema, database policy,
template, extraction, date inference, or status behavior changes are needed.

## Verification

Real-browser tests cover mixed standard/additional rows, equal and missing
deadlines, past deadlines, independent completion dates/statuses, draft edits,
final review, creation and reload, saved deadline edits and clearing, and delayed
question actions beside pending suggestions and an open editor. Use the guarded
disposable PostgreSQL test database and disabled real model requests. Run Ruff,
mypy, the full test suite, and pull-request CI.
