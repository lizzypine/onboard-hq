# Instructions for coding agents

This project is a web app that helps community health center staff manage onboarding for new healthcare providers. It brings requirements, statuses, deadlines, and proposed start dates into one place so staff can quickly see outstanding tasks. An LLM turns free-text updates into suggested changes, which users review and approve before saving.

The project proposal is `docs/proposal.md`; keep that file unchanged. Record subsequent database design decisions in `docs/database-design.md`, distinguishing its proposed target from the implemented `db/schema.sql`. `docs/proposal-v2.pdf` contains the revised proposal and Ethan's feedback; distinguish changes incorporated into the proposal from suggestions still under consideration.

## Product constraints and proposal feedback

- Use synthetic provider records and administrative updates only. Version one excludes real employee records, forwarded-email processing, document uploads, and automated reminders.
- Load the selected provider's current requirements and statuses before interpreting an update. Do not automatically add a requirement that does not apply to that provider type.
- Account for multiple provider types, such as Dentist and Dental Hygienist. Separate type-specific requirement templates from each provider's actual checklist; template changes must not silently change existing checklists. Manager creation supports provider-only additions through the reviewed five-step modal described in `docs/superpowers/specs/2026-11-22-add-provider-walkthrough-design.md` and `docs/database-design.md`. Save requirement changes only its browser draft; final Add provider saves the whole checklist atomically. Standard rows retain their assigned membership; additions never alter templates. Other checklist exceptions and post-creation addition/removal controls remain outside scope.
- Present each suggestion with the original update and supporting text. Users must be able to approve, correct, or reject suggestions independently; only approved changes may update requirement statuses or dates. Retain original updates, suggestions, and review decisions in persistent storage.
- Use the **Sample Input Set** and **Three Acceptance Criteria** in `docs/proposal.md` when implementing and testing extraction. Include relative dates ("next Tuesday"), corrections ("actually the drug screen moved to the 29th"), and status reversals (credentialing returned for missing information becomes Incomplete). Flag ambiguous dates and keep corrections subject to human approval.
- Follow **Data Use > Incomplete Dates** in `docs/proposal.md` for date resolution: incomplete dates are anchored to the proposed start date, and unsupported wording produces a warning with no guessed date. The revised PDF's references to today's date and the upcoming month do not override this policy; resolve those differences in the spec before extending date handling.
- Include a synthetic message mentioning two providers when evaluating provider scoping. Ethan suggested this harder case, but its expected behavior is not yet specified; settle it in the spec before implementing support for updates about multiple providers.
- The licensing knowledge design in `docs/superpowers/specs/2026-11-22-licensing-knowledge-design.md` governs the approved RAG slice. Manager-reviewed source versions, immutable retained originals, extraction locators, scoped passages and pgvector indexing are implemented. Question answering and saved licensing substeps are separate slices. Use the bounded manifest and sanitized internal draft. Every draft needs explicit Manager review before publication. No original internal addresses, staff names or staff emails belong in the corpus. Neon migration and production ingestion require separate authorization.
- Ethan suggested comparing the time to answer "what's still outstanding for Dr. X?" using the current process versus the app. Keep dashboard correctness checks; investigate this additional value measure with the health center contact before setting evaluation targets.
- Anyone can propose updates; only a manager can add fictional providers, archive or restore providers, approve suggestions, or directly save checklist status/date/deadline edits. For this prototype, use a clearly labeled simulated Non-manager/Manager role switch rather than sign-in; Non-manager retains the internal `proposer` API value. Enforce it in creation, lifecycle, review, and manual save operations; it is not real access control. Manual saves require atomic immutable before/after history, stable retry identities, and shared requirement version checks.
- Persist application records in Neon PostgreSQL using `DATABASE_URL` from the environment. Manage schema changes with dbmate SQL migrations. Keep database credentials in `.env`, and use placeholder values only in `.env.example`. Automated database tests must use a separate test database rather than the configured Neon application database.
- Use Pydantic for request/response validation and structured model output. Keep authorization and business rules in plain Python and relational integrity constraints in PostgreSQL.
- The persistence and manager-review slice requires automated unit, PostgreSQL integration, and real-browser end-to-end tests, run locally and in CI. Use `TestModel` with real model requests disabled in every layer; never point automated tests at the Neon application database.
- Local/cloud semantic routing is possible future work using OpenCode at `opencode.ai` (referred to as `opencode-ai`). Investigate its integration and the routing policy before adopting it; do not add routing or change the current model gateway as part of persistence and review.

## Layout

- `app/main.py`: routes, dependency/lifecycle wiring, and HTTP error mapping. No business rules.
- `app/page.py`: page markup; `app/static/onboarding.js`: coherent provider selection/loading, creation recovery, pending suggestion content beneath matching checklist rows, completed history display, and saved-review orchestration.
- `app/static/providers.js`: Manager creation/catalog requests, frozen save recovery, coherent selection callbacks, and duplicate-name labels. No analysis or review calls.
- `app/static/provider-lifecycle.js`: inline Manager Archive/Restore controls, native archive confirmation, explicit desired-state requests, and read-only reconciliation of unconfirmed responses. No automatic write retries.
- `app/static/provider-wizard.js` and `app/static/provider-wizard.css`: native five-step modal, per-item additional requirement drafts, final review, and scoped layout. No HTTP/storage/model calls.
- `app/static/provider-recovery.js`: validated frozen creation requests in sessionStorage; no HTTP/model calls or automatic replay.
- `app/static/date-help.js`: shared Expected completion date explanation on hover/focus/tap, scoped to the active dialog when open; SQL/API fields remain named scheduled_date.
- `app/static/checklist.js`: saved checklist rows, status badges, placement of controller-supplied requirement detail nodes, one Manager edit draft, and frozen manual-save recovery. No provider/history loading, suggestion review calls, or model calls.
- `app/static/checklist-recovery.js`: validate frozen UUID-era drafts and read saved history by retained retry keys; no save POSTs or model calls. The checklist controller clears resolved drafts only after a coherent saved view loads.
- `app/static/statuses.js`: safe native status dropdown and labeled badge DOM helpers; choices and tones come from the dashboard.
- `app/static/review.js`: one suggestion's editable checklist comparison, draft date actions, validation, and manager decision callbacks. No data loading or persistence.
- `app/dependencies.py` shares the FastAPI pool dependency. `app/knowledge_routes.py` wires source endpoints.
- `app/knowledge_models.py` defines retained-source, passage, scope, operation and corpus contracts. `app/knowledge.py` orchestrates Manager review, publication and reindexing. `app/rules/knowledge.py` validates source roles, revisions, retried operations and embedding identity.
- `app/knowledge_sources.py` handles bounded manifest fetching and the explicit source CLI. `app/source_extraction.py` preserves passage text and page/section offsets. `app/embeddings.py` owns the independent, validated embedding adapter.
- `app/repository/knowledge.py` serializes source decisions and corpus changes. `knowledge_reads.py` reads coherent scope-filtered snapshots. `knowledge_writes.py` writes draft content, applicability and immutable operation receipts inside the caller's transaction.
- `app/agent.py`: the Pydantic AI agent and output models.
- `app/updates.py`: extraction, scope filtering, and date-resolution orchestration. No HTTP or UI code.
- `app/database.py`: environment configuration and PostgreSQL connection lifecycle. No routes or model calls.
- `app/models.py`: shared Pydantic context, stored-record, captured-state, and HTTP contracts; integer resource IDs and distinct UUID retry keys.
- `app/provider_models.py`: provider-creation and configured type-template catalog contracts.
- `app/checklist_models.py`: direct checklist edit request/audit records and derived dropdown option contracts, separate from stored LLM evidence.
- `app/checklist.py`: Manager-only direct-edit orchestration; no HTTP/model calls.
- `app/rules/checklist.py`: pure direct-save role, version, status, no-op, and retry identity rules.
- `app/rules/statuses.py`: shared synthetic/provider-only status choices, completion classification, and badge tones; unknown standard requirements/types retain Needs review. Unconfigured provider-only rows use the generic vocabulary with Completed meaning finished.
- `app/repository/checklist.py`: locked atomic checklist edits with append-only retryable audit history.
- `app/providers.py`: manager-only provider creation orchestration; no HTTP or model calls.
- `app/provider_lifecycle.py`: Manager archive/restore orchestration; no HTTP/model calls.
- `app/repository/provider_lifecycle.py`: provider-lock-serialized archived_at changes only; preserves assigned checklists and history.
- `app/rules/providers.py`: pure creation authorization, reviewed-template/addition validation, defaults, and immutable creation retry comparison.
- `app/rules/catalog.py`: pure normalized catalog names and reviewed-template membership fingerprints.
- `app/monitoring_models.py`: derived dashboard contracts, separate from stored provider/context snapshots.
- `app/monitoring.py`: Hawaii clock boundary and dashboard loading from one saved provider/checklist read.
- `app/rules/monitoring.py`: pure completion, deadline, and count rules with an explicit as-of date. No clock or I/O.
- `app/repository/catalog.py`: immutable complete-checklist version configuration for seeds/tests; normalized names, no administration route.
- `app/repository/provider_creation.py`: immutable creation receipt reconstruction, provider/checklist insertions, and additional definition resolution within the caller's transaction.
- `app/repository/snapshots.py`: save and reconstruct relational captured requirement state within the caller's transaction.
- `app/rules/provider_state.py`: pure lifecycle Manager authorization and archived-state write guard; archived records remain viewable.
- `app/repository/providers.py`: PostgreSQL provider/type reads and atomic template-based checklist initialization with creation retry identities; the provider/checklist SELECT is in `db/queries.py`. Repository transaction helpers are in `app/repository/__init__.py`.
- `db/queries.py`: one parameterized `fetch_provider` query returning a typed provider and its own checklist; used by production repositories and tested directly in `tests/test_queries.py`.
- `db/seed.py`: explicit, repeatable synthetic development seed; run with `python -m db.seed`. Never run at application startup. `app/seed.py` preserves the earlier CLI/imports for compatibility.
- `app/repository/updates.py`: request claims, captured provider context, and saved suggestions/history.
- `app/repository/reviews.py`: locked, atomic checklist changes and terminal review decisions.
- `app/rules/review.py`: pure role, date-confirmation, and stale-version review rules.
- `app/reviews.py`: saved analysis/review orchestration. Release database connections before model calls.
- `db/migrations/`: dbmate SQL schema changes; `db/schema.sql` is the generated schema-only snapshot.
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
bash scripts/test.sh uv run pytest # full suite with disposable local PostgreSQL
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

- Keep `docs/proposal.md` unchanged. Record database decisions in the relevant section of `docs/database-design.md` and name that section in the pull request Summary. For other scope changes, use a separate scoped design document rather than rewriting the proposal. Change only what the decision affects. Do not add a dated log, approval history, or progress notes; git keeps the history. A documented target design does not authorize implementation.
- When the user provides a revised proposal, synchronize affected agent guidance and the database design as appropriate without editing `docs/proposal.md`. Feedback phrased as an option or suggestion does not by itself settle an open question.
- `docs/proposal.md` describes the original project; `docs/database-design.md` records subsequent database decisions and target-schema changes. A design under `docs/superpowers/specs/` covers one change. If their requirements conflict beyond the explicitly recorded database decisions, ask before building.
