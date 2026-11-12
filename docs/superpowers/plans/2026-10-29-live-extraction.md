# Live Extraction and Date Confirmation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Connect the existing page to structured model extraction, retain valid suggestions with warnings, and let users inspect, edit, and temporarily confirm inferred dates without changing checklist statuses.

**Architecture:** Pydantic AI extracts requirement changes and stated date components. Plain Python filters requirement scope and resolves dates; an orchestration module assembles the existing response envelope. FastAPI owns transport, while page-local JavaScript owns temporary date confirmation.

**Tech Stack:** Python >=3.13, FastAPI, Pydantic, installed Pydantic AI OpenAI support, pytest/TestClient/TestModel, vanilla browser JavaScript. No additional dependencies are expected.

**Spec:** [Approved design](../specs/2026-10-29-live-extraction-design.md) and [project proposal](../../proposal.md), especially LLM Role, Data Use / Incomplete Dates, Saved Records, Searchable Text, and Human Review.

## Global Constraints

- No database, RAG, accounts, reminders, saved history, or checklist status changes.
- Read `LLM_API_TOKEN` and `LLM_API_GATEWAY` from the environment. Never write a key outside `.env`. Require `LLM_MODEL` for production extraction; no hard-coded model identifier.
- Tests never call a real model. Use `TestModel` with `override_allow_model_requests(False)`; no skipped tests or weakened checks. Keep Ruff's `max-complexity = 10`.
- Keep `GET /`, `POST /updates/analyze`, request fields `provider`/`update_text`, and response top-level fields `message`/`suggestions`/`ambiguities`.
- Valid suggestions survive unknown-requirement warnings. No applicable suggestions yields insufficient information.
- Incomplete dates resolve to the latest valid occurrence on or before the proposed start date, never relative to today. An absent start date leaves incomplete dates unset with a warning.
- Date confirmation is page-local, resets on editing or reanalysis, and never approves a status change.
- Work on a feature branch; commit each tested task. Run `uv run ruff check`, `uv run mypy`, and `uv run pytest` after changes and include output. Push, open a PR with Summary/Test plan, watch checks, never merge.

## Review Focus

1. Mixed valid/unmatched requirement output must retain valid suggestions; all-unmatched output must reach the existing empty guard (Tasks 1 and 4).
2. Day-only dates at month/year boundaries and February 29 must find real calendar dates; invalid inputs must terminate with a warning (Task 2).
3. Missing start dates must not block complete explicit dates, and explicit dates after the start date must not be silently rewritten (Tasks 2 and 4).
4. Model/configuration failures must not expose credentials, return placeholder suggestions, or be confused with empty extraction (Tasks 3 and 4).
5. Editing/reanalyzing must invalidate prior date confirmations; a stale response must not restore an earlier analysis (Task 5).

## File Responsibilities

| File | Responsibility |
| --- | --- |
| `app/agent.py` | Existing Pydantic request/output models, raw extraction models, agent construction, and extraction prompt. |
| `app/rules/__init__.py` | Compatibility export of `validate_update_suggestions`; replaces `app/rules.py`. |
| `app/rules/scope.py` | Empty-suggestion validation and canonical checklist filtering; no runtime LLM/FastAPI dependencies. |
| `app/rules/dates.py` | Frozen Python date-resolution result and calendar inference; no Pydantic/LLM/FastAPI imports. |
| `app/updates.py` | Extraction → scope → dates → final-response orchestration; no HTTP or UI code. |
| `app/main.py` | Existing page and routes, injected agent dependency, HTTP error translation, and page-local date controls. |
| `tests/conftest.py` | Automatic model-request blocking and shared deterministic agent/client fixtures. |
| `tests/test_scope.py`, `tests/test_dates.py`, `tests/test_agent.py`, `tests/test_updates.py` | Behavioral tests owned by the matching modules. |
| `tests/test_rules.py`, `tests/test_skeleton.py` | Preserve existing contracts; adapt endpoint test injection when the placeholder is removed. |
| `AGENTS.md` | Update Layout when splitting rules and adding orchestration. |
| `.gitignore`, `README.md` | Ignore `.superpowers/` companion runtime files; document configuration, running, and temporary-state boundaries. |

The `.superpowers/` directory contains throwaway brainstorming screens and a session key: do not stage it. The checked-in design/proposal are the implementation inputs. This plan does not authorize product implementation until the human reviews it and selects an execution approach.

---

### Task 1: Filter Requirement Scope Without Losing Valid Suggestions

**Files:** Replace `app/rules.py` with `app/rules/__init__.py` and `app/rules/scope.py`; create `tests/test_scope.py`; modify `AGENTS.md` Layout. Existing `tests/test_rules.py` must continue to pass unchanged.

**Interfaces:**
- Consumes `Requirement` and `SuggestedChange` from `app.agent` for type annotations only (`TYPE_CHECKING`).
- Produces `filter_suggestions(requirements: Sequence[Requirement], suggestions: Sequence[SuggestedChange]) -> tuple[list[SuggestedChange], list[str]]` and the unchanged `validate_update_suggestions(requirements, suggestions) -> None` signature.
- A target matches a checklist name after `.strip().casefold()`. Returned suggestions use the canonical checklist spelling, without mutating inputs. Unknown targets are omitted and generate an ambiguity naming the target. Do not treat a recognized requirement alone as a status change: discard suggestions whose proposed status is blank/whitespace, with a warning.

- [ ] **Step 1: Write failing tests** named `test_mixed_scope_keeps_valid_suggestions`, `test_all_unknown_reaches_empty_guard`, `test_scope_uses_canonical_names`, `test_blank_status_is_not_actionable`, and `test_scope_preserves_inputs`. Use `Requirement(name="Hawaii dental license", status="Outstanding")` and suggestions targeting that name plus `"State NED license"`. For the mixed case, pin these assertions:

```python
kept, warnings = filter_suggestions(requirements, suggestions)
assert [s.requirement for s in kept] == ["Hawaii dental license"]
assert any("State NED license" in warning for warning in warnings)
assert [item.model_dump() for item in requirements] == original_requirements
assert [item.model_dump() for item in suggestions] == original_suggestions
```

For an all-unknown list, assert `kept == []` and the existing validator raises `ValueError` matching `"(?i)insufficient information"`. Canonicalization uses a target `"  HAWAII DENTAL LICENSE  "`; blank status uses `"   "` and must be omitted with a warning.
- [ ] **Step 2: Run** `uv run pytest tests/test_scope.py tests/test_rules.py -v`; expect new tests to fail because filtering is absent, with the two existing guard tests passing.
- [ ] **Step 3: Implement** the package split and filter. Keep `app.rules.validate_update_suggestions` available through the package export; keep runtime agent imports out of the rules package. Update Layout in `AGENTS.md` to name the new responsibilities.
- [ ] **Step 4: Verify** with `uv run ruff check`, `uv run mypy`, and `uv run pytest`; expect all checks/tests to pass.
- [ ] **Step 5: Commit** only the task's files with `refactor: separate requirement scope validation`.

### Task 2: Resolve Partial Dates Deterministically

**Files:** Create `app/rules/dates.py`, `tests/test_dates.py`; extend `AGENTS.md` Layout with the date module.

**Interfaces:**
- Produces a frozen dataclass `DateResolution(proposed_date: date | None, inferred: bool, explanation: str | None, warning: str | None)`.
- Produces `resolve_date(*, year: int | None, month: int | None, day: int | None, proposed_start_date: date | None) -> DateResolution`.
- Complete dates return the stated date with `inferred=False`, even with no start date or when later than the start date. Month/day and day-only forms follow the approved backward-looking calendar rule. Unsupported shapes (for example, year+day without month), invalid components, or no possible occurrence return no date and a warning. All-missing components return no date and a missing-date warning; orchestration decides when date resolution is necessary.

- [ ] **Step 1: Write `test_resolve_date`** with `pytest.mark.parametrize` over the following exact cases. Each row supplies `year`, `month`, `day`, `start`, `expected_date`, and `expected_inferred`; parse the ISO table dates with `date.fromisoformat` and test:

```python
result = resolve_date(year=year, month=month, day=day, proposed_start_date=start)
assert (result.proposed_date, result.inferred) == (expected_date, expected_inferred)
if expected_date is None:
    assert result.warning
if expected_inferred:
    assert start is not None
    assert result.explanation is not None
    assert start.isoformat() in result.explanation
```

| year / month / day | Proposed start | Expected date / inferred |
| --- | --- | --- |
| None / 10 / 22 | 2027-01-15 | 2026-10-22 / True |
| None / None / 18 | 2027-01-15 | 2026-12-18 / True |
| None / None / 18 | 2026-11-01 | 2026-10-18 / True |
| None / None / 18 | 2026-10-18 | 2026-10-18 / True |
| None / None / 31 | 2026-03-01 | 2026-01-31 / True |
| None / 2 / 29 | 2027-01-15 | 2024-02-29 / True |
| None / 10 / 22 | None | None / False |
| 2026 / 10 / 22 | None | 2026-10-22 / False |
| 2027 / 2 / 01 | 2027-01-15 | 2027-02-01 / False |
| None / 2 / 30 | 2027-01-15 | None / False |
| None / 13 / 18 | 2027-01-15 | None / False |
| None / None / 0 | 2027-01-15 | None / False |
| 2026 / None / 18 | 2027-01-15 | None / False |
| None / None / None | 2027-01-15 | None / False |
| None / None / 18 | 0001-01-01 | None / False |

- [ ] **Step 2: Run** `uv run pytest tests/test_dates.py -v`; expect failure because the resolver is absent.
- [ ] **Step 3: Implement** `DateResolution` and `resolve_date` using `datetime.date` and `calendar`. Validate components before searching. Month/day walks backward through years; day-only walks backward through months. Bound search by the valid Gregorian calendar and Python's year range, return warnings for impossible dates, and never call `date.today()`. Keep helpers focused enough for complexity <=10.
- [ ] **Step 4: Verify** with `uv run ruff check`, `uv run mypy`, and `uv run pytest`; expect all checks/tests to pass.
- [ ] **Step 5: Commit** with `feat: resolve incomplete dates from provider start dates`.

### Task 3: Extract Structured Suggestions Through the Configured Agent

**Files:** Modify `app/agent.py`; create `tests/conftest.py`, `tests/test_agent.py`; document configuration in `README.md`.

**Interfaces:**
- Preserve existing request models. Add `MentionedDate(text: str, year: int | None = None, month: int | None = None, day: int | None = None)` and `ExtractedSuggestion(requirement: str, proposed_status: str, supporting_text: str, date: MentionedDate | None = None)`. Add `ExtractionResult(suggestions: list[ExtractedSuggestion], ambiguities: list[str])` with empty-list defaults.
- Extend final `SuggestedChange` with defaulted metadata: `date_text: str | None = None`, `date_inferred: bool = False`, `date_explanation: str | None = None`, `date_requires_confirmation: bool = False`. Do not rename its existing fields or add response top-level fields.
- Produce `AgentConfigurationError`, `build_agent(model: Model | None = None) -> Agent[None, ExtractionResult]`, and `async extract_update(request: AnalyzeUpdateRequest, agent: Agent[None, ExtractionResult]) -> ExtractionResult`.
- With an injected model, `build_agent` does not require environment configuration. Otherwise require nonblank `LLM_API_TOKEN`, `LLM_API_GATEWAY`, and `LLM_MODEL`, then construct `OpenAIProvider(base_url=..., api_key=...)`, `OpenAIChatModel`, and `Agent(output_type=ExtractionResult)`. Do not instantiate the production agent at import time. Keep credential values out of errors, prompts, and logs.

- [ ] **Step 1: Write `test_extracts_stated_components_without_inference`** using `TestModel(custom_output_args={"suggestions": [{"requirement": "Drug screening", "proposed_status": "Scheduled", "supporting_text": "scheduled on the 18th", "date": {"text": "on the 18th", "day": 18}}], "ambiguities": []})` and assert:

```python
result = asyncio.run(extract_update(request, agent))
assert result.suggestions[0].date is not None
assert result.suggestions[0].date.day == 18
assert result.suggestions[0].date.month is None
assert result.suggestions[0].date.year is None
```

Add `test_empty_extraction` asserting `suggestions == []`, `test_missing_configuration` parametrized over the three environment names and expecting `AgentConfigurationError`, and `test_injected_model_needs_no_configuration` with all three variables absent. Add `test_prompt_contains_context_without_credentials`: capture the agent run's user messages with Pydantic AI's `capture_run_messages`, serialize them with `ModelMessagesTypeAdapter.dump_json`, and assert the provider name, current requirement/status, and original update are present while a synthetic token value is absent. Never load a real token for this test.
- [ ] **Step 2: Add an autouse fixture** in `tests/conftest.py` that yields inside `override_allow_model_requests(False)`. Run `uv run pytest tests/test_agent.py -v`; expect failures for missing models/factory, never a network request. The fixture stays in force for all later tests.
- [ ] **Step 3: Implement** the extraction models and agent functions. Encode provider context and original update as structured JSON user data. Instructions require canonical checklist names, supporting excerpts, no invented status changes from general reassurance, and only date components actually stated. Return ambiguity text for missing dates or unsupported wording; Python owns inference. Keep unrelated/unknown mentions available for the deterministic scope filter rather than creating checklist requirements. Document environment-variable names and setup without writing credentials.
- [ ] **Step 4: Verify** with `uv run ruff check`, `uv run mypy`, and `uv run pytest`; expect all checks/tests to pass with real model requests disabled.
- [ ] **Step 5: Commit** with `feat: extract structured onboarding suggestions with Pydantic AI`.

### Task 4: Replace the Placeholder Endpoint With Validated Extraction

**Files:** Create `app/updates.py`, `tests/test_updates.py`; modify `app/main.py`, `tests/conftest.py`, `tests/test_skeleton.py`, and `AGENTS.md` Layout.

**Interfaces:**
- Consumes Tasks 1–3. Produce `async process_update(request: AnalyzeUpdateRequest, agent: Agent[None, ExtractionResult]) -> AnalyzeUpdateResponse` in `app/updates.py`.
- Produce `get_extraction_agent() -> Agent[None, ExtractionResult]` as the FastAPI dependency in `app/main.py`; it calls `build_agent()` lazily. Inject it into the existing POST route using `Depends`; retain the route path and response envelope.
- For each raw suggestion, create a final-shaped `SuggestedChange` candidate without resolved dates and call `filter_suggestions(requirements, [candidate])`. This preserves the association between a retained candidate and its raw date components without introducing identifiers or parallel index maps. Resolve dates only for retained candidates, then call the existing empty guard over the assembled applicable list. Carry model ambiguities, scope warnings, and retained date warnings into `ambiguities`. On the empty guard's expected `ValueError`, return HTTP 200 with an insufficient-information message, `suggestions=[]`, and retained warnings. Do not catch unrelated programming errors as insufficient information.
- Resolve dates only for a stated date mention or a status equal to `Scheduled` after trimming/case folding. Missing dates for other statuses do not generate a blanket date warning. Carry resolution warnings into ambiguities; set confirmation metadata from the resolver. Keep input context unchanged.
- Production configuration failure: HTTP 503 with a generic configuration message. Model HTTP/invalid-output failures: HTTP 502 with a generic retry message; timeouts: HTTP 504. Never expose provider bodies or credentials. Keep these HTTP mappings in the route/dependency, not rules.

- [ ] **Step 1: Write failing TestClient tests** through the actual path, with `app.dependency_overrides[get_extraction_agent]` supplying a deterministic `TestModel` agent. Use one canonical provider fixture with start `2027-01-15` and dental-license/drug-screening requirements. Name tests after these outcomes (`test_mixed_scope_response`, `test_no_actionable_suggestions`, `test_inferred_date_metadata`, `test_dates_without_start`, `test_missing_date_warning`, `test_model_errors`, `test_missing_configuration`, `test_context_unchanged`):
  - Known license + unknown NED output: status `200`, one license suggestion, and a NED warning.
  - All-unknown or empty output: status `200`, `suggestions == []`, and `"insufficient information" in message.lower()`.
  - Day `18` output: proposed date `"2026-12-18"`, original date text preserved, `date_inferred is True`, and `date_requires_confirmation is True`.
  - No start + partial date: proposed date is `None`, warning present, valid suggestion still visible. No start + complete `2026-10-22`: explicit date survives without inferred confirmation.
  - Scheduled with no date: valid suggestion plus warning. License received with no date: no missing-date warning.
  - Mock `extract_update` to raise the installed SDK's model HTTP/invalid-output exceptions and `TimeoutError`: status `502`/`504` with generic messages. Missing configuration with production dependency restored: status `503` and no token disclosure. In that same environment `GET /` still returns `200`.
  - Request/provider snapshots match after processing; response top-level fields equal `set(AnalyzeUpdateResponse.model_fields)`.
- [ ] **Step 2: Adapt the existing skeleton endpoint test** to use a shared `client` fixture in `tests/conftest.py`. That fixture overrides `get_extraction_agent` with a `TestModel` agent, opens `TestClient(app)`, and restores dependency overrides in `finally`. Keep the existing status/field assertions and page-form assertion. Run `uv run pytest tests/test_updates.py tests/test_skeleton.py -v`; expect new integration assertions to fail against the placeholder.
- [ ] **Step 3: Implement** `process_update`, lazy injection, and HTTP mappings. Use explicit typed intermediate values; keep business logic out of `app/main.py`. Preserve canonical names and supporting text while mapping raw date components to resolver results. Update Layout to include `app/updates.py`.
- [ ] **Step 4: Verify** with `uv run ruff check`, `uv run mypy`, and `uv run pytest`; expect all checks/tests to pass without production configuration or network requests.
- [ ] **Step 5: Commit** with `feat: connect update analysis to validated model extraction`.

### Task 5: Display Live Results and Confirm Inferred Dates Locally

**Files:** Modify `app/main.py`, `README.md`, `.gitignore`; extend `tests/test_skeleton.py` only for durable page contract checks, not exact HTML snapshots.

**Interfaces:**
- Consume the response contract from Tasks 3–4. Keep the existing form and endpoint. Render original update, supporting text, suggestions, ambiguities, inference explanation, and error/status feedback using `textContent` and DOM creation.
- For every inferred date, render a labeled editable date input and Confirm date button. Per-analysis state is local to the rendered suggestion: editing marks it unconfirmed; confirmation requires a valid nonempty date input and changes only its local label. There is no approval POST, storage API, or checklist mutation.
- At new submission start, clear old suggestions/confirmations, capture that submission's original text, disable duplicate submission, and retain existing error handling. Empty extraction displays insufficient information; model failures display the server's safe message. Restore the submit button on success/failure. Do not display prior results after a failed request.

- [ ] **Step 1: Keep the existing page-form test** and endpoint contract tests passing. Define a browser verification checklist before editing: inferred-date edit/confirm/reset; mixed warnings; empty result; missing start; explicit dates; safe error; unchanged checklist. Do not add brittle substring tests for labels or mock the DOM in Python.
- [ ] **Step 2: Implement** the UI in the existing page, preserving the main sections. Replace placeholder copy with synthetic-data and temporary-confirmation wording. Remove the disabled general approve/correct/reject buttons to avoid implying that workflow exists. After editing an inferred date, clear confirmation; after confirmation say it applies only to that date in this page. Reanalysis removes the old controls, preventing stale confirmations. An in-flight form cannot submit again, so stale responses cannot overtake a later submission.
- [ ] **Step 3: Document** configuration/startup and the lack of persistence in `README.md`; add `.superpowers/` to `.gitignore`. Do not add the companion runtime files, session key, `.env`, or real credentials.
- [ ] **Step 4: Verify in the browser** using a temporary, untracked runner under `/tmp` that imports `app` and `get_extraction_agent`, overrides that dependency with `build_agent(TestModel(custom_output_args=...))`, and serves the app through Uvicorn. For mixed-output/date fixture, confirm `2026-12-18`, edit it to `2026-12-17`, see confirmation clear, confirm again, then reanalyze and see fresh unconfirmed output. Check the displayed checklist never changes and refresh loses confirmation. Restart the runner with empty, unknown-only, missing-start, and error fixtures and verify the corresponding states. Test narrow and desktop widths, keyboard focus/labels, and a synthetic supporting excerpt containing `<script>` renders as text. No live model calls are needed. Stop temporary runners afterward.
- [ ] **Step 5: Verify** with `uv run ruff check`, `uv run mypy`, and `uv run pytest`; expect all checks/tests to pass. Review `git diff --check` and changed paths to ensure no credentials/runtime artifacts or unrelated changes are staged.
- [ ] **Step 6: Commit** with `feat: display extraction results and confirm inferred dates`.

## Whole-Branch Verification and Handoff

- [ ] Compare the finished change with this design and `docs/proposal.md`. Record any newly approved decisions in their proposal sections and name those sections in the PR Summary. Do not quietly broaden scope.
- [ ] Run `uv run ruff check`, `uv run mypy`, and `uv run pytest`, and record actual output plus the browser checklist results. Never claim a real-model extraction-quality evaluation from `TestModel` results.
- [ ] Push the implementation branch, create/update the PR with Summary and Test plan, and run `gh pr checks --watch`. Report the resulting PR URL and final check status; do not merge.
- [ ] Keep the production model identifier as deployment configuration. A later synthetic live-model evaluation may assess extraction quality; it is separate from automated tests and is not required to finish this slice.

## Self-Review

Spec coverage maps to Tasks 1/4 (requirement filtering and insufficient information), 2 (date policy), 3 (structured extraction/configuration), 4 (real endpoint integration and errors), and 5 (display/local confirmation and boundaries). Interfaces above define all cross-task names. Each Review Focus item has a test or browser verification step in its owning task. No product implementation is included in the documentation change that introduces this plan.
