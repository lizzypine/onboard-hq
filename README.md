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
uv run pytest
```

## Database and test setup

Install Node.js 22 and run `npm ci` for the pinned `npx dbmate` command.
Copy `.env.example` to `.env` and fill in local settings. The example leaves
credentials blank and sets the non-secret default `DBMATE_NO_DUMP_SCHEMA=true`.
Install PostgreSQL 18 tools (on macOS: `brew install postgresql@18`), then run
`bash scripts/install-dbmate.sh` to install checksum-verified dbmate 2.38.1 in
the ignored `.superpowers/bin` directory. Set `DATABASE_URL` to Neon's pooled
connection and `DATABASE_URL_UNPOOLED` to its direct connection in `.env`.
For an existing UUID-era database, follow the [cutover runbook](docs/database-cutover.md)
before migrating. The final backup must follow the write freeze. Run schema
migrations explicitly, with PostgreSQL 18's tools on PATH:

```sh
npx dbmate --no-dump-schema -e DATABASE_URL_UNPOOLED migrate
```

For an already normalized database, the Add Provider walkthrough additionally
requires `20261122000100_add_provider_requirements.sql`. Merging the implementation
updates source code; it does not apply this migration. Stop the old app, keep a
verified backup, run the explicit migration with `DBMATE_NO_DUMP_SCHEMA=true`,
check `npx dbmate -e DATABASE_URL_UNPOOLED status` for `Pending: 0`, then restart
the matching updated app. Its empty down section leaves schema/data intact and
is not a downgrade procedure. Existing providers do not need reseeding for this
feature. Live Neon migration requires separate authorization.

Managers can now archive or restore a provider from **Select a provider**:
switch the simulated role to **Manager**, select the provider, and choose
**Archive provider**. Confirm the provider's name; saved checklist progress and
history are preserved, while unsaved edits are discarded. The app switches to
**Archived** and keeps that provider selected for viewing. Choose **Restore
provider** to return them to **Active** with the same checklist, statuses, dates,
deadlines, assigned template version, and history. Existing archived providers
can be selected through **Provider view → Archived** and restored the same way.
These controls need no additional migration. Permanent deletion remains deferred.
The role switch is simulated, not real sign-in or access control.

Disable dbmate's automatic schema dump for credentialed connections: its dump
command passes the connection URL to `pg_dump` as a process argument. The committed
`db/schema.sql` snapshot is generated from a passwordless disposable local database
using the same migrations and PostgreSQL 18 tools. Regenerate it there after schema
changes; keep Neon credentials in the environment only.

The onboarding slice has twelve application tables, with integer resource IDs, whole-checklist
versions, normalized captured context/warnings, and immutable manual edit history.
The UUID-to-integer change requires a coordinated maintenance-window cutover for an
existing database; stop/drain the old application and verify a final backup before
migration. SQL rollback refuses this ID conversion; recovery needs that backup and
the matching old app. Do not run a mixture of old and new workers. Seed the existing synthetic provider
explicitly with `uv run --env-file .env python -m db.seed`. Seeding again preserves
existing checklist progress and does not add new template entries to an established
checklist. Migrations and seeds never run at application startup.

The migrations under `db/migrations/` create the tables. `db/queries.py` provides
`fetch_provider`, the application's parameterized query for one provider and their
linked checklist; `tests/test_queries.py` tests it against an isolated database.
Resource IDs are database-generated positive integers. Creation, analysis, and
manual-save retry identities remain UUIDs; they are separate from record IDs.
The old `python -m app.seed` entry point remains compatible. After migrating and
seeding the development database, verify its migration status:

```sh
npx dbmate status
```

It should report `Pending: 0`. Seeding prints `Synthetic provider seed complete.`
and supplies Dr. Kekoa Ejemplo with five checklist rows in an empty database.

Install the pinned Playwright browser once, then run all unit, PostgreSQL
integration, and real-browser end-to-end tests:

```sh
PLAYWRIGHT_BROWSERS_PATH="$PWD/.superpowers/browsers" uv run playwright install chromium
uv run pytest
```

Bare pytest lazily starts a temporary loopback PostgreSQL 18 cluster when a
database test needs it and removes it at session teardown, including test failures.
Pure tests do not start a server. The existing `bash scripts/test.sh uv run pytest`
wrapper is also supported. Set
`PG18_BIN` if its binaries are elsewhere. CI supplies a separate PostgreSQL
service through `TEST_DATABASE_URL`. Tests refuse remote targets and databases
without the `onboard_hq_test_` prefix. Never use the Neon application URL for tests.
Browser contexts and server processes are isolated per test; a failed browser test
keeps its trace in ignored `test-results/`. CI installs Chromium and its system
dependencies and retains failure traces as an artifact. Focused pure rule tests can
still run without a database, for example `uv run pytest tests/test_dates.py`.

## Licensing knowledge sources

The source foundation adds ten application tables. Disposable PostgreSQL 18 needs pgvector 0.8.7. Install the pinned release with `PG_CONFIG=/opt/homebrew/opt/postgresql@18/bin/pg_config bash scripts/install-pgvector.sh` on Apple Silicon. On other systems point `PG_CONFIG` to the PostgreSQL 18 executable. The installer verifies the source archive checksum before building. CI runs its service on the matching pgvector image.

List configured source identifiers with `uv run python -m app.knowledge_sources list`. In an explicitly selected development database with the migration and Dentist catalog, `uv run --env-file .env python -m app.knowledge_sources ingest SOURCE_ID` retrieves one configured source and saves a reviewable draft. Use `internal-guide` for the sanitized internal checklist. The CLI rejects unlisted URLs and redirects. A failed fetch leaves the existing published version available. Missing review/effective dates remain unknown.

A fresh database starts with an empty published corpus. Each official source must be reachable at its configured URL, return its expected PDF or HTML content type, and pass extraction before Manager review. The official NED practitioner instructions and 2026 prescriber education entries were successfully fetched during source verification. If an official server is temporarily unavailable, retry the configured source import after it recovers.

The Manager source API in `/docs` accepts independent UUID operation IDs, the current draft revision and the simulated Manager header. Managers can correct internal text, review scopes and issues, confirm publication, or withdraw a published version. Official source content is replaced through a new controlled import. Retained originals are available as downloads. Source review is required before information is available to retrieval.

The embedding adapter shares the configured gateway/token. Its default model is `text-embedding-3-small`, version `1`, with 1536 dimensions. After changing `EMBEDDING_MODEL`, `EMBEDDING_VERSION` or `EMBEDDING_DIMENSIONS`, explicitly run `uv run --env-file .env python -m app.knowledge_sources activate-space` against the intended development database. It embeds published passages outside transactions and activates the new space after all vectors are ready. A concurrent publication requires restarting the reindex.

## Saved licensing questions

The licensing QA migration adds six tables for questions, captured topics and source versions,
retrieval ranks, claims and citations. In `/docs`, submit `POST /qa/ask` with a new
UUID `request_id`, the selected integer `provider_id`, an optional
`requirement_id` belonging to that provider, and the question. Both simulated
roles can ask for active or archived providers. The server derives Hawaii and
the selected provider type. The question selects related topics and the requirement
provides a fallback hint for broad questions. Both search paths use the same reviewed
type, jurisdiction, topic and effective-period scope.

`GET /qa/requests/{request_id}` reconciles an interrupted response.
`GET /qa/{answer_id}` reopens a retained answer, and
`GET /providers/{provider_id}/answers` lists that provider’s question history.
Identical submissions return the existing result or processing receipt. Reusing
a request UUID with changed input returns 409. Each answer records its outcome,
claims and exact retained citations. Service failures have a distinct outcome.
A source change or date change that affects applicability can mark a retained
answer outdated. Ask a new question with a new UUID for current guidance.
Questions and answers are separate from onboarding progress and review history.

The licensing question fixtures exercise exact hybrid retrieval and citation
plumbing using source-bound excerpts, deterministic embeddings and TestModel
on a disposable local database. The same fixtures record the semantic evaluation
rubric. Live model quality has not been measured.

## What this feature does

Select the fictional provider and enter a synthetic update in Non-manager or Manager
mode. The model extracts proposed changes and supporting text. The original update,
provider context, suggestions, and warnings are saved. Unknown requirements appear
as warnings, and empty extraction is retained as insufficient information.

Switch the **Simulated role** to **Manager** to approve, approve with corrections,
or reject each suggestion independently. Only approved changes update the checklist.
Original proposals remain visible alongside the decision and its applied values.
This role switch demonstrates permissions and does not authenticate a person.

The **Updates** section accepts free-text updates. Pending suggestions appear directly
beneath their matching requirements in the **Onboarding checklist**, with the original
update, supporting text, and warnings. The checklist's pending count shows suggestions
waiting for a decision; saved checklist values change only after approval. Multiple
proposals for one requirement remain separate, newest first.

**Review history** retains original updates, completed decisions, and manual checklist
edits. It starts closed; choose its heading to open or close it. Normal refreshes
and saved decisions preserve your choice; changing providers or reloading the page
starts it closed again. The visible Non-manager role uses the existing internal
`proposer` API value and has the same permissions.

The striped checklist has colored, labeled status badges. Green means a recognized
finished status; blue is Pending, Scheduled, or Submitted; amber is Outstanding or
Incomplete; unfamiliar values are neutral and retain Needs review monitoring.
Color never replaces status text or changes completion rules. Red monitoring
indicators still follow saved deadlines and the server's Hawaii date.

In **Manager** mode, use a checklist row's **Edit** action to change **Status**,
**Expected completion date**, or **Deadline**, then **Save changes** or **Cancel**. Status
uses a requirement-specific dropdown, including the existing value when unfamiliar.
Dates are explicit full dates; clearing either date removes it on Save. Changing
one date never substitutes it for the other. No-op/invalid drafts cannot be saved.
Changing role/provider or choosing Refresh data discards unsaved drafts.
Analyzing an update preserves an open manual edit when that requirement's saved
version has not changed, including incomplete date input. Review dropdown choices
preserve the exact saved/proposed status wording when selected or approved.

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

In **Manager** mode, the green **+ Add provider** button opens five steps: fictional
name, configured provider type dropdown (including when only one is available),
optional proposed start date, requirements, and final review. Standard rows start
**Outstanding** with both dates **Not set**. Add a provider-only requirement by
entering its name, status dropdown, optional Expected completion date, and optional
deadline, then choosing **Save requirement**. It joins the combined draft list;
you can Edit/Remove it or add another before final review. These additions never
modify a shared template. A pending requirement editor must be saved or canceled
before Review.

The final **Add provider** button has no plus sign and saves the provider and all
requirements in one transaction, without a model call. No draft step writes to the
database. A changed standard checklist requires another review before saving.
Managers can create the first provider when templates are configured; types with
no requirements are unavailable. This screen does not edit existing profiles or
add/remove requirements after creation.

The new provider is selected after saving; the previous provider's update draft is
cleared. Duplicate names remain separate records, distinguished in the picker by
type, start date, and a short reference. If a save response is lost, retry the same
save using **Retry save** to recover the original record. Submitted details stay
frozen and survive reload in this browser tab. Recovery requires explicit Manager
action; it never posts automatically. If browser storage cannot retain a new save,
no creation request is sent. If saving succeeds but loading fails, use **Refresh
data** or **Reload saved provider** to load the saved view. Creation never resets
progress or reapplies template changes on retry. Cancel discards an unsent draft;
closing a submitted attempt retains its recovery record and cannot undo a save.

**Expected completion date** means when the item is expected to finish, such as a
scheduled drug screening. **Deadline** means the latest date it must finish. The
**?** help works on hover, keyboard focus, and tap. Both dates remain optional and
independent, and their underlying database/API fields are unchanged.

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
a new request. Real accounts, post-creation requirement additions/removals, and
semantic routing remain outside scope. Provider-type templates are separate from individual checklists;
template edits do not silently change established checklists.

The checklist shows **Finished**, **Remaining**, **Overdue**, and **Needs review**
counts, with a Monitoring label on each row. Remaining includes uncertain items;
Overdue and Needs review are subsets of Remaining. These synthetic completion
rules cover the five canonical Dentist requirements: Signed offer letter,
Received Hawaii/State NED licenses, Completed drug screening, and Approved insurance
credentialing. Status matching trims whitespace and ignores case without changing
the saved wording. Unrecognized statuses, requirements, or provider types show
Needs review, which refers to the completion rule rather than a pending suggestion.
Unconfigured provider-only additions use the explicit generic status list;
Completed means finished, while Outstanding/Pending/Scheduled/Incomplete remain
unfinished. Known provider/name rules still take precedence, and unfamiliar saved
or proposed values retain Needs review.

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
