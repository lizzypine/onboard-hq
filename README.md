# Onboard HQ

A synthetic provider-onboarding prototype with saved checklists, model suggestions,
and manager review, built with FastAPI, Pydantic AI, and Neon PostgreSQL.

## Run locally

Install dependencies with `uv sync --locked --dev`. Set these environment variables
in a local, ignored `.env` file:

- `LLM_API_TOKEN`: the gateway token.
- `LLM_API_GATEWAY`: the OpenAI-compatible API base URL, including its API path.
- `LLM_MODEL`: a model identifier supported by your gateway.
- `DATABASE_URL`: the pooled Neon PostgreSQL connection used by the app.
- `DATABASE_URL_UNPOOLED`: the direct connection for dbmate migrations.

For `LLM_MODEL=gpt-6-luna`, the app explicitly disables reasoning on Chat
Completions requests because this model rejects function tools with reasoning
enabled. Structured extraction still uses Pydantic validation. Other configured
models retain their default reasoning settings.

Do not commit credentials. Start the development server with:

```sh
uv run --env-file .env fastapi dev app/main.py
```

The HTML shell loads without configuration. Provider data requires a migrated
database with configured type templates (the explicit development seed supplies
the synthetic Dentist templates); analysis also requires the model settings. Automated tests use
`TestModel` and block real model requests, including the browser test server:

```sh
uv run ruff check
uv run mypy
bash scripts/test.sh uv run pytest
```

## Database and test setup

Install PostgreSQL 18 tools (on macOS: `brew install postgresql@18`), then run
`bash scripts/install-dbmate.sh` to install checksum-verified dbmate 2.38.1 in
the ignored `.superpowers/bin` directory. Set `DATABASE_URL` to Neon's pooled
connection and `DATABASE_URL_UNPOOLED` to its direct connection in `.env`.
Run schema migrations explicitly, with PostgreSQL 18's tools on PATH:

```sh
PATH="$(brew --prefix postgresql@18)/bin:.superpowers/bin:$PATH" dbmate --no-dump-schema -e DATABASE_URL_UNPOOLED migrate
```

Disable dbmate's automatic schema dump for credentialed connections: its dump
command passes the connection URL to `pg_dump` as a process argument. The committed
`db/schema.sql` snapshot is generated from a passwordless disposable local database
using the same migrations and PostgreSQL 18 tools. Regenerate it there after schema
changes; keep Neon credentials in the environment only.

The schema has eight application tables, including immutable manual checklist edit
history. Apply the checked-in migrations before using the updated app. Seed the existing synthetic provider
explicitly with `uv run --env-file .env python -m app.seed`. Seeding again preserves
existing checklist progress and does not add new template entries to an established
checklist. Migrations and seeds never run at application startup.

Install the pinned Playwright browser once, then run all unit, PostgreSQL
integration, and real-browser end-to-end tests:

```sh
PLAYWRIGHT_BROWSERS_PATH="$PWD/.superpowers/browsers" uv run playwright install chromium
bash scripts/test.sh uv run pytest
```

This starts and removes a temporary loopback PostgreSQL 18 cluster. Set
`PG18_BIN` if its binaries are elsewhere. CI supplies a separate PostgreSQL
service through `TEST_DATABASE_URL`. Tests refuse remote targets and databases
without the `onboard_hq_test_` prefix. Never use the Neon application URL for tests.
Browser contexts and server processes are isolated per test; a failed browser test
keeps its trace in ignored `test-results/`. CI installs Chromium and its system
dependencies and retains failure traces as an artifact. Focused pure rule tests can
still run without a database, for example `uv run pytest tests/test_dates.py`.

## What this feature does

Select the fictional provider and enter a synthetic update in Proposer or Manager
mode. The model extracts proposed changes and supporting text. The original update,
provider context, suggestions, and warnings are saved. Unknown requirements appear
as warnings, and empty extraction is retained as insufficient information.

Switch the **Simulated role** to **Manager** to approve, approve with corrections,
or reject each suggestion independently. Only approved changes update the checklist.
Original proposals remain visible alongside the decision and its applied values.
This role switch demonstrates permissions and does not authenticate a person.

The **Updates** section accepts free-text updates. **Suggestions and review history**
starts closed; choose its heading to open or close it. The visible pending count
shows suggestions waiting for a decision. Analysis points you there without opening
the section automatically. Normal refreshes and saved decisions preserve your
choice; changing providers or reloading the page starts it closed again.

The striped checklist has colored, labeled status badges. Green means a recognized
finished status; blue is Pending, Scheduled, or Submitted; amber is Outstanding or
Incomplete; unfamiliar values are neutral and retain Needs review monitoring.
Color never replaces status text or changes completion rules. Red monitoring
indicators still follow saved deadlines and the server's Hawaii date.

In **Manager** mode, use a checklist row's **Edit** action to change **Status**,
**Requirement date**, or **Deadline**, then **Save changes** or **Cancel**. Status
uses a requirement-specific dropdown, including the existing value when unfamiliar.
Dates are explicit full dates; clearing either date removes it on Save. Changing
one date never substitutes it for the other. No-op/invalid drafts cannot be saved.
Changing role/provider or choosing Refresh data discards unsaved drafts.

Each direct save updates the checklist and appends a **Manager checklist edit**
history entry atomically, with before/after values and time. It makes no model call
and does not approve pending suggestions. Even a deadline-only save advances the
checklist version: older pending suggestions must be reanalyzed before approval,
and concurrent stale edits conflict rather than overwrite another manager's work.

If a direct save response is lost, use **Retry checklist save**. The submitted values
and operation identity stay frozen, including in this browser tab across reloads
when browser storage is available. Return to that provider in Manager mode to retry;
the retry cannot reapply changes over later progress. A confirmed save with a failed
view refresh says it was saved; **Refresh data** or retry loads the saved state.
Manual saves appear alongside updates and review decisions in newest-first history.

In **Manager** mode, choose **Add provider**, enter a fictional name, choose a
configured type, and optionally set a proposed start date. A single available type
appears as text. Review the requirement preview, then save. Each provider receives
an independent checklist from the current type template: all requirements start
**Outstanding**, with dates and deadlines **Not set**. Creation makes no model call;
enter progress through the existing update-and-approval flow. Managers can also add
the first provider when templates are configured. Types with no requirements are
unavailable; this screen does not edit templates or existing provider profiles.

The new provider is selected after saving; the previous provider's update draft is
cleared. Duplicate names remain separate records, distinguished in the picker by
type, start date, and a short reference. If a save response is lost, retry the same
form to recover the original record. Keep its details unchanged: changed details
under the same save identity conflict rather than overwrite a saved provider. If
saving succeeds but loading fails, use **Refresh data** or retry that form to load
the saved provider. Creation never resets progress or reapplies template changes
on retry. Cancel closes the form; it does not undo a save that already succeeded.

Each pending Manager decision shows the affected requirement as an editable
checklist row. Highlighted cells and text identify differences from saved values;
the original proposal remains visible while you select **Reviewed status** or
**Reviewed date**. Requirement names and deadlines are read-only. The saved
checklist and monitoring counts change only after approval.

The date field initially contains the proposed date, or the saved date when none
was proposed. Leave it untouched to keep that value, enter another date to set it,
or clear it to remove the date through **Approve with corrections**. Inferred dates
must remain nonempty and explicitly confirmed before approval.

Review and submit one suggestion at a time. Saving a decision, refreshing data,
or switching role/provider rebuilds the review rows and clears other unsaved edits.

For incomplete dates, Python uses the most recent valid occurrence on or before
the proposed start date. Check the original wording and inference explanation,
edit the inferred date if needed, then check **Confirm inferred date** and approve.
Editing a date clears its confirmation. Selecting a date is separate from changing
the deadline; a date correction never overwrites a requirement deadline.
Without a proposed start date, incomplete dates stay unset with a warning.

Checklist progress, pending suggestions, and completed decisions survive refreshes
and application restarts. A stale or already-reviewed suggestion cannot overwrite
newer progress; refresh or reanalyze before approving. A failed or interrupted
analysis remains visible and creates no reviewable partial suggestions. Retrying the
same request ID does not repeat analysis; editing/submitting a new proposal creates
a new request. No real accounts, checklist-exception controls, or semantic routing
are included. Provider-type templates are separate from individual checklists;
template edits do not silently change established checklists.

The checklist shows **Finished**, **Remaining**, **Overdue**, and **Needs review**
counts, with a Monitoring label on each row. Remaining includes uncertain items;
Overdue and Needs review are subsets of Remaining. These synthetic completion
rules cover the five canonical Dentist requirements: Signed offer letter,
Received Hawaii/State NED licenses, Completed drug screening, and Approved insurance
credentialing. Status matching trims whitespace and ignores case without changing
the saved wording. Unrecognized statuses, requirements, or provider types show
Needs review, which refers to the completion rule rather than a pending suggestion.

Monitoring uses only saved deadlines and the server's Hawaii calendar date
(`Pacific/Honolulu`). A deadline today is due today; an unfinished requirement
with an earlier deadline is Overdue. Finished items have no overdue warning.
An uncertain item with an earlier deadline shows **Deadline passed — needs review**
without increasing the confirmed Overdue count. Appointment dates and proposed
start dates never substitute for deadlines; existing missing deadlines remain unset.

The labeled as-of date describes the loaded snapshot. Loading a provider,
**Refresh data**, and successful analysis/review reload monitoring; there is no
automatic midnight refresh. Pending or rejected proposals and role switches leave
the counts unchanged. A failed immediate refresh after a saved analysis/review/manual edit retains
the whole previous snapshot and explains that saving succeeded. Provider selection,
creation, and **Refresh data** clear the old snapshot before loading a new one, so
a failed load cannot display another provider's checklist. An unavailable initial load
shows no counts and disables submission. Empty saved checklists explicitly show
zero counts and an empty message; no checklist is described as permission to start.

The automated tests establish application behavior with deterministic model output;
they do not measure real-model extraction quality. No tests run against the Neon
application database.
