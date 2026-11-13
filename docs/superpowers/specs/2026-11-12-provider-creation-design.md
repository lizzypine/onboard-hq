# Manager-Only Provider Creation

## Intent

Let a manager add a fictional provider to the onboarding app and immediately work
with that provider's own saved checklist. The user selected Manager-only creation
and an initial status of Outstanding for every requirement, with progress entered
later through the existing update-and-approval workflow.

The canonical proposal's **Data Use > Provider Types and Checklists**, **Incomplete
Dates**, **Human Review**, and **Testing Strategy** remain authoritative. This
feature continues the synthetic-only prototype and simulated roles.

## Approaches

- **Create from a configured type template with all requirements Outstanding —
  selected by the user.** Gives every new provider their own complete starting
  checklist and uses the established review workflow for progress.
- **Enter existing progress during creation — considered.** Adds another status
  editing workflow and more decisions to the initial form; the user selected the
  first approach.

## Form and Flow

Proposed presentation: an Add provider action in **1. Select a provider**, visible
only in Manager mode. It opens an inline form in that section; Cancel closes it
without creating a record. This placement is the author's recommendation.

- Required **Provider name**, accepting nonblank fictional display names.
- Required **Provider type**, chosen only from stored types with at least one
  configured requirement template. Show a single available type as a labeled value;
  use a picker when several are available. The project ships a Dentist template;
  this change does not invent Dental Hygienist requirements or add other fixtures.
- Optional **Proposed start date**, using an explicit date input. Leave it unset by
  default; no current-date or other fallback.
- A read-only preview of the selected type's requirement names, each Outstanding,
  with requirement dates and deadlines Not set. This is informational: the server
  copies the authoritative template it reads during creation. If templates change
  while a form is open, the created provider's returned checklist is authoritative.
- **Add provider** and **Cancel** actions. Submit only with valid fields. Disable
  conflicting interactions while a save or refresh is in progress.
- After creation, select the new provider, load their coherent dashboard and empty
  update history, clear the previous provider's update text/request state, and close
  the form. A new Dentist with the five shipped requirements shows Finished 0,
  Remaining 5, Overdue 0, Needs review 0.
- A manager can create the first provider even when no provider is currently
  selected, provided templates are configured. Missing templates/configuration
  produce an actionable error and no fabricated checklist or record.
- The general prototype notice and form identify this as fictional/synthetic data.
  The role switch remains explicitly simulated and does not authenticate a person.

## Creation Rules and Stored State

The server enforces Manager mode on the creation operation. Proposer mode and a
missing role cannot create records. Request/response validation uses Pydantic;
authorization and initialization defaults remain plain Python rules.

Create the provider and its full copied checklist in one PostgreSQL transaction.
Use the selected stored type's own requirements; never copy another provider's
progress. Every requirement starts Outstanding, with scheduled_date/deadline null
and version 0. Preserve source-template references and relational type constraints.

The new checklist is independent. Later template changes do not add, rename,
remove, or change its saved requirements. Creating a provider never modifies
existing provider records, their checklist progress, histories, or decisions.

Use a stable client-generated creation UUID as the provider ID for one form's save
attempts. An identical retry returns that existing provider without reinitializing
the checklist; this remains true after template or checklist progress changes.
The same ID with different name/type/start-date input returns a conflict. Keep the
ID across save/response/refresh failures; a deliberate new form starts a new ID.
Do not deduplicate by name: distinct providers may share a display name. Distinguish
duplicate names in the picker with type/start date and a short reference if needed.

Missing/empty type templates must fail without a partial provider. Invalid fields
produce validation errors. Database/schema/configuration failures use safe errors
without connection strings or raw driver details. No model call is involved.

## Failure and Selection Behavior

Preserve the existing analysis/review retry behavior and coherent dashboard/history
loading. Do not combine the new provider's name with a prior provider's checklist
or history. Until the new snapshot loads, either keep the complete previous snapshot
with its matching selected provider or clear the snapshot and disable analysis.

If creation succeeded but loading failed, say the provider was saved and retain the
creation ID/preferred new selection for recovery. Retrying must not create another
provider. If the save response was lost, retry the same ID and payload. A conflict
after editing a previously submitted attempt must not overwrite the saved provider.

Switching providers loads the selected provider's own requirements before analysis.
This does not add support for updates mentioning multiple providers; that expected
behavior remains an open proposal question. Saved evidence and decisions stay
scoped to their existing provider IDs.

## Boundaries and Builder Choices

No real employee records, sign-in, bulk imports, email processing, uploads, template
editor, checklist exceptions, provider editing/deletion, deadline entry, reminders,
model routing, or additional completion-policy mappings are included.

The existing schema already supports provider and requirement insertion; no
migration is expected. Keep the explicit development seed and never run it at
startup or use its completed statuses as defaults for new records.

Keep routes in `app/main.py`, connection handling in `app/database.py`, database
operations in `app/repository/providers.py`, contracts in focused Pydantic models,
and creation authorization/defaults/orchestration outside routes. Split browser
provider-form responsibilities from general onboarding/review orchestration as
needed, updating AGENTS.md. Exact function/DTO names and HTTP statuses, consistent
with existing conventions, are left to the implementation plan.

Update the affected **Provider Types and Checklists** and role-related proposal
text with the approved creation behavior in this feature's change. Keep the initial
development fixture distinction: creating fictional records is separate from adding
new type fixtures or claiming real-world checklist validation.

## Verification

- Unit coverage for request validation, Manager-only creation, defaults and request
  identity conflict rules. No database or real model.
- PostgreSQL integration coverage for atomic creation, exact type-template copying,
  null dates/version 0, isolated existing records, unknown/empty types, idempotent
  and concurrent retries, conflicting reused IDs, unchanged progress on retry, and
  no backfill after template edits. Include other synthetic types only in guarded
  tests, without applying Dentist completion rules to them.
- Real-browser coverage for role visibility, adding/selecting a fictional provider,
  the expected initial counts, switching between providers without mixed state,
  duplicate names, first-provider creation, invalid fields, cancellation, restart
  persistence, lost save responses and failed post-save refresh recovery.
- Exercise analysis/review for the new selected provider with TestModel and verify
  the original provider's checklist/history remain unchanged.
- Every automated layer uses deterministic TestModel with real requests disabled
  and a separate disposable/local test database. Never test against Neon.
- Run Ruff, mypy, JavaScript syntax checks and the full suite locally and in CI;
  get one fresh implementation review, open a PR with its verified change diagram,
  watch checks, and leave merging to the user.
