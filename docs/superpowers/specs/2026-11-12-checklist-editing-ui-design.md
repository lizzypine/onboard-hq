# Checklist Editing and UI Refinements

## Intent and Scope

Make the checklist easier to scan and let a Manager explicitly save changes to
status, requirement date, and deadline. Keep proposing updates available to both
simulated roles, retain evidence and decisions, and preserve each provider's own
records. This remains a fictional-data prototype with simulated permissions.

The user chose the striped table, a status dropdown, all three editable fields,
and added color. They also requested a collapsed Suggestions and review history
section, an Updates heading, and Add provider at the selection section's top right.

## Approaches

- **Striped table — selected by the user.** Alternating subtle fills and stronger
  dividers separate requirements while aligned columns support comparison. Each
  row has Edit; one row's editor opens underneath with Save changes and Cancel.
- **Requirement cards — considered.** Strong separation and room for fields, at
  the cost of more scrolling and repeated labels.
- **Expandable rows — considered.** Compact summaries, but comparing dates and
  deadlines requires opening rows.

The updated interactive preview is served at `http://127.0.0.1:8002/preview.html`.
It demonstrates layout and local interactions only; it is not the application.
Its comparison controls and extra vertical space are not product UI.

## Page Presentation

Use the existing page and native controls; no new UI framework or dependencies.

- Rename section 3 to **Updates**; retain Original update and Analyze update.
- Place **Add provider** at the top right beside **1. Select a provider**. Preserve
  Manager-only visibility, creation preview, stable save identities, and recovery.
  Let the header wrap sensibly at small widths without overlapping its title.
- Keep the existing monitoring counts and Monitoring column above/in the checklist.
  Apply stripes by requirement, not by inserted editor row; keep each editor
  visually associated with its requirement. A selected row has a visible editing
  cue as well as a colored background. Names stay read-only.
- Make **Suggestions and review history** one native disclosure. Default closed on
  initial page load and provider change; users can open/close it with pointer or
  keyboard. Preserve their choice during refresh, analysis, and saved decisions.
  Do not automatically open it after analysis. Keep a pending-suggestion count
  visible in its summary and point to the section from the saved-analysis message.
  Distinguish pending suggestions from monitoring's **Needs review** count.
- Show saved manual checklist edits in the same history section, labeled
  **Manager checklist edit**, alongside original updates and review decisions in
  newest-first order. Show before/after values, changed field labels, and time.

## Status Choices and Color

Replace status text entry with native dropdowns in the direct checklist editor
and pending suggestion's Manager correction row. The choices are specific to the
provider type and requirement. For the five canonical synthetic Dentist items,
reuse the existing recognized monitoring vocabulary rather than inventing policy:

| Requirement | Dropdown choices |
| --- | --- |
| Offer letter | Outstanding, Pending, Incomplete, Signed |
| Hawaii dental license | Outstanding, Pending, Incomplete, Received |
| State NED license | Outstanding, Pending, Incomplete, Received |
| Drug screening | Outstanding, Pending, Scheduled, Incomplete, Completed |
| Insurance credentialing | Outstanding, Pending, Submitted, Incomplete, Approved |

Keep a saved or originally proposed unfamiliar status available verbatim when
needed to preserve/approve it; opening an editor must never rewrite it. Such values
retain Needs review monitoring. For unconfigured types/requirements, offer
Outstanding and existing/proposed values only; do not apply Dentist completion
rules. No custom status text field or template/status administration is added.
The server validates a direct edit against its authoritative allowed choices plus
the locked current value. Extraction remains capable of retaining stated statuses;
this change must not discard saved evidence or silently normalize wording.

The author's proposed palette uses a teal header, subtle blue stripes, and labeled
status badges: green for recognized finished values; blue for Pending, Scheduled,
and Submitted; amber for Outstanding and Incomplete; neutral for unfamiliar values.
Color never replaces words. Keep red overdue indicators tied to existing monitoring
rules. Unfinished blue items still count as Remaining; badge colors do not alter
completion/deadline rules. Provide readable contrast, visible focus, safe text
rendering, and desktop/390px layouts with contained horizontal table scrolling.

## Direct Manager Edits

This adds an explicit Manager save path alongside suggestion approval. It does not
call the model, fabricate an original update/suggestion, or auto-approve a pending
suggestion. Enforce Manager role server-side; missing role defaults to Proposer.

- Edit status, requirement date, and deadline on an existing checklist row only.
  Dates use native full-date fields. Allow clearing either date with an explicit
  Save; preserve untouched fields. Do not infer dates or substitute one date for
  another. No new ordering restrictions between dates are introduced.
- Only one row has an unsaved editor at a time. Save is disabled for invalid/no-op
  input. Cancel discards the draft without writes. Switching role/provider or
  explicitly refreshing discards unsaved drafts; clearly identify any saved result.
- Save the row change and an immutable manual-edit history record atomically. Store
  provider/requirement IDs, stable operation ID, submitted values, before/after
  status/date/deadline, expected/resulting checklist version, simulated Manager
  role, and timestamp. Do not reuse review_decisions or fake LLM suggestions.
- Lock the authoritative requirement, verify provider ownership, compare expected
  version, and increment the version once on any real edit, including deadline-only
  edits. A stale edit fails without overwriting newer changes. Existing pending
  suggestions therefore become stale after a direct edit and retain current review
  conflict behavior. History and existing terminal decisions remain unchanged.
- An identical retry of the same operation returns its saved result without
  reapplying changes or recording another event, even after later progress. Reused
  identity with different input conflicts. Keep the operation ID/payload across lost
  responses and reconcile that attempt before allowing another save from the draft.
- A failed atomic save leaves no audit event or partial field changes. If saving is
  known to have succeeded but reloading fails, say so and offer Refresh data; show
  no mixed provider snapshot or invented monitoring. A lost response can be retried
  without duplicates. Do not let a retry reset later progress.

## Architecture and Boundaries

Keep validation in Pydantic, role/status/version rules in plain Python, orchestration
outside routes, and locked atomic writes in a focused repository. Separate direct
edit contracts/history from LLM update/review contracts. Use a forward-only dbmate
migration for immutable manual-edit records and update the schema snapshot from an
isolated local database. Keep dropdown metadata and completion rules consistent
without duplicating divergent definitions. Exact module names, route contracts,
and history transport are builder choices, documented in the implementation plan.

No requirement addition/removal/renaming, provider profile editing, checklist
exceptions, template editor, new provider fixtures, reminders, model changes,
multi-provider messages, real employee records, or real authentication are added.

Synchronize canonical proposal **Provider Types and Checklists**, **Status and
Deadline Monitoring**, **Human Review**, and **Testing Strategy** with the new direct
Manager save path. Update AGENTS layout responsibilities and README use/recovery
instructions with implementation. The earlier provider-creation design's exclusion
of a deadline editor applied to that feature; this separate change adds it.

## Verification

Use unit, isolated PostgreSQL integration, and real-browser tests. Every automated
layer disables real model requests and uses TestModel; never test on Neon or load
application credentials into tests.

Cover role enforcement; requirement-specific dropdowns and unfamiliar saved/proposed
values; full/partial/cleared dates; before/after history; no-op/cancel; atomic rollback;
provider ownership; concurrent/stale edits and suggestion reviews; identical/conflicting
retry identities; retry after later progress; failed/lost responses; failed reloads;
deadline-only monitoring changes using Hawaii time; provider isolation; restart
persistence; disclosure defaults and toggle preservation; pending counts; renamed
heading; Add provider placement; keyboard, safe text, contrast, and narrow layout.

Retain all creation/analysis/review/monitoring checks. Run Ruff, mypy, JavaScript
syntax checks, and the complete disposable-database pytest suite locally and in CI.
Get one fresh whole-branch implementation review, open a PR with its verified change
diagram, watch checks, and leave merging to the user.
