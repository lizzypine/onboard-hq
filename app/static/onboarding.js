"use strict";

import {renderReviewControls} from "./review.js?v=4";
import {providerLabel, setupProviderCreation} from "./providers.js?v=4";
import {setupChecklist} from "./checklist.js?v=7";
import {setupDateHelp} from "./date-help.js?v=4";
import {setupProviderLifecycle} from "./provider-lifecycle.js?v=2";
import {setupAskAI} from "./ask-ai.js";
import {setupKnowledgeManager} from "./knowledge-manager.js";

setupDateHelp();

const providerSelect = document.getElementById("provider");
const roleSelect = document.getElementById("demo-role");
const submitButton = document.getElementById("submit-update");
const refreshButton = document.getElementById("refresh-data");
const updateText = document.getElementById("update-text");
const status = document.getElementById("request-status");
const results = document.getElementById("review-results");
const pendingDetails = new Map();
const state = {provider: null, monitoring: null, history: [], edits: [], checklistOptions: [], busy: false, generation: 0, pending: null, preferredProviderId: null};
let creation = null;
let checklist = null;
let lifecycle = null;
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
    error.code = data.code;
    error.savedUpdateId = data.detail?.update_id;
    throw error;
  }
  return data;
}

function setBusy(value) {
  state.busy = value;
  providerSelect.disabled = value || !state.provider;
  document.getElementById("provider-state").disabled = value;
  roleSelect.disabled = value;
  refreshButton.disabled = value;
  submitButton.disabled = value || !state.provider || Boolean(state.provider.archived_at);
  document.querySelectorAll(".review-fields").forEach(element => {
    element.disabled = value || !state.provider || Boolean(state.provider.archived_at);
  });
  creation?.setBusy(value);
  checklist?.setBusy(value);
  lifecycle?.setBusy(value);
  askAI.setBusy(value);
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
    state.provider ? state.provider.provider_type + " · Proposed start: " + (state.provider.proposed_start_date || "Not set") + (state.provider.archived_at ? " · Archived — viewing only" : "") : "";
  renderMonitoring();
  document.getElementById("empty-checklist").hidden = !state.provider || state.provider.requirements.length > 0;
  checklist?.render(state.provider, state.monitoring, state.checklistOptions);
  lifecycle?.render(state.provider);
}

function option(select, value, label) {
  const item = text(select, "option", label);
  item.value = value;
  return item;
}

async function decide(suggestion, body) {
  if (state.busy || state.provider?.archived_at) return;
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

function renderSuggestion(parent, suggestion, completed, update = null) {
  const card = text(parent, "article", "");
  card.className = "suggestion";
  card.setAttribute("aria-label", suggestion.requirement);
  text(card, "h4", suggestion.requirement);
  if (update) renderUpdateEvidence(card, update, "h5");
  const canReview = !suggestion.decision && completed && roleSelect.value === "manager";
  if (!canReview) {
    text(card, "p", "Proposed status: " + suggestion.proposed_status);
    text(card, "p", "Proposed date: " + (suggestion.proposed_date || "Not specified"));
  }
  text(card, "h5", "Supporting text");
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
      {busy: state.busy || Boolean(state.provider.archived_at), onDecide: decide,
        statusChoices: state.checklistOptions.find(r => r.requirement_id === suggestion.requirement_id)?.statuses || []});
  } else text(card, "p", completed ? "Awaiting manager review." : "Analysis is unfinished; this cannot be reviewed.");
}

function renderUpdateEvidence(parent, update, heading = "h3") {
  text(parent, heading, "Original update");
  text(parent, "blockquote", update.update_text);
  text(parent, "p", "Submitted: " + new Date(update.created_at).toLocaleString());
  text(parent, "p", update.processing_state === "processing" ? "Analysis unfinished. No checklist changes were applied." : update.message);
  if (update.ambiguities.length) {
    text(parent, heading, "Warnings and ambiguities");
    const list = text(parent, "ul", "");
    update.ambiguities.forEach(warning => text(list, "li", warning));
  }
}

function renderPendingSuggestion(suggestion, update) {
  let container = pendingDetails.get(suggestion.requirement_id);
  if (!container) {
    container = document.createElement("div");
    container.className = "requirement-suggestion-content";
    text(container, "h3", "Pending suggestions");
    pendingDetails.set(suggestion.requirement_id, container);
  }
  renderSuggestion(container, suggestion, true, update);
}

function renderReviews() {
  results.replaceChildren();
  pendingDetails.clear();
  const pending = state.history.reduce((count, update) => count + (update.processing_state === "completed" ? update.suggestions.filter(s => !s.decision).length : 0), 0);
  document.getElementById("pending-suggestions").textContent = pending + " pending suggestion" + (pending === 1 ? "" : "s");
  if (!state.history.length && !state.edits.length) text(results, "p", "No saved updates yet.");
  const entries = [...state.history.map(record => ({kind: "update", record})), ...state.edits.map(record => ({kind: "edit", record}))]
    .sort((a, b) => Date.parse(b.record.created_at) - Date.parse(a.record.created_at) || b.kind.localeCompare(a.kind) || b.record.id - a.record.id);
  for (const entry of entries) {
    if (entry.kind === "edit") { renderManualEdit(entry.record); continue; }
    const update = entry.record;
    const group = text(results, "div", "");
    group.className = "update";
    renderUpdateEvidence(group, update);
    const completed = update.processing_state === "completed";
    if (completed && update.suggestions.some(s => !s.decision)) text(group, "p", "Pending suggestions are shown in the Onboarding checklist.");
    update.suggestions.forEach(suggestion => {
      if (completed && !suggestion.decision) renderPendingSuggestion(suggestion, update);
      else renderSuggestion(group, suggestion, completed);
    });
  }
}

function renderManualEdit(edit) {
  const card = text(results, "article", "");
  card.className = "update manual-edit-history";
  card.setAttribute("aria-label", "Manager checklist edit: " + edit.requirement_name);
  text(card, "h3", "Manager checklist edit");
  text(card, "p", edit.requirement_name);
  for (const [label, field] of [["Status", "status"], ["Expected completion date", "scheduled_date"], ["Deadline", "deadline"]]) {
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
  askAI.syncProvider(state.provider);
  renderReviews();
  renderChecklist();
  checklist?.onSnapshotLoaded(state.edits);
}

function clearSnapshot() {
  ++state.generation;
  state.provider = null;
  state.monitoring = null;
  state.history = [];
  state.edits = [];
  state.checklistOptions = [];
  askAI.syncProvider(null);
  renderReviews();
  renderChecklist();
}

async function initialize(preferredId = state.preferredProviderId) {
  const selected = preferredId || providerSelect.value;
  setBusy(true);
  clearSnapshot();
  try {
    const providers = await api("/providers?state=" + document.getElementById("provider-state").value);
    providerSelect.replaceChildren();
    providers.forEach(provider => option(providerSelect, provider.id, providerLabel(provider, providers)));
    if (providers.some(provider => String(provider.id) === String(selected))) providerSelect.value = selected;
    if (!providers.length) {
      status.textContent = document.getElementById("provider-state").value === "archived"
        ? "No archived providers. Choose Active to view onboarding providers."
        : "No active providers. Choose Archived to view or restore providers, or ask a manager to add a fictional provider.";
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
  if (state.busy || !state.provider || state.provider.archived_at) return;
  const bodyText = updateText.value;
  const key = JSON.stringify([state.provider.id, bodyText]);
  if (!state.pending || state.pending.key !== key) state.pending = {key, id: crypto.randomUUID()};
  setBusy(true);
  status.textContent = "Analyzing update…";
  let saved = false;
  try {
    const analyzed = await api("/updates/analyze", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({provider_id: state.provider.id, request_id: state.pending.id, update_text: bodyText})});
    saved = true;
    await loadState();
    state.pending = null;
    const hasPending = state.history.some(update => update.id === analyzed.id && update.processing_state === "completed" && update.suggestions.some(s => !s.decision));
    status.textContent = hasPending
      ? "Update and suggestions saved. Review pending suggestions beneath their requirements in the Onboarding checklist."
      : "Update saved. No pending suggestions from this update. Open Review history for the saved result and any warnings.";
  } catch (error) {
    if (error.savedUpdateId) state.pending = null;
    if (!saved) {
      try { await loadState(); } catch { /* Preserve the last known view and the visible error. */ }
    }
    status.textContent = saved ? "Update saved, but the view could not refresh. Refresh data or retry this submission." : error.message;
  } finally { setBusy(false); }
});

updateText.addEventListener("input", () => { state.pending = null; });
const getProvider = () => state.provider;
const getRole = () => roleSelect.value;
const askAI = setupAskAI({api, getProvider, getRole,
  onBindingsChanged: () => checklist.refreshRequirementDetails()});
const knowledge = setupKnowledgeManager({api, getProvider, getRole});

function requirementDetails(requirement) {
  const pending = pendingDetails.get(requirement.id);
  const action = askAI.requirementAction(requirement);
  if (!pending || !action) return pending || action;
  if (!pending.contains(action)) pending.prepend(action);
  return pending;
}

checklist = setupChecklist({api, roleSelect, setBusy, onSaved: loadState,
  requirementDetails, onLegacyProvider: async provider => {
  document.getElementById("provider-state").value = provider.archived_at ? "archived" : "active";
  state.preferredProviderId = provider.id;
  if (!await initialize(provider.id) || state.provider?.id !== provider.id) throw new Error("Saved view unavailable.");
}});
creation = setupProviderCreation({api, roleSelect, setBusy, onCreated: async (id, archived = false) => {
  document.getElementById("provider-state").value = archived ? "archived" : "active";
  state.preferredProviderId = id;
  updateText.value = "";
  state.pending = null;
  disclosure.open = false;
  if (!await initialize(id) || state.provider?.id !== id) throw new Error("Saved provider could not load.");
  providerSelect.focus();
}});
lifecycle = setupProviderLifecycle({api, roleSelect, setBusy, onChanged: async provider => {
  const archived = Boolean(provider.archived_at);
  document.getElementById("provider-state").value = archived ? "archived" : "active";
  state.preferredProviderId = provider.id;
  updateText.value = "";
  state.pending = null;
  disclosure.open = false;
  checklist.resetDraft();
  if (!await initialize(provider.id) || state.provider?.id !== provider.id
      || Boolean(state.provider.archived_at) !== archived) {
    clearSnapshot();
    throw new Error("Saved provider view unavailable.");
  }
  return state.provider;
}, onUnavailable: (id, archived) => {
  document.getElementById("provider-state").value = archived ? "archived" : "active";
  state.preferredProviderId = id;
  updateText.value = "";
  state.pending = null;
  disclosure.open = false;
  providerSelect.replaceChildren();
  clearSnapshot();
}});
roleSelect.addEventListener("change", () => {
  renderReviews();
  creation.syncRole();
  checklist.syncRole();
  lifecycle.syncRole();
  knowledge.syncRole();
});
knowledge.syncRole();
function changeProviderSelection() {
  lifecycle.clearRecovery();
  state.preferredProviderId = null;
  updateText.value = "";
  state.pending = null;
  disclosure.open = false;
  initialize();
}
providerSelect.addEventListener("change", changeProviderSelection);
refreshButton.addEventListener("click", async () => {
  if (await lifecycle.refresh()) return;
  await initialize();
  await checklist.recoverLegacy();
});
initialize().then(() => checklist.recoverLegacy());

document.getElementById("provider-state").addEventListener("change", changeProviderSelection);
