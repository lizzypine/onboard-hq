"use strict";

import {renderReviewControls} from "./review.js";
import {providerLabel, setupProviderCreation} from "./providers.js";
import {setupChecklist} from "./checklist.js";

const providerSelect = document.getElementById("provider");
const roleSelect = document.getElementById("demo-role");
const submitButton = document.getElementById("submit-update");
const refreshButton = document.getElementById("refresh-data");
const updateText = document.getElementById("update-text");
const status = document.getElementById("request-status");
const results = document.getElementById("review-results");
const state = {provider: null, monitoring: null, history: [], edits: [], checklistOptions: [], busy: false, generation: 0, pending: null, preferredProviderId: null};
let creation = null;
let checklist = null;
const disclosure = document.getElementById("review-disclosure");
disclosure.open = false;

function text(parent, tag, value) {
  const element = document.createElement(tag);
  element.textContent = value;
  parent.append(element);
  return element;
}

async function api(path, options = {}) {
  const response = await fetch(path, options);
  const data = await response.json();
  if (!response.ok) {
    const detail = typeof data.detail === "string" ? data.detail : data.detail?.message;
    const message = detail || "The request could not be completed. Please try again.";
    const error = new Error(message);
    error.status = response.status;
    error.savedUpdateId = data.detail?.update_id;
    throw error;
  }
  return data;
}

function setBusy(value) {
  state.busy = value;
  providerSelect.disabled = value || !state.provider;
  roleSelect.disabled = value;
  refreshButton.disabled = value;
  submitButton.disabled = value || !state.provider;
  document.querySelectorAll(".review-fields").forEach(element => { element.disabled = value; });
  creation?.setBusy(value);
  checklist?.setBusy(value);
}

function renderMonitoring() {
  const summary = document.getElementById("monitoring-summary");
  summary.hidden = !state.monitoring;
  const asOf = document.getElementById("monitoring-as-of");
  asOf.textContent = state.monitoring ? "As of " + state.monitoring.as_of_date + " · Hawaii (" + state.monitoring.time_zone + ")" : "";
  for (const key of ["finished", "remaining", "overdue", "needs_review"]) {
    document.getElementById("count-" + key).textContent = state.monitoring ? state.monitoring.counts[key] : "";
  }
}

function renderChecklist() {
  document.getElementById("provider-description").textContent =
    state.provider ? state.provider.provider_type + " · Proposed start: " + (state.provider.proposed_start_date || "Not set") : "";
  renderMonitoring();
  document.getElementById("empty-checklist").hidden = !state.provider || state.provider.requirements.length > 0;
  checklist?.render(state.provider, state.monitoring, state.checklistOptions);
}

function option(select, value, label) {
  const item = text(select, "option", label);
  item.value = value;
  return item;
}

async function decide(suggestion, body) {
  if (state.busy) return;
  setBusy(true);
  let saved = false;
  try {
    await api("/suggestions/" + suggestion.id + "/review", {
      method: "POST", headers: {"Content-Type": "application/json", "X-Demo-Role": roleSelect.value},
      body: JSON.stringify(body)
    });
    saved = true;
    await loadState();
    status.textContent = "Manager decision saved. The checklist and history are up to date.";
  } catch (error) {
    status.textContent = saved ? "Decision saved, but the view could not refresh. Refresh data before continuing." : error.message;
    if (error.status === 409) {
      try { await loadState(); } catch { /* Keep the conflict visible; never invent current data. */ }
    }
  } finally { setBusy(false); }
}

function renderSuggestion(parent, suggestion, completed) {
  const card = text(parent, "article", "");
  card.className = "suggestion";
  card.setAttribute("aria-label", suggestion.requirement);
  text(card, "h4", suggestion.requirement);
  const canReview = !suggestion.decision && completed && roleSelect.value === "manager";
  if (!canReview) {
    text(card, "p", "Proposed status: " + suggestion.proposed_status);
    text(card, "p", "Proposed date: " + (suggestion.proposed_date || "Not specified"));
  }
  text(card, "blockquote", suggestion.supporting_text);
  if (suggestion.date_text) text(card, "p", "Original date wording: " + suggestion.date_text);
  if (suggestion.date_explanation) text(card, "p", "Original inference: " + suggestion.date_explanation);
  if (suggestion.decision) {
    const decision = suggestion.decision;
    text(card, "p", {approved: "Approved", corrected: "Approved with corrections", rejected: "Rejected"}[decision.outcome]);
    if (decision.outcome !== "rejected") {
      text(card, "p", "Applied status: " + decision.applied_status);
      text(card, "p", "Applied date: " + (decision.applied_scheduled_date || "Not set"));
    } else text(card, "p", "Checklist unchanged by this decision.");
    text(card, "p", "Reviewed: " + new Date(decision.reviewed_at).toLocaleString());
  } else if (canReview) {
    renderReviewControls(card, suggestion, state.provider.requirements.find(r => r.id === suggestion.requirement_id),
      {busy: state.busy, onDecide: decide,
        statusChoices: state.checklistOptions.find(r => r.requirement_id === suggestion.requirement_id)?.statuses || []});
  } else text(card, "p", completed ? "Awaiting manager review." : "Analysis is unfinished; this cannot be reviewed.");
}

function renderHistory() {
  results.replaceChildren();
  const pending = state.history.reduce((count, update) => count + (update.processing_state === "completed" ? update.suggestions.filter(s => !s.decision).length : 0), 0);
  document.getElementById("pending-suggestions").textContent = pending + " pending suggestion" + (pending === 1 ? "" : "s") + (state.edits.length ? " · " + state.edits.length + " checklist edit" + (state.edits.length === 1 ? "" : "s") : "");
  if (!state.history.length && !state.edits.length) text(results, "p", "No saved updates yet.");
  const entries = [...state.history.map(record => ({kind: "update", record})), ...state.edits.map(record => ({kind: "edit", record}))]
    .sort((a, b) => Date.parse(b.record.created_at) - Date.parse(a.record.created_at) || b.record.id.localeCompare(a.record.id));
  for (const entry of entries) {
    if (entry.kind === "edit") { renderManualEdit(entry.record); continue; }
    const update = entry.record;
    const group = text(results, "div", "");
    group.className = "update";
    text(group, "h3", "Original update");
    text(group, "blockquote", update.update_text);
    text(group, "p", "Submitted: " + new Date(update.created_at).toLocaleString());
    text(group, "p", update.processing_state === "processing" ? "Analysis unfinished. No checklist changes were applied." : update.message);
    if (update.ambiguities.length) {
      text(group, "h4", "Warnings and ambiguities");
      const list = text(group, "ul", "");
      update.ambiguities.forEach(warning => text(list, "li", warning));
    }
    update.suggestions.forEach(suggestion => renderSuggestion(group, suggestion, update.processing_state === "completed"));
  }
}

function renderManualEdit(edit) {
  const card = text(results, "article", "");
  card.className = "update manual-edit-history";
  card.setAttribute("aria-label", "Manager checklist edit: " + edit.requirement_name);
  text(card, "h3", "Manager checklist edit");
  text(card, "p", edit.requirement_name);
  for (const [label, field] of [["Status", "status"], ["Requirement date", "scheduled_date"], ["Deadline", "deadline"]]) {
    if (edit["previous_" + field] !== edit["applied_" + field]) text(card, "p", label + ": " + (edit["previous_" + field] || "Not set") + " → " + (edit["applied_" + field] || "Not set"));
  }
  text(card, "p", "Saved by simulated Manager: " + new Date(edit.created_at).toLocaleString());
}

async function loadState() {
  const id = providerSelect.value;
  const generation = ++state.generation;
  const [dashboard, history, edits] = await Promise.all([api("/providers/" + id + "/dashboard"), api("/providers/" + id + "/updates"), api("/providers/" + id + "/checklist-edits")]);
  if (generation !== state.generation || providerSelect.value !== id) return;
  state.provider = dashboard.provider;
  state.monitoring = dashboard.monitoring;
  state.history = history;
  state.edits = edits;
  state.checklistOptions = dashboard.checklist_options;
  renderChecklist();
  renderHistory();
  checklist?.onSnapshotLoaded();
}

function clearSnapshot() {
  ++state.generation;
  state.provider = null;
  state.monitoring = null;
  state.history = [];
  state.edits = [];
  state.checklistOptions = [];
  renderChecklist();
  renderHistory();
}

async function initialize(preferredId = state.preferredProviderId) {
  const selected = preferredId || providerSelect.value;
  setBusy(true);
  clearSnapshot();
  try {
    const providers = await api("/providers");
    providerSelect.replaceChildren();
    providers.forEach(provider => option(providerSelect, provider.id, providerLabel(provider, providers)));
    if (providers.some(provider => provider.id === selected)) providerSelect.value = selected;
    if (!providers.length) {
      status.textContent = "No providers yet. A manager can add a fictional provider when templates are configured.";
      return false;
    }
    await loadState();
    state.preferredProviderId = null;
    creation?.onProviderLoaded(state.provider.id);
    status.textContent = "Saved checklist and review history loaded.";
    return true;
  } catch {
    clearSnapshot();
    status.textContent = "Saved data is unavailable. Try Refresh data or ask the administrator.";
    return false;
  } finally { setBusy(false); }
}

document.getElementById("update-form").addEventListener("submit", async event => {
  event.preventDefault();
  if (state.busy || !state.provider) return;
  const bodyText = updateText.value;
  const key = JSON.stringify([state.provider.id, bodyText]);
  if (!state.pending || state.pending.key !== key) state.pending = {key, id: crypto.randomUUID()};
  setBusy(true);
  status.textContent = "Analyzing update…";
  let saved = false;
  try {
    await api("/updates/analyze", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({provider_id: state.provider.id, request_id: state.pending.id, update_text: bodyText})});
    saved = true;
    await loadState();
    state.pending = null;
    status.textContent = "Update and suggestions saved. Open Suggestions and review history to review pending suggestions.";
  } catch (error) {
    if (error.savedUpdateId) state.pending = null;
    if (!saved) {
      try { await loadState(); } catch { /* Preserve the last known view and the visible error. */ }
    }
    status.textContent = saved ? "Update saved, but the view could not refresh. Refresh data or retry this submission." : error.message;
  } finally { setBusy(false); }
});

updateText.addEventListener("input", () => { state.pending = null; });
checklist = setupChecklist({api, roleSelect, setBusy, onSaved: loadState});
creation = setupProviderCreation({api, roleSelect, setBusy, onCreated: async id => {
  state.preferredProviderId = id;
  updateText.value = "";
  state.pending = null;
  disclosure.open = false;
  if (!await initialize(id)) throw new Error("Saved provider could not load.");
  providerSelect.focus();
}});
roleSelect.addEventListener("change", () => { renderHistory(); creation.syncRole(); checklist.syncRole(); });
providerSelect.addEventListener("change", () => {
  state.preferredProviderId = null;
  updateText.value = "";
  state.pending = null;
  disclosure.open = false;
  initialize();
});
refreshButton.addEventListener("click", () => initialize());
initialize();
