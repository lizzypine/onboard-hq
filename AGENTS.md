# Instructions for coding agents

This project is a web app that helps community health center staff manage onboarding for new healthcare providers. It brings requirements, statuses, deadlines, and proposed start dates into one place so staff can quickly see outstanding tasks. An LLM turns free-text updates into suggested changes, which users review and approve before saving.

The full proposal is in docs/proposal.md.

## Layout

- app/main.py: routes and the page. No business rules.- app/agent.py: the Pydantic AI agent and output model.- app/rules.py: rules in plain Python. No FastAPI, no LLM client.

## Commands

`bashuv run fastapi dev app/main.py # run the appuv run ruff check # lintuv run mypy # check typesuv run pytest # run the tests`

## Rules

- Tests never call a real model. Use TestModel with override_allow_model_requests(False).- Read LLM_API_TOKEN and LLM_API_GATEWAY from the environment. Never write a key outside .env.- Run ruff, mypy, and pytest after every change and include their output. Never report done while one fails.- Never weaken a check: no raised max-complexity, no # noqa or # type: ignore, no skipped tests.
