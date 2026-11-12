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

Do not commit credentials. Start the development server with:

```sh
uv run --env-file .env fastapi dev app/main.py
```

The HTML shell loads without configuration. Provider data requires a migrated,
seeded database; analysis also requires the model settings. Automated tests use
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
PATH="$(brew --prefix postgresql@18)/bin:.superpowers/bin:$PATH" dbmate -e DATABASE_URL_UNPOOLED migrate
```

The schema has seven application tables. Seed the existing synthetic provider
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

The automated tests establish application behavior with deterministic model output;
they do not measure real-model extraction quality. No tests run against the Neon
application database.
