# Instructions for coding agents

This project is a web app that helps community health center staff manage onboarding for new healthcare providers. It brings requirements, statuses, deadlines, and proposed start dates into one place so staff can quickly see outstanding tasks. An LLM turns free-text updates into suggested changes, which users review and approve before saving.

The canonical project spec is `docs/proposal.md`. `docs/proposal-v2.pdf` contains the revised proposal and Ethan's feedback; distinguish changes incorporated into the proposal from suggestions still under consideration.

## Product constraints and proposal feedback

- Use synthetic provider records and administrative updates only. Version one excludes real employee records, forwarded-email processing, document uploads, and automated reminders.
- Load the selected provider's current requirements and statuses before interpreting an update. Do not automatically add a requirement that does not apply to that provider type.
- Present each suggestion with the original update and supporting text. Users must be able to approve, correct, or reject suggestions independently; only approved changes may update requirement statuses or dates. Retain original updates, suggestions, and review decisions in persistent storage.
- Use the **Sample Input Set** and **Three Acceptance Criteria** in `docs/proposal.md` when implementing and testing extraction. Include relative dates ("next Tuesday"), corrections ("actually the drug screen moved to the 29th"), and status reversals (credentialing returned for missing information becomes Incomplete). Flag ambiguous dates and keep corrections subject to human approval.
- Follow **Data Use > Incomplete Dates** in `docs/proposal.md` for date resolution: incomplete dates are anchored to the proposed start date, and unsupported wording produces a warning with no guessed date. The revised PDF's references to today's date and the upcoming month do not override this policy; resolve those differences in the spec before extending date handling.
- Include a synthetic message mentioning two providers when evaluating provider scoping. Ethan suggested this harder case, but its expected behavior is not yet specified; settle it in the spec before implementing support for updates about multiple providers.
- Policy/checklist documents retrieved by provider type, with citations to policy lines, are an investigation option from Ethan's feedback. Document retrieval and RAG are not committed version-one requirements.
- Ethan suggested comparing the time to answer "what's still outstanding for Dr. X?" using the current process versus the app. Keep dashboard correctness checks; investigate this additional value measure with the health center contact before setting evaluation targets.
- Version-one permissions remain undecided. Ethan suggested either a single role or anyone proposing with a manager approving. Resolve that choice in the spec before implementing permissions; the sketch's question about restricting updates to HR/credentialing is not a requirement.

## Layout

- `app/main.py`: routes and the page. No business rules.
- `app/agent.py`: the Pydantic AI agent and output models.
- `app/updates.py`: extraction, scope filtering, and date-resolution orchestration. No HTTP or UI code.
- `app/rules/__init__.py`: compatibility exports for plain Python rules.
- `app/rules/scope.py`: requirement scope and empty-suggestion validation. No FastAPI, no LLM client.
- `app/rules/dates.py`: calendar date inference in plain Python. No FastAPI, no LLM client.
- This is the starting layout. When a module takes on a second responsibility, split it by responsibility (for example, `app/rules.py` into `app/rules/quota.py` and `app/rules/scope.py`) and update this section in the same change.

## Commands

```bash
uv run fastapi dev app/main.py # run the app
uv run ruff check             # lint
uv run mypy                   # check types
uv run pytest                 # run the tests
```

## Rules

- Tests never call a real model. Use `TestModel` with `override_allow_model_requests(False)`.
- Read `LLM_API_TOKEN` and `LLM_API_GATEWAY` from the environment. Never write a key outside `.env`.
- Run ruff, mypy, and pytest after every change and include their output. Never report done while one fails.
- Never weaken a check: no raised max-complexity, no `# noqa` or `# type: ignore`, no skipped tests.

## Changes

- Never commit to main. Make each change on its own branch and open a pull request with `gh pr create`. The description has a `## Summary` (what changed and why, citing `docs/proposal.md`) and a `## Test plan` checklist (checked items were run; unchecked items are left for the reviewer).
- After pushing, run `gh pr checks --watch` and report the result.
- Never merge a pull request. The person merges after reviewing it.
- When a pull request is ready to open, has just opened, or is refreshed after code changes, use `.agents/skills/pr-diagram/SKILL.md` to maintain one code-verified Mermaid change diagram while preserving Summary and Test plan.

## Spec

- `docs/proposal.md` is the spec. When a decision is made in a conversation (a feature added or left out, a limit or value chosen, an open question answered), edit the section the decision belongs to so that it states the decision, in the same change, and name that section in the pull request Summary. Change only what the decision affects. Do not add a dated log, approval history, or status notes; git and `docs/superpowers/` keep the history.
- When a revised proposal incorporates a change, synchronize the affected section of `docs/proposal.md` in the same change as the agent guidance. Feedback phrased as an option or suggestion does not by itself settle an open question.
- A design under `docs/superpowers/specs/` covers one change; `docs/proposal.md` covers the whole project. If the two disagree, ask before building.
