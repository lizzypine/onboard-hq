# Requirement history in the onboarding checklist

## Intent

Make each checklist requirement the entry point to its saved update and review
history. Clicking a name such as **Hawaii dental license** opens that item's
history. Remove section **4. Review history** after moving its saved evidence
into the checklist section. This supports the centralized tracker and reviewed
updates in `docs/proposal.md`, which remains unchanged.

## Approaches

- **Chosen: native history dialog.** Requirement names become accessible buttons
  that open a scrollable dialog without rearranging checklist rows. This suits
  longer original messages and before/after comparisons, and follows the app's
  existing native dialogs.
- **Alternative: expand history beneath each row.** It keeps history inline but
  makes the checklist much taller and competes with pending review controls.

The prototype continues to identify saved reviews and manual edits as
**simulated Manager**. It does not collect staff names or introduce sign-in.
The existing update records do not identify their submitter; do not invent one.

## Navigation and content

- Clicking a requirement name opens **Update history**, labeled with the provider
  and selected requirement. The dialog includes the item's current saved status,
  expected completion date, and deadline for context.
- Add **All update history** in section 2. It opens the same dialog for the
  selected provider, with an **All requirements** filter. The filter also lets
  users choose an exact assigned requirement. This broader view is an
  implementation proposal to preserve access to every original update.
- An item filter includes only suggestions and direct edits linked to that exact
  provider and requirement ID. When an update concerns several requirements,
  retain its original text as evidence but show only the selected item's
  suggestions and decisions.
- Show manual edits with their saved timestamp, simulated Manager attribution,
  and immutable before/after status, expected completion date, and deadline.
- Show approved, corrected, and rejected suggestions with their saved review
  timestamp, simulated Manager attribution, outcome, original update and
  submission time, proposed values, supporting text, date inference evidence,
  warnings, and before/after status and expected completion date. Rejections
  explicitly say that no checklist change was applied.
- Pending suggestions appear as read-only **Awaiting manager review** entries in
  history. Their editable approval/correction/rejection controls remain beneath
  the matching checklist row; opening history must not replace those drafts.
- The all-requirements view also retains updates with no suggestions, failed
  analysis, and unfinished analysis, including original text and warnings. Do
  not guess an item association for these records. Item history offers a way to
  switch to the broader view.
- Order activity newest first: decisions by `reviewed_at`, manual edits by
  `created_at`, and unreviewed suggestions or unassigned updates by the update's
  `created_at`. Use stable IDs and event kinds to resolve timestamp ties.
- Show a clear empty state when a selected requirement has no saved activity.
  Do not manufacture an initial change or an author for seeded/created rows.

## Interaction and implementation constraints

Use the existing coherently loaded provider, updates, and manual-edit records;
no schema migration, new attribution fields, or model calls are needed. Separate
history event selection and safe read-only rendering from checklist editing and
pending suggestion orchestration. Keep authorization and persistence unchanged.

History is available in either simulated role, including for archived providers.
Support keyboard activation, native dialog focus containment, Escape/Close,
focus return to the opener, and usable scrolling on narrow screens. Opening and
closing history preserves unsaved update text and checklist/review drafts.
Close the dialog when its provider context is cleared or changed. A coherent
same-provider refresh updates the open history without showing another item's
records or silently discarding its filter. Do not present incomplete reloads as
an empty saved history. History display performs no writes.

Remove the old section and disclosure wiring. Update status messages and tests
that currently direct users to section 4 so they use **All update history**.
Preserve deadline ordering, pending suggestion placement, retained evidence,
provider scoping, manual-save recovery, and existing question actions.

## Verification

Add tests for exact requirement/provider filtering, manual and reviewed changes,
late review timestamps, rejection without a saved change, multiple requirements
in one update, empty history, unmatched/failed/unfinished updates in the broader
view, safe text rendering, role/archive behavior, filter/refresh behavior,
keyboard and narrow-screen use, and draft preservation. Update existing browser
tests to use the new history entry points. All automated tests use disposable
PostgreSQL and disabled real model requests. Run Ruff, mypy, the full test suite,
code review, and pull-request CI before reporting completion.
