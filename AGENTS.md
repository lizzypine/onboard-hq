# Instructions for coding agents

This project is a web app that helps community health center staff manage onboarding for new healthcare providers. It brings requirements, statuses, deadlines, and proposed start dates into one place so staff can quickly see outstanding tasks. An LLM turns free-text updates into suggested changes, which users review and approve before saving.

The full proposal is in docs/proposal.md.

## Layout

- app/main.py: routes and the page. No business rules.
- app/agent.py: the Pydantic AI agent and output models.
- app/rules/__init__.py: compatibility exports for plain Python rules.
- app/rules/scope.py: requirement scope and empty-suggestion validation. No FastAPI, no LLM client.
- app/rules/dates.py: calendar date inference in plain Python. No FastAPI, no LLM client.
- This is the starting layout. When a module takes on a second responsibility, split it by responsibility (for example, `app/rules.py` into `app/rules/quota.py` and `app/rules/scope.py`) and update this section in the same change.

## Commands

`bashuv run fastapi dev app/main.py # run the appuv run ruff check # lintuv run mypy # check typesuv run pytest # run the tests`

## Rules

- Tests never call a real model. Use TestModel with override_allow_model_requests(False).- Read LLM_API_TOKEN and LLM_API_GATEWAY from the environment. Never write a key outside .env.- Run ruff, mypy, and pytest after every change and include their output. Never report done while one fails.- Never weaken a check: no raised max-complexity, no # noqa or # type: ignore, no skipped tests.

## Changes

- Never commit to main. Make each change on its own branch and open a pull request with gh pr create. The description has a ## Summary (what changed and why, citing docs/proposal.md) and a ## Test plan checklist (checked items were run; unchecked items are left for the reviewer).- After pushing, run gh pr checks --watch and report the result.-
  Never merge a pull request. The person merges after reviewing it.

## Spec

`docs/proposal.md` is the spec. When a decision is made in a conversation (a feature added or left out, a limit or value chosen, an open question answered), edit the section the decision belongs to so that it states the decision, in the same change, and name that section in the pull request Summary. Change only what the decision affects. Do not add a dated log, approval history, or status notes; git and `docs/superpowers/` keep the history.- A design under `docs/superpowers/specs/` covers one change; `docs/proposal.md` covers the whole project. If the two disagree, ask before building.
