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
