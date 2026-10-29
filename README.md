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
