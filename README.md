# Onboard HQ

A synthetic provider-onboarding prototype built with FastAPI and Pydantic AI.

## Run locally

Install dependencies with `uv sync --locked --dev`. Set these environment variables
in a local, ignored `.env` file:

- `LLM_API_TOKEN`: the gateway token.
- `LLM_API_GATEWAY`: the OpenAI-compatible API base URL, including its API path.
- `LLM_MODEL`: a model identifier supported by your gateway.

Do not commit credentials. Start the development server with:

```sh
uv run --env-file .env fastapi dev app/main.py
```

The page loads without model configuration; analysis requires all three variables.
Automated tests use `TestModel` and block real model requests:

```sh
uv run ruff check
uv run mypy
uv run pytest
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

For the complete automated suite, run:

```sh
bash scripts/test.sh uv run pytest
```

This starts and removes a temporary loopback PostgreSQL 18 cluster. Set
`PG18_BIN` if its binaries are elsewhere. CI supplies a separate PostgreSQL
service through `TEST_DATABASE_URL`. Tests refuse remote targets and databases
without the `onboard_hq_test_` prefix. Never use the Neon application URL for tests.

## What this feature does

Select the fictional provider and enter a synthetic update. The model extracts
suggested changes and supporting text. Unknown requirements appear as warnings
alongside valid suggestions; no applicable suggestions yields insufficient information.

For incomplete dates, Python uses the most recent valid occurrence on or before
the proposed start date. Check the original wording and inference explanation,
edit the inferred date if needed, then select **Confirm date**. Editing a date
clears its confirmation, and another analysis or page refresh resets confirmations.
Without a proposed start date, incomplete dates stay unset with a warning.

Date confirmation is temporary and does not approve a status change. The checklist
never changes, and there is no database, saved history, account system, or retrieval.
The automated tests establish application behavior with deterministic model output;
they do not measure real-model extraction quality.
