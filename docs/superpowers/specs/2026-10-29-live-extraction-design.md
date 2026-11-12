# Live Extraction and Date Confirmation Design

## Intent

Make the existing onboarding page useful for inspecting model-generated suggestions from synthetic updates. Demonstrate the page-to-model-to-page flow without adding retrieval, persistence, or checklist mutation. The project-wide spec is [the proposal](../../proposal.md), particularly LLM Role, Data Use / Incomplete Dates, and Human Review.

## Approaches

- **Live extraction into suggestion cards:** Selected because the page and structured contracts already exist, and this is the smallest useful model-connected feature. The scope includes the date confirmation agreed during brainstorming.
- **Extraction plus temporary status review:** Deferred because approving, correcting, rejecting, and applying statuses introduces another workflow beyond extraction quality.
- **Deadline monitoring:** Deferred because it would exercise Python rules but would not connect the page to the model.

## Scope and Behavior

1. Keep `GET /` and `POST /updates/analyze`. The page sends selected synthetic provider context and original update text. The model returns structured requirement changes, stated date components, supporting text, and ambiguities.
2. Use the provider's existing checklist as the allowed requirement scope. Show valid suggestions together with warnings for unmatched requirements. Run the existing empty-suggestion guard after filtering; if none remain, return insufficient information without changing any requirement.
3. Resolve incomplete dates in plain Python. Month/day without year means the latest valid month/day on or before the proposed start date. Day alone means the latest valid occurrence of that day on or before the start date. January 15, 2027 implies October 22, 2026 for "October 22" and December 18, 2026 for "on the 18th."
4. With no proposed start date, incomplete dates stay unset with a warning. Missing/invalid/unsupported date mentions are not guessed. Fully specified valid dates are preserved; the on-or-before boundary applies to inferred dates. There is no fallback to today's date.
5. Display original wording, resolved date, and an inference explanation. Inferred dates require editable, page-local confirmation. Editing clears confirmation; analyzing a new update clears prior confirmations. Confirming a date does not approve a status change.
6. A model/configuration failure is visibly distinct from insufficient information. Do not fabricate a placeholder result when the model fails.

## Technical Calls

These are implementation choices proposed with the plan, rather than additional workflow decisions:

- Keep FastAPI, Pydantic, and the installed Pydantic AI stack. Use an OpenAI-compatible provider with `LLM_API_TOKEN`, `LLM_API_GATEWAY`, and required `LLM_MODEL` environment configuration. Create the configured agent lazily, so `GET /` and tests do not need credentials.
- Keep model extraction separate from deterministic filtering/date resolution. Split rules by responsibility when adding date handling, as required by `AGENTS.md`; preserve `app.rules.validate_update_suggestions` for existing callers.
- Treat unsupported partial date shapes as unresolved with a warning. Only complete dates, month/day, and day-only mentions are supported in this slice.
- Use canonical checklist names for model output. Compare names after trimming and case folding; retain canonical names in responses. Do not build a semantic requirement matcher.
- Keep the three response top-level fields `message`, `suggestions`, and `ambiguities`; add date metadata within suggestions.
- Block real model requests throughout automated tests. Use `TestModel` outputs to test structured extraction and integration, and exercise the UI in the browser with deterministic output.

## Boundaries

No database, RAG, saved history, accounts, reminders, general approve/correct/reject workflow, or status application. No automatic start-date readiness judgment. The selected synthetic provider context is request data, not a trusted or persisted provider registry. No live model smoke call is required to complete automated verification.

## Acceptance

- A relevant update yields inspectable suggestions and supporting text through the real page/endpoint integration, using a substituted model during tests.
- Mixed known/unknown requirements retain the known suggestions and warn about the unknown ones; no applicable suggestions yields insufficient information.
- Calendar inference covers month/day, day-only, prior-year/prior-month rollover, leap days, and missing reference dates.
- Inferred dates can be corrected and confirmed locally; editing/reanalysis resets confirmation and leaves the checklist unchanged.
- Model errors are displayed as errors; all automated tests, Ruff, and mypy pass without real model requests.

## Left to Implementation

Function bodies, prompt wording consistent with these constraints, accessible markup, and focused styling. No particular vendor model identifier is chosen by this design; deployment supplies it via `LLM_MODEL`. Any wider requirement/status taxonomy or persistence work needs a separate design.
