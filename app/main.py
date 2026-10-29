"""Routes and a basic page for the provider onboarding skeleton."""

from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic_ai import Agent
from pydantic_ai.exceptions import (
    ModelAPIError,
    ModelTimeoutError,
    UnexpectedModelBehavior,
)

from app.agent import (
    AgentConfigurationError,
    AnalyzeUpdateRequest,
    AnalyzeUpdateResponse,
    ExtractionResult,
    build_agent,
)
from app.updates import process_update

app = FastAPI(title="Onboard HQ")

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
  </style>
</head>
<body>
<main>
  <h1>Onboard HQ</h1>
  <p>Provider onboarding dashboard</p>
  <p><strong>Prototype:</strong> Synthetic data and fixed example suggestions.
     Updates are not analyzed or saved.</p>

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
    <p>Submit an update to display the fixed placeholder response.</p>
    <p>Approve, correct, and reject controls are disabled in this skeleton.</p>
    <div id="review-results" aria-live="polite"></div>
  </section>
</main>
<script>
  const provider = {
    provider_id: "kekoa-ejemplo",
    name: "Dr. Kekoa Ejemplo",
    provider_type: "Dentist",
    proposed_start_date: "2026-12-01",
    requirements: [
      {name: "Offer letter", status: "Signed", deadline: null},
      {name: "Hawaii dental license", status: "Received", deadline: null},
      {name: "Drug screening", status: "Scheduled", deadline: null},
      {name: "State NED license", status: "Outstanding", deadline: null},
      {name: "Insurance credentialing", status: "Pending", deadline: null}
    ]
  };

  function appendText(parent, tag, text) {
    const element = document.createElement(tag);
    element.textContent = text;
    parent.append(element);
    return element;
  }

  const requirements = document.getElementById("requirements");
  for (const requirement of provider.requirements) {
    const row = document.createElement("tr");
    appendText(row, "td", requirement.name);
    appendText(row, "td", requirement.status);
    appendText(row, "td", requirement.deadline ?? "Not set");
    requirements.append(row);
  }

  const form = document.getElementById("update-form");
  const submitButton = document.getElementById("submit-update");
  const status = document.getElementById("request-status");
  const results = document.getElementById("review-results");

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const updateText = document.getElementById("update-text").value;
    submitButton.disabled = true;
    status.textContent = "Loading placeholder response...";
    results.replaceChildren();
    try {
      const response = await fetch(form.action, {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({provider, update_text: updateText})
      });
      if (!response.ok) {
        throw new Error("The placeholder response could not be loaded.");
      }
      const data = await response.json();
      appendText(results, "h3", "Original update");
      appendText(results, "p", updateText);
      appendText(results, "p", data.message);
      for (const suggestion of data.suggestions) {
        const item = document.createElement("div");
        item.className = "suggestion";
        appendText(item, "h3", suggestion.requirement);
        appendText(item, "p", "Proposed status: " + suggestion.proposed_status);
        appendText(item, "p", "Proposed date: " +
          (suggestion.proposed_date ?? "Not specified"));
        appendText(item, "p", "Supporting text: " + suggestion.supporting_text);
        for (const label of ["Approve", "Correct", "Reject"]) {
          const button = appendText(item, "button", label);
          button.type = "button";
          button.disabled = true;
        }
        results.append(item);
      }
      appendText(results, "h3", "Ambiguities");
      for (const ambiguity of data.ambiguities) {
        appendText(results, "p", ambiguity);
      }
      status.textContent = "Placeholder response displayed. Nothing was saved.";
    } catch (error) {
      status.textContent = "Unable to load the placeholder response. Try again.";
    } finally {
      submitButton.disabled = false;
    }
  });
</script>
</body>
</html>
"""


@app.get("/", response_class=HTMLResponse)
async def index() -> str:
    """Display the synthetic provider dashboard and update form."""
    return PAGE


def get_extraction_agent() -> Agent[None, ExtractionResult]:
    """Create the configured agent only when analysis is requested."""
    try:
        return build_agent()
    except AgentConfigurationError:
        raise HTTPException(503, "Model analysis is not configured.") from None


@app.post("/updates/analyze", response_model=AnalyzeUpdateResponse)
async def analyze_update(
    request: AnalyzeUpdateRequest,
    agent: Annotated[Agent[None, ExtractionResult], Depends(get_extraction_agent)],
) -> AnalyzeUpdateResponse:
    """Analyze an update and translate model failures into safe HTTP errors."""
    try:
        return await process_update(request, agent)
    except (TimeoutError, ModelTimeoutError):
        raise HTTPException(504, "Analysis timed out. Please try again.") from None
    except (ModelAPIError, UnexpectedModelBehavior):
        raise HTTPException(502, "Unable to analyze update. Please try again.") from None
