# Status and Deadline Monitoring

## Intent and Size

Help a manager answer what is finished, what remains, and which unfinished requirements have passed their deadlines for the selected synthetic provider. The persistence/review slice already saves authoritative checklist values and manager decisions. This is a contained dashboard slice that derives monitoring from those values, with unit, PostgreSQL integration, and browser tests. It requires no schema migration, new model call, or new write operation.

The project-wide authority is [the proposal](../../proposal.md), particularly **Data Use > Status and Deadline Monitoring**, **Human Review**, and **Testing Strategy**. This document describes the next implementation; writing it does not change the running app or Neon records.

## Decisions from the Conversation

- Use the existing fictional dentist, Dr. Kekoa Ejemplo, with concrete synthetic test cases.
- The user confirmed these results: Signed offer letter with yesterday's deadline is finished; Scheduled drug screening due next week is outstanding; Completed drug screening with yesterday's deadline is finished without an overdue warning; Incomplete credentialing with yesterday's deadline is outstanding and overdue.
- Derive completion from the saved status using requirement-specific rules. Do not add a separate manager-controlled completion field.
- The user reviewed the interactive mockup and its proposed Received-license and Approved-credentialing completion rules. Keep its four counts, checklist monitoring labels, due-today boundary, and unfamiliar-status behavior.
- Retain synthetic-only records, simulated roles, and the existing independent approval/correction/rejection flow.

## Approaches

1. **Derive completion from the approved status — selected.** A small explicit rule set interprets the current saved status for each requirement. This matches the confirmed examples and adds no parallel value for managers to maintain. Unknown wording must remain visibly uncertain.
2. **Separate completion field — considered but not selected.** A manager marks completion independently of status wording. It would allow arbitrary wording but add persistent state, edit/review behavior, and potential disagreement between status and completion.

Do not standardize all model output into a new closed status vocabulary in this slice. Existing proposals and manager corrections remain free text. The monitoring classifier recognizes only its configured examples and displays uncertainty for the rest.

## Goals and Boundaries

Add an informative Monitoring column and Finished, Remaining, Overdue, and Needs review counts to the selected provider's checklist. Preserve the original status, requirement date, deadline, and original update/review evidence. Compute all indicators in plain Python from saved data.

Do not add provider/checklist administration, deadline entry/editing, reminder delivery, automatic readiness judgments, status rewriting, rule-management screens, authentication, checklist exceptions, additional provider fixtures, or local/cloud model routing. No monitoring result writes a checklist value, decision, version, or audit record. Pending suggestions, rejected suggestions, and the simulated role switch do not change monitoring inputs.

Do not populate real application deadlines from the mockup. Existing seed/checklist records keep their existing values, including null deadlines. Synthetic deadline variations belong in guarded test fixtures. With null deadlines the app still shows completion/counts and correctly produces no overdue warning.

## Completion Rules

Support the existing canonical Dentist type and five canonical requirement names. Type/name matching uses those stored canonical names; other types or requirements need review even when a status happens to match one below. Do not apply a dentist rule to a different type with a similarly named requirement.

The finished mappings were shown in the accepted mockup. The explicit unfinished sets below are the author's proposed implementation defaults for this prototype, including all current seed states and the confirmed nonfinished scenarios:

| Requirement | Finished statuses | Known unfinished statuses |
| --- | --- | --- |
| Offer letter | Signed | Pending, Outstanding, Incomplete |
| Hawaii dental license | Received | Pending, Outstanding, Incomplete |
| Drug screening | Completed | Scheduled, Pending, Outstanding, Incomplete |
| State NED license | Received | Outstanding, Pending, Incomplete |
| Insurance credentialing | Approved | Pending, Submitted, Outstanding, Incomplete |

Compare status text using surrounding-whitespace trimming and case folding, without altering the stored value. Do not use substring matching, an LLM, fuzzy matching, or inferred synonyms. For example, ` completed ` matches drug-screen Completed; `Not completed` and `Completed?` do not. `Completed` on an offer letter is not the configured Signed status and needs review.

A requirement has one completion classification: `finished`, `outstanding`, or `needs_review`. An empty/otherwise unknown saved status receives `needs_review` if encountered. Keep normal repository validation and safe-error behavior for malformed records; do not silently repair database values. Unknown type/name/status combinations show the raw saved wording and an explanation that the completion rule needs review. This is different from an unreviewed model suggestion.

These are synthetic prototype rules, not a validated licensing or health-center policy. Add more actual workflow mappings only after validating them with the contact and updating the spec/tests.

## Deadline Rules and Clock

Use the requirement's saved `deadline` only. Its `scheduled_date` and the provider's proposed start date cannot substitute for a missing deadline.

The author proposes `Pacific/Honolulu` as the fixed monitoring time zone for this Hawaii prototype. Capture the current Hawaii date once per dashboard response and pass that explicit `as_of_date` to the pure rules. Do not depend on the host's local time zone or browser clock. Display the as-of date and Hawaii time-zone label so a long-open page does not imply freshly computed data.

| Completion | Deadline | Monitoring result |
| --- | --- | --- |
| Finished | Any or missing | Finished; no overdue warning |
| Outstanding | Before as-of date | Overdue |
| Outstanding | On as-of date | Outstanding — due today |
| Outstanding | After as-of date | Outstanding |
| Outstanding | Missing | Outstanding; displayed deadline remains Not set |
| Needs review | Before as-of date | Deadline passed — needs review |
| Needs review | Today, future, or missing | Needs review |

Keep completion and deadline assessment distinct in typed results. An unknown completion is never asserted to be finished or confirmed overdue. Its passed deadline remains conspicuous through the combined review label.

No grace period or due-soon threshold is introduced. Equality with today is not overdue. The current date used here has no effect on incomplete-date inference, which still uses the proposed start date and has no today fallback.

## Counts and Display

For the selected provider, let total be the number of saved requirements:

- Finished: number classified finished.
- Remaining: total minus Finished, including both known unfinished and Needs review.
- Overdue: known unfinished requirements with a deadline before the as-of date.
- Needs review: requirements whose completion classification is unknown.

Overdue and Needs review are subsets of Remaining, not additional requirements to add to it. An empty checklist produces zero counts and an explicit empty message, not a readiness claim. Never describe even a fully finished checklist as permission to start work.

Place the four counts above the existing checklist and append its Monitoring column. Retain the current status, requirement date, and deadline columns. Use text labels alongside color, an accessible table header, and an internally scrollable table on narrow screens. Include a short explanation that Remaining includes uncertain items and that Needs review concerns completion rules.

Retain the existing proposal and manager-review sections. Recompute the dashboard when the provider loads/changes, Refresh data is used, or the existing workflow reloads server state after analysis/review. Rejection and a role switch must not alter the counts. No new polling or automatic midnight refresh is included; the as-of label and existing Refresh data action make the snapshot explicit. Do not show the mockup's scenario buttons or preview-date picker in the app.

## Data Flow and Responsibilities

The author proposes an additive read endpoint such as `GET /providers/{provider_id}/dashboard`. Return the provider's saved checklist and its derived monitoring in one typed response. Fetch the provider/checklist once using the existing repository query, capture the as-of date once, and derive row results and counts from that same returned model. Do not fetch checklist and monitoring separately and join potentially different versions in the browser.

Preserve the existing provider/list/history/write contracts. In particular, do not add clock-dependent fields to `StoredProvider` or its persisted context snapshots. A separate dashboard response can contain the unchanged StoredProvider plus monitoring metadata, requirement IDs/classifications, and counts. History may continue loading through its existing endpoint; existing row-lock/version checks remain authoritative for writes.

- `app/rules/monitoring.py`: pure status/completion, deadline, and count rules with explicit inputs. No clock access, FastAPI, SQL, or LLM client.
- A small application service, proposed as `app/monitoring.py`: capture/convert the clock, load the stored provider, and construct validated dashboard output.
- Shared Pydantic contracts: define the dashboard and monitoring output separately from stored snapshots; split contracts by responsibility if needed and update AGENTS.md when modules actually change.
- `app/main.py`: the read route, dependency wiring, and existing error mapping. No completion or deadline rules.
- `app/page.py` and `app/static/onboarding.js`: display the typed server results and keep the existing submission/review behavior.

Missing provider IDs return 404, malformed IDs return 422, and database/schema/configuration errors use the existing safe 503 behavior. Accept no browser-supplied status, checklist, as-of date, or completion flag as authoritative monitoring input. No schema migration, new dependency, Neon mutation, or model invocation is needed for this slice.

The successful-analysis/failed-refresh request-ID preservation from the prior slice remains intact. On a failed dashboard refresh, do not combine fresh indicators with old checklist values or report that a saved review/analysis failed. A previously displayed snapshot may remain only as a whole, with its as-of label and a visible refresh error; the existing initial-load failure behavior may instead clear the view. Do not invent zero counts as a fallback for unavailable data.

## Verification

All automated tests use isolated loopback PostgreSQL and deterministic `TestModel` where extraction is exercised; real model requests remain disabled in both pytest and the browser server. No automated or manual check in this slice writes to Neon.

### Unit Tests

Turn the four agreed scenarios into failing tests before implementation. Cover every finished mapping and explicit unfinished set, whitespace/case normalization, status reversals, misleading substrings, unknown statuses/types/requirements, missing/today/future/past deadlines, scheduled dates that differ from deadlines, missing proposed start dates, and counts including unknown completion. Pass explicit dates into pure rules. Test clock conversion around Hawaii midnight separately from rule classification.

### PostgreSQL Integration Tests

Use stored versions of the fictional dentist with synthetic statuses/deadlines in the guarded test database. Verify dashboard output matches that saved checklist and computes counts from it; repeated reads make no writes. Assert pending or rejected suggestions do not change monitoring, approved changes do, and a later approved Incomplete reversal returns a finished item to Remaining/Overdue when appropriate. Preserve version/history/seed behavior and safe 404/422/503 responses. Test an unknown provider type without adopting dentist completion rules.

### Browser Tests

Use a controlled clock through test-only dependency injection, without a production date override or new fixture endpoint. Exercise the four scenarios, labels/counts after approval and refresh, completion reversal, unknown status with a past deadline, due-today behavior, and missing deadlines. Verify safe rendering of unfamiliar status text, accessible labels, narrow layouts, initial-load failure, and saved-analysis/failed-dashboard-refresh retry behavior. Preserve the real-server-restart persistence coverage; indicators should be recomputed from the saved values after restart.

Include all layers in the existing local/CI pytest run and retain Ruff and mypy as required checks. No skipped tests, real model calls, weakening of checks, or application-database test targets. Keep browser test infrastructure separate from production routes and configuration.

## Left to the Builder

Choose exact DTO names, the additive route's final name, clock dependency signatures, small helper boundaries, accessible visual details consistent with the mockup, and focused test-file organization. Keep server-derived checklist/monitoring coherence, explicit unknown handling, fixed Hawaii date boundaries, preserved write/snapshot contracts, and the agreed acceptance cases. Do not broaden the completion vocabulary, infer deadlines, add a deadline editor, overwrite existing seed data, or generalize the dentist's rules to other provider types without another product decision.
