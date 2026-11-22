# Add Provider Walkthrough and Provider-Only Requirements

## Intent and authority

Replace the inline creation form with the approved five-step modal. A Manager can
review a standard checklist, save additional requirements into the modal's draft,
and review everything before saving one provider and their entire checklist.

This is a target design, not implemented functionality. It extends the original
proposal's **Data Use > Provider Types and Checklists**, **Human Review**, and
**Saved Records** through a scoped design, keeping `docs/proposal.md` unchanged.
The database target is also recorded under **Provider creation walkthrough target**
in `docs/database-design.md`. For this feature, this design replaces the older
provider-creation design's inline form, single-type text display, latest-template
fallback, and exclusion of creation-time checklist additions. The implemented
integer resource IDs and distinct UUID retry keys remain authoritative.

Only fictional providers and synthetic administrative updates are permitted. The
existing role switch is simulated; server enforcement of Manager mode is required
but is not authentication. Managed sign-in remains future work.

## Approaches

- **Extend the existing checklist system — selected by the user.** Store standard
  and provider-only requirements together, preserving their origin. Both use the
  existing monitoring, manual editing, update analysis, suggestion review, and
  history operations. Save the provider and all rows in one transaction.
- **Use a separate system for additional requirements — considered.** A separate
  checklist/table flow would require parallel analysis, editing, monitoring, and
  history handling. It would split the combined list approved in the preview.

The user approved the first approach. Author choices below settle engineering
details needed for reliable creation; they are not additional user requests.

## Approved presentation

The green **+ Add provider** button stays at the top right of **Select a provider**.
It opens a native modal dialog with a heading, five labeled progress steps, Back,
Cancel, and a primary forward action. The final saving button reads **Add provider**
without a plus sign. Preserve the existing dashboard outside the modal; this
feature does not replace its other sections with the preview's sample dashboard.

1. **Provider name:** required, nonblank fictional display name. Duplicates remain
   allowed; identity is the generated integer ID.
2. **Provider type:** required dropdown of configured types, even when only one
   type is available. Always offer an explicit selection prompt. Fetch the actual
   catalog; do not invent new provider types or fixture requirements.
3. **Proposed start date:** optional explicit calendar date, initially blank, with
   Skip for now. No inferred date or today fallback.
4. **Requirements:** show the selected type's standard requirements in a striped
   table, followed by saved additional rows in the same table. Include counts and
   clearly label additions **Additional · this provider only**. Standard rows are
   read-only here and start Outstanding with both dates unset. They can be edited
   after creation through the existing Manager edit operation.
5. **Review:** show the provider details and complete combined checklist exactly
   as they will be submitted. Provide Edit links for name, type, start date, and
   checklist, returning to Review after editing. Only the final Add provider action
   submits a creation request.

Preserve the approved modal's green accents, clear row dividers, status badges,
scrollable body, and persistent navigation footer. On narrow screens the dialog
fits the viewport and tables scroll horizontally inside their own regions.
Match the existing app's accessible typography and status colors; color always
has a text equivalent. The preview is a visual reference, not production code to
copy wholesale or a new frontend framework.

## Saving one additional requirement at a time

**+ Add requirement** opens one editor with:

- **Requirement name:** required; trim surrounding spaces. Names must differ from
  standard rows and other saved additions after the catalog's existing
  `lower(btrim(name))` normalization. Enforce this on the server as well as in the
  browser. Reuse an existing shared definition when a matching name already
  exists; otherwise create a definition atomically. Do not rename a shared label.
- **Status:** required native dropdown. A new custom requirement offers
  Outstanding, Pending, Scheduled, Incomplete, Completed, initially Outstanding.
  If that provider type and name already have a configured vocabulary, reuse it.
- **Expected completion date:** optional explicit date.
- **Deadline:** optional explicit date.

**Save requirement** validates the editor, trims the name, closes the editor, and
adds the row to the combined draft checklist. Only then can the Manager add another
requirement. A new editor starts blank with Outstanding and unset dates. Neither
this button nor step navigation sends a write request or calls a model.

Saved additional rows have Edit and Remove actions. Editing works on a copy;
Save requirement replaces the draft row and Cancel requirement leaves its saved
draft values unchanged. A pending editor blocks Review until it is saved or
canceled. Back retains the editor when returning to Requirements. Draft Remove
does not delete a database row because creation has not happened yet.

Author choices: changing provider type retains additions, loads that type's
standard checklist, and revalidates names and statuses. Any duplicate or now-invalid
status must be resolved before Review or final submission; do not discard or
silently rewrite an addition. Cancel/close before submission discards the entire
unsent provider draft; reopening starts fresh. No extra confirmation is required
for unsent draft cancellation.

## Date wording and accessible help

Use **Expected completion date** throughout the visible app: creation, saved
checklist, direct editor, suggestion comparison, and history labels. This names
the existing `scheduled_date` value; it adds no date column, backfill, or conversion
of previously saved values. Keep API/SQL field names and inference rules unchanged.

A small **?** beside the field label or column heading explains:

> When this item is expected to be completed—for example, the scheduled drug
> screening date. The deadline is the latest date it must be completed.

The explanation opens on hover, keyboard focus, and tap/click. Provide an
accessible button name and description, Escape dismissal, outside-click dismissal,
and a second-tap close. Keep help available long enough to read, within the viewport,
and within the modal's accessibility scope while the dialog is open. Dismissing
help with Escape must not also close the dialog. Do not rely on a native title
attribute alone. Label inputs independently of the help control.

Both dates may be unset, including for Scheduled. Do not introduce an ordering
constraint between them: a planned completion after a deadline must remain visible
rather than being silently corrected. Existing explicit/incomplete-date rules,
Manager approval, and date confirmation remain in force for extracted suggestions.

## Creation contract and concurrency

Extend the validated creation request with the reviewed checklist template ID,
a server-issued membership fingerprint, and a list of additional requirement
inputs (name, status, scheduled_date, deadline). Empty additions are valid. The
catalog response supplies the template identity/fingerprint, names, and authoritative
status vocabulary metadata needed by the browser. Exact DTO names are builder
choices. Reject invalid dates, blank/duplicate names, unsupported initial statuses,
extra fields, and inconsistent type/template pairs on the server.

Author choice: pin the final save to the checklist actually reviewed. Under the
existing provider-type and template-header locks, compare both the latest template
ID and its membership fingerprint. The fingerprint covers sorted normalized
membership and template/type identity; it requires no persisted fingerprint column.
If either changed, return a conflict with no new provider or definitions. Retain
profile/addition drafts, reload the catalog, show the changed standard list, and
require another Review. Never silently substitute a new checklist at final save.

For a new attempt, one transaction validates and locks the catalog, resolves any
additional definitions, inserts the provider, and inserts all standard/additional
rows. Every row starts at version 0. Standard rows use Outstanding and null dates;
additional rows use the explicitly reviewed values. A failure rolls back the
provider, checklist, and any newly created definitions together. Do not fabricate
an update, suggestion, review decision, or manual-edit event for initialization.
No creation operation calls the model. All later changes use the existing flows.

Keep one UUID retry identity for the final submitted payload. Freeze that payload
while saving or recovering; double-clicks and retries cannot change it. Check for
an existing creation under the retry lock before checking the current catalog or
initial-status rules, so later catalog/progress/archive changes do not break a
legitimate retry. Compare the original profile/template and the set of normalized
additional names with their immutable initial status/date/deadline values, ignoring
addition ordering. Conflicting reused identities fail; identical retries return
the existing provider without resetting any progress.

Author choice: retain an unresolved submitted attempt in sessionStorage, scoped to
this app/tab, so closing/reopening the modal or reloading can recover the same UUID
and frozen payload. Validate recovered payloads; never retry automatically or save
under a newly selected Proposer role. While recovery is unresolved, expose Retry
save and preserve the attempt rather than offering another save identity. Ordinary
unsent field drafts need not survive reload. Clear the recovery record only after
an authoritative no-commit result or a coherent saved provider view is loaded.

If the save response is lost, say the outcome is unconfirmed and retry the same
attempt. If saving is confirmed but dashboard loading fails, say saved and offer
reload recovery, without another creation. On success select the new provider,
load its dashboard and empty update history coherently, clear prior update-entry
state, close the modal, and restore useful focus. Do not mix the previous provider's
checklist/history with the new provider. Retain existing duplicate-name labels,
first-provider creation, and active/archived viewing behavior.

## Database target

Use one forward-only dbmate migration; do not modify an already applied migration.
There are still twelve application tables and no list/JSON receipt column.

- Make `requirements.checklist_template_id` nullable. Non-null identifies a
  standard row; null identifies a provider-only addition. Do not add a redundant
  origin flag. The provider itself still requires its assigned checklist version.
- Keep both existing composite foreign keys. Non-null standard rows must match
  their provider's assigned version (`ON DELETE CASCADE`) and an actual template
  membership (`ON DELETE RESTRICT`).
- Add `requirements.provider_id REFERENCES providers(id) ON DELETE CASCADE` and
  `requirement_definition_id REFERENCES requirement_definitions(id) ON DELETE
  RESTRICT` as direct foreign keys. These protect additions when null template IDs
  exempt them from composite matching. Preserve existing indexes and the unique
  `(provider_id, requirement_definition_id)` constraint; the provider-leading
  unique index and definition index support both direct relationships.
- Add nullable `initial_status text`, `initial_scheduled_date date`, and
  `initial_deadline date` to requirements. A CHECK requires additional rows to have
  a nonblank initial_status; their two initial dates are optional. Standard rows
  must have all three initial columns null. Extend the ownership trigger to keep
  these values, definition/provider identity, and template origin immutable.
- Initial values are the normalized creation receipt for additional rows. Later
  edits/reviews change only current status/date/deadline/version. Existing standard
  rows and all stored history are preserved, with the new columns null.

Propagate nullable template provenance through stored/captured Pydantic models,
queries, and snapshot reconstruction. The immutable row origin is available to
monitoring and edit rules; existing snapshot rows still capture mutable values
relationally. Do not expose initial receipt fields as editable API inputs or UI
fields. Provider deletion cascades through its additions and history, preserving
shared definitions. No individual live requirement deletion is added.

## Shared workflow behavior

Additional requirements are in the selected provider's actual saved context before
interpreting updates. An update can propose changes only to rows already in that
provider's checklist; it still cannot create new requirements or touch another
provider. Each suggestion retains original evidence and independent Manager review.
Use existing ownership checks, stale versions, atomic decisions, and immutable
manual-edit history for additional rows too.

For configured provider/name mappings, preserve existing completion semantics and
status choices. Otherwise, provider-only additions use the agreed generic
vocabulary: Completed means finished; Outstanding/Pending/Scheduled/Incomplete
mean unfinished. This fallback depends on explicit additional-row provenance, not
just an unfamiliar name. Unknown standard requirements/types keep Needs review.
Unknown later saved/model-proposed values remain verbatim and Needs review rather
than becoming an invented completion rule. Direct editors preserve the current
unfamiliar value; review controls preserve original proposed wording as today.
Use the same authoritative vocabulary for creation, saved editing, and review.

Deadline monitoring remains based on the Hawaii calendar date and saved deadline,
independently of expected completion date. Completed additions are not overdue;
unfinished additions with a past deadline are. Archived providers remain viewable
and block writes; an identical creation retry may return an archived saved result.

## Scope and builder choices

No template editor, profile editing, addition/removal of requirements after
creation, new provider-type fixtures, managed authentication, reminders, uploads,
multi-provider extraction, model routing, or deadline inference is included.
This does not apply any migration or write sample rows to Neon. Live rollout
requires separate authorization after the reviewed implementation and tests.

Keep the existing FastAPI/Pydantic/raw-SQL/dbmate stack. Routes only wire operations
and map errors. Split modal/draft/recovery browser responsibilities as needed;
keep status vocabulary and creation validation in shared Python rules. Exact
module names, digest encoding, DOM IDs, safe error text, and deterministic row
ordering are builder choices. Resolve definition insertions in a deterministic
normalized-name order across types/creation and catalog helpers to avoid deadlocks.
Keep seed behavior repeatable and independent of app startup. Update affected
agent layout guidance with implementation responsibility changes.

## Acceptance and verification

- Unit tests: contracts, name/status validation, configured versus generic
  provenance-aware choices/completion, role enforcement, template comparison,
  retry equality, and existing date/monitoring rules.
- Isolated PostgreSQL tests: upgrade preserves existing rows/evidence; nullable
  origin and receipt CHECKs; direct/composite foreign keys and deletes; receipt
  immutability; exact standard copying plus custom initial values; atomic rollback;
  canonical definition reuse; concurrent additions and same-key retries; reordered
  equal retries; conflicting retries; later progress/archive/catalog changes;
  preview-versus-save template races; scope, snapshot, manual edit, and approved
  suggestion behavior for additions.
- Real-browser tests: all five steps; optional start date; one-type dropdown;
  per-requirement save/edit/cancel/remove; combined list and full review; invalid and
  duplicate inputs; back navigation and type-change revalidation; no writes before
  final Add provider; keyboard focus/close/help and mobile scrolling; Manager-only
  creation; empty/missing catalogs; coherent selection; lost responses, reload
  recovery, and failed post-save dashboard loads; persistence across app restart.
- Include the new wording/help in saved checklist and suggestion/manual-edit
  screens. Check visible colors/text and help on hover, focus, and tap.
- All tests use synthetic records and disposable local/CI PostgreSQL, never Neon.
  Use TestModel and disable real model requests in every layer.
- Run Ruff, mypy, JavaScript syntax checks, and the full pytest suite. Obtain one
  implementation review, open a PR with Summary/Test plan and a code-verified
  change diagram, watch CI, and leave merging to the user.
