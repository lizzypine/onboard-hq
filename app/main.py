"""Routes and the synthetic provider onboarding page."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse

from app.agent import build_agent
from app.database import (
    DatabaseConfigurationError,
    DatabasePool,
    DatabaseUnavailable,
    create_pool,
    database_url,
)
from app.models import (
    DemoRole,
    ProviderSummary,
    ReviewDecision,
    ReviewRequest,
    SavedUpdate,
    StoredProvider,
    SubmitUpdateRequest,
)
from app.repository import RecordNotFound
from app.repository.providers import ProviderRepository
from app.repository.reviews import ReviewRepository
from app.repository.updates import UpdateConflict, UpdateRepository
from app.reviews import AgentFactory, review_suggestion, submit_update
from app.rules.review import ReviewConflict, ReviewForbidden, ReviewValidationError


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncIterator[None]:
    pool: DatabasePool | None
    try:
        pool = create_pool(database_url())
    except DatabaseConfigurationError:
        pool = None
    application.state.pool = pool
    if pool is not None:
        await pool.open()
    try:
        yield
    finally:
        if pool is not None:
            await pool.close()


router = APIRouter()


def get_pool(request: Request) -> DatabasePool:
    pool: DatabasePool | None = getattr(request.app.state, "pool", None)
    if pool is None:
        raise HTTPException(503, "Database is not configured.")
    return pool


def get_repository(
    pool: Annotated[DatabasePool, Depends(get_pool)],
) -> ProviderRepository:
    return ProviderRepository(pool)


async def database_error(_request: Request, _error: Exception) -> JSONResponse:
    return JSONResponse(
        status_code=503,
        content={
            "detail": "Database is unavailable. Check configuration and migrations."
        },
    )


async def missing_record(_request: Request, _error: Exception) -> JSONResponse:
    return JSONResponse(status_code=404, content={"detail": "Record not found."})


@router.get("/providers", response_model=list[ProviderSummary])
async def providers(
    repository: Annotated[ProviderRepository, Depends(get_repository)],
) -> list[ProviderSummary]:
    return await repository.list_providers()


@router.get("/providers/{provider_id}", response_model=StoredProvider)
async def provider(
    provider_id: UUID,
    repository: Annotated[ProviderRepository, Depends(get_repository)],
) -> StoredProvider:
    return await repository.get_provider(provider_id)


PAGE = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Onboard HQ</title>
  <style>
    body { font-family: system-ui, sans-serif; margin: 0; background: #f4f6f8;
           color: #172b3a; line-height: 1.5; }
    main { max-width: 850px; margin: auto; padding: 24px; }
    section { background: white; border: 1px solid #cbd5df; border-radius: 8px;
              padding: 20px; margin: 20px 0; }
    h1, h2 { line-height: 1.2; }
    h2 { font-size: 1.25rem; margin-top: 0; }
    label { display: block; font-weight: 600; margin-bottom: 8px; }
    select, textarea, button { font: inherit; padding: 8px; }
    select, textarea { box-sizing: border-box; width: 100%; }
    textarea { min-height: 120px; }
    button { margin: 8px 8px 0 0; }
    table { width: 100%; border-collapse: collapse; }
    th, td { text-align: left; padding: 10px 4px; border-bottom: 1px solid #ddd; }
    .suggestion { border-top: 1px solid #cbd5df; padding: 16px 0; }
    #request-status { min-height: 1.5em; }
    input[type="date"] { display: block; font: inherit; padding: 8px;
                         max-width: 100%; box-sizing: border-box; }
    .date-review { background: #f1f6f8; border-radius: 6px; padding: 14px; }
    .date-review label { margin-top: 12px; }
    button:disabled { cursor: default; }
  </style>
</head>
<body>
<main>
  <h1>Onboard HQ</h1>
  <p>Provider onboarding dashboard</p>
  <p><strong>Prototype:</strong> Synthetic provider data. Updates are sent for model
     analysis. Updates and suggestions are saved; date confirmation alone does not approve a status.</p>

  <section aria-labelledby="provider-heading">
    <h2 id="provider-heading">1. Select a provider</h2>
    <label for="provider">Provider</label>
    <select id="provider">
      <option value="kekoa-ejemplo">Dr. Kekoa Ejemplo</option>
    </select>
    <p>Dentist · Proposed start date: December 1, 2026</p>
  </section>

  <section aria-labelledby="checklist-heading">
    <h2 id="checklist-heading">2. Onboarding checklist</h2>
    <table>
      <thead><tr><th scope="col">Requirement</th><th scope="col">Status</th>
        <th scope="col">Deadline</th></tr></thead>
      <tbody id="requirements"></tbody>
    </table>
    <p>Deadlines have not been set in this example.</p>
  </section>

  <section aria-labelledby="update-heading">
    <h2 id="update-heading">3. Input status update</h2>
    <form id="update-form" action="/updates/analyze" method="post">
      <label for="update-text">Original update</label>
      <textarea id="update-text" name="update_text" required
        placeholder="Enter a synthetic onboarding update"></textarea>
      <button id="submit-update" type="submit">Analyze update</button>
    </form>
    <p id="request-status" role="status" aria-live="polite"></p>
  </section>

  <section aria-labelledby="review-heading">
    <h2 id="review-heading">4. AI suggestions / human review</h2>
    <p>Submit an update to see proposed changes and supporting text.</p>
    <p>Check and confirm inferred dates in this page. Confirming a date does not
       approve a status change. The checklist remains unchanged.</p>
    <div id="review-results" aria-live="polite"></div>
  </section>
</main>
<script>
  let provider;
  let submissionKey = null;
  let requestId = null;

  function appendText(parent, tag, text) {
    const element = document.createElement(tag);
    element.textContent = text;
    parent.append(element);
    return element;
  }

  const requirements = document.getElementById("requirements");
  const providerSelect = document.getElementById("provider");
  async function refreshProvider() {
    const response = await fetch("/providers/" + providerSelect.value);
    if (!response.ok) throw new Error("Unable to load stored checklist.");
    provider = await response.json();
    requirements.replaceChildren();
    for (const requirement of provider.requirements) {
      const row = document.createElement("tr");
      appendText(row, "td", requirement.name);
      appendText(row, "td", requirement.status);
      appendText(row, "td", requirement.deadline ?? "Not set");
      requirements.append(row);
    }
  }
  async function loadProvider() {
    const response = await fetch("/providers");
    if (!response.ok) throw new Error("Unable to load providers.");
    const providers = await response.json();
    providerSelect.replaceChildren();
    for (const item of providers) {
      const option = appendText(providerSelect, "option", item.name);
      option.value = item.id;
    }
    if (!providers.length) throw new Error("No providers found. Load synthetic seed data.");
    await refreshProvider();
  }

  const form = document.getElementById("update-form");
  const submitButton = document.getElementById("submit-update");
  const status = document.getElementById("request-status");
  const results = document.getElementById("review-results");

  function appendDateReview(parent, suggestion, index) {
    const review = document.createElement("div");
    review.className = "date-review";
    appendText(review, "p", suggestion.date_explanation);
    const label = appendText(review, "label", "Check or correct inferred date");
    const input = document.createElement("input");
    input.type = "date";
    input.id = "suggestion-date-" + index;
    input.value = suggestion.proposed_date ?? "";
    input.required = true;
    label.htmlFor = input.id;
    review.append(input);
    const confirmation = appendText(review, "p", "Awaiting date confirmation.");
    confirmation.setAttribute("role", "status");
    const button = appendText(review, "button", "Confirm date");
    button.type = "button";
    input.addEventListener("input", () => {
      confirmation.textContent = "Awaiting date confirmation.";
      button.disabled = false;
    });
    button.addEventListener("click", () => {
      if (!input.reportValidity()) return;
      confirmation.textContent = "Date confirmed in this page: " + input.value +
        ". Checklist statuses are unchanged.";
      button.disabled = true;
    });
    parent.append(review);
  }

  function appendSuggestion(suggestion, index) {
    const item = document.createElement("div");
    item.className = "suggestion";
    appendText(item, "h3", suggestion.requirement);
    appendText(item, "p", "Proposed status: " + suggestion.proposed_status);
    appendText(item, "p", "Supporting text: " + suggestion.supporting_text);
    if (suggestion.date_text) {
      appendText(item, "p", "Original date wording: " + suggestion.date_text);
    }
    if (suggestion.date_requires_confirmation) {
      appendDateReview(item, suggestion, index);
    } else {
      appendText(item, "p", "Proposed date: " +
        (suggestion.proposed_date ?? "Not specified"));
    }
    results.append(item);
  }

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (submitButton.disabled) return;
    const updateText = document.getElementById("update-text").value;
    submitButton.disabled = true;
    providerSelect.disabled = true;
    status.textContent = "Analyzing update...";
    results.replaceChildren();
    let failureMessage = "Unable to analyze update. Please try again.";
    try {
      await ready;
      if (!provider) throw new Error("No stored provider is available.");
      const key = JSON.stringify([provider.id, updateText]);
      if (submissionKey !== key || !requestId) {
        submissionKey = key;
        requestId = crypto.randomUUID();
      }
      const response = await fetch(form.action, {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({provider_id: provider.id, request_id: requestId, update_text: updateText})
      });
      const data = await response.json();
      if (!response.ok) {
        if (typeof data.detail === "string") failureMessage = data.detail;
        else if (data.detail?.message) failureMessage = data.detail.message;
        throw new Error(failureMessage);
      }
      requestId = null;
      appendText(results, "h3", "Original update");
      appendText(results, "p", updateText);
      appendText(results, "p", data.message);
      data.suggestions.forEach(appendSuggestion);
      if (data.ambiguities.length) {
        appendText(results, "h3", "Warnings and ambiguities");
        for (const ambiguity of data.ambiguities) {
          appendText(results, "p", ambiguity);
        }
      }
      status.textContent = data.suggestions.length ?
        "Update and suggestions saved. Checklist statuses are unchanged." : data.message;
    } catch {
      results.replaceChildren();
      status.textContent = failureMessage;
    } finally {
      submitButton.disabled = false;
      providerSelect.disabled = false;
    }
  });
  providerSelect.addEventListener("change", () => {
    results.replaceChildren();
    refreshProvider().catch(() => { status.textContent = "Unable to load stored checklist."; });
  });
  const ready = loadProvider().catch((error) => {
    status.textContent = error.message;
    submitButton.disabled = true;
  });
</script>
</body>
</html>
"""


@router.get("/", response_class=HTMLResponse)
async def index() -> str:
    """Display the synthetic provider dashboard and update form."""
    return PAGE


def get_agent_factory() -> AgentFactory:
    """Construct the configured agent only after persisting a claimed update."""
    return build_agent


@router.post("/updates/analyze", response_model=SavedUpdate)
async def analyze_update(
    request: SubmitUpdateRequest,
    factory: Annotated[AgentFactory, Depends(get_agent_factory)],
    pool: Annotated[DatabasePool, Depends(get_pool)],
) -> SavedUpdate:
    saved = await submit_update(UpdateRepository(pool), request, factory)
    if saved.failure_category is not None:
        code = {"configuration": 503, "timeout": 504, "model": 502}[
            saved.failure_category
        ]
        raise HTTPException(
            code, {"message": saved.message, "update_id": str(saved.id)}
        )
    return saved


@router.get("/updates/{update_id}", response_model=SavedUpdate)
async def saved_update(
    update_id: UUID, pool: Annotated[DatabasePool, Depends(get_pool)]
) -> SavedUpdate:
    return await UpdateRepository(pool).get(update_id)


@router.get("/providers/{provider_id}/updates", response_model=list[SavedUpdate])
async def saved_updates(
    provider_id: UUID, pool: Annotated[DatabasePool, Depends(get_pool)]
) -> list[SavedUpdate]:
    return await UpdateRepository(pool).list_for_provider(provider_id)


async def update_conflict(_request: Request, _error: Exception) -> JSONResponse:
    return JSONResponse(
        status_code=409,
        content={
            "detail": "Request is already processing or its input has changed. Refresh saved history."
        },
    )


@router.post("/suggestions/{suggestion_id}/review", response_model=ReviewDecision)
async def record_review(
    suggestion_id: UUID,
    request: ReviewRequest,
    pool: Annotated[DatabasePool, Depends(get_pool)],
    role: Annotated[DemoRole, Header(alias="X-Demo-Role")] = "proposer",
) -> ReviewDecision:
    return await review_suggestion(ReviewRepository(pool), suggestion_id, request, role)


async def review_forbidden(_request: Request, error: Exception) -> JSONResponse:
    return JSONResponse(status_code=403, content={"detail": str(error)})


async def review_conflict(_request: Request, error: Exception) -> JSONResponse:
    return JSONResponse(status_code=409, content={"detail": str(error)})


async def review_invalid(_request: Request, error: Exception) -> JSONResponse:
    return JSONResponse(status_code=422, content={"detail": str(error)})


def create_app() -> FastAPI:
    application = FastAPI(title="Onboard HQ", lifespan=lifespan)
    application.include_router(router)
    application.add_exception_handler(DatabaseUnavailable, database_error)
    application.add_exception_handler(RecordNotFound, missing_record)
    application.add_exception_handler(UpdateConflict, update_conflict)
    application.add_exception_handler(ReviewForbidden, review_forbidden)
    application.add_exception_handler(ReviewConflict, review_conflict)
    application.add_exception_handler(ReviewValidationError, review_invalid)
    return application


app = create_app()
