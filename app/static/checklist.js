"use strict";

import {statusBadge, statusSelect} from "./statuses.js";
import {addDateHelp} from "./date-help.js?v=4";
import {inspectLegacyAttempt, legacyAttemptKey, recoverLegacyAttempt} from "./checklist-recovery.js?v=2";

const pendingKey = "onboard-hq:pending-checklist-edit:v2";

function text(parent, tag, value, className = "") {
  const node = document.createElement(tag);
  node.textContent = value;
  node.className = className;
  parent.append(node);
  return node;
}

function restoreAttempt() {
  try {
    const value = JSON.parse(sessionStorage.getItem(pendingKey));
    const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
    if (value && Number.isSafeInteger(value.providerId) && value.providerId > 0 && Number.isSafeInteger(value.requirementId) && value.requirementId > 0 && uuid.test(value.body?.operation_id)
        && typeof value.providerName === "string" && typeof value.body.status === "string"
        && Number.isInteger(value.body.expected_version) && value.body.expected_version >= 0
        && [value.body.scheduled_date, value.body.deadline].every(d => d === null || typeof d === "string")) return value;
  } catch { /* Keep the in-memory retry available if browser storage is unavailable. */ }
  return null;
}

function monitoringLabel(indicator) {
  if (indicator.completion === "finished") return "Finished";
  if (indicator.completion === "needs_review") return indicator.deadline_state === "past" ? "Deadline passed — needs review" : "Needs review";
  if (indicator.deadline_state === "past") return "Overdue";
  return indicator.deadline_state === "due_today" ? "Outstanding — due today" : "Outstanding";
}

export function setupChecklist({api, roleSelect, setBusy, onSaved, onLegacyProvider, requirementDetails = () => null}) {
  const body = document.getElementById("requirements");
  const notice = document.getElementById("checklist-status");
  const retry = document.getElementById("retry-checklist");
  let provider = null, monitoring = null, options = [];
  let busy = false, editId = null, draft = null, syncDraft = null;
  let pending = restoreAttempt();
  let message = pending ? "A checklist save needs confirmation. Retry the saved attempt." : "";

  let legacyAttempt = null, legacyResult = null, legacyBusy = false, legacyMessage = "";
  try { legacyAttempt = inspectLegacyAttempt(sessionStorage); } catch { /* Keep current in-memory recovery available. */ }
  const legacyRegion = document.createElement("section");
  legacyRegion.setAttribute("aria-label", "Older checklist save");
  const legacyStatus = text(legacyRegion, "p", "");
  legacyStatus.id = "legacy-checklist-status";
  legacyStatus.setAttribute("role", "status");
  const checkLegacy = text(legacyRegion, "button", "Check older save");
  checkLegacy.type = "button";
  const dismissLegacy = text(legacyRegion, "button", "Dismiss older save");
  dismissLegacy.type = "button";
  notice.after(legacyRegion);

  function renderLegacy() {
    legacyRegion.hidden = !legacyAttempt && !legacyMessage;
    const details = legacyAttempt ? "Older checklist save for " + legacyAttempt.providerName
      + ". Status: " + legacyAttempt.body.status + ". Expected completion date: " + (legacyAttempt.body.scheduled_date || "Not set")
      + ". Deadline: " + (legacyAttempt.body.deadline || "Not set") + ". " : "";
    legacyStatus.textContent = details + legacyMessage;
    checkLegacy.hidden = dismissLegacy.hidden = !legacyAttempt;
    checkLegacy.disabled = dismissLegacy.disabled = busy || legacyBusy;
  }

  function forgetLegacy() {
    legacyAttempt = null;
    legacyResult = null;
    try { sessionStorage.removeItem(legacyAttemptKey); } catch { /* A future reload can safely confirm again. */ }
  }

  async function recoverLegacy() {
    if (!legacyAttempt || legacyBusy) return;
    legacyBusy = true;
    setBusy(true);
    legacyMessage = "Checking saved history…";
    renderLegacy();
    try {
      legacyResult = await recoverLegacyAttempt({api, attempt: legacyAttempt});
      if (legacyResult.kind === "saved") {
        legacyMessage = "This older checklist save was already saved. Loading its current checklist and history…";
        await onLegacyProvider(legacyResult.provider);
      } else {
        legacyMessage = legacyResult.event
          ? "The operation has different saved values. This draft is retained; no change was submitted."
          : "The saved operation is unavailable. This draft is retained until you dismiss it; no change was submitted.";
      }
    } catch {
      legacyMessage = "The current saved view is unavailable. This draft is retained; check again when data loads.";
    } finally {
      legacyBusy = false;
      setBusy(false);
      renderLegacy();
    }
  }

  checkLegacy.addEventListener("click", recoverLegacy);
  dismissLegacy.addEventListener("click", () => { forgetLegacy(); legacyMessage = ""; renderLegacy(); });
  renderLegacy();

  function remember() {
    try {
      if (pending) sessionStorage.setItem(pendingKey, JSON.stringify(pending));
      else sessionStorage.removeItem(pendingKey);
    } catch { /* The current page still retains the operation identity. */ }
  }

  function showNotice() {
    const sameProvider = pending && provider?.id === pending.providerId;
    notice.textContent = pending && !sameProvider
      ? "A checklist save needs confirmation for " + pending.providerName + ". Select that provider to recover it."
      : pending && provider?.archived_at
        ? "This checklist save is retained. Restore the provider before retrying the same save."
        : message;
    retry.hidden = !pending || !sameProvider || roleSelect.value !== "manager" || Boolean(provider.archived_at);
    retry.disabled = busy;
  }

  function syncControls() {
    body.querySelectorAll(".checklist-fields").forEach(fieldset => { fieldset.disabled = busy; });
    body.querySelectorAll(".checklist-edit-button").forEach(button => { button.disabled = busy || Boolean(pending); });
    if (syncDraft) syncDraft();
    showNotice();
    renderLegacy();
  }

  async function sendAttempt() {
    if (busy || !pending || provider?.id !== pending.providerId || provider.archived_at || roleSelect.value !== "manager") return;
    const attempt = pending;
    setBusy(true);
    message = "Saving checklist changes…";
    showNotice();
    try {
      await api("/providers/" + attempt.providerId + "/requirements/" + attempt.requirementId + "/edits", {
        method: "POST", headers: {"Content-Type": "application/json", "X-Demo-Role": roleSelect.value}, body: JSON.stringify(attempt.body)
      });
      attempt.confirmed = true;
      remember();
      await onSaved();
      message = "Checklist changes saved. The checklist and history are up to date.";
    } catch (error) {
      if (attempt.confirmed) message = "Checklist changes saved, but the view could not refresh. Use Refresh data or Retry checklist save.";
      else if (!error.status || error.status >= 500) message = "The checklist save could not be confirmed. Retry checklist save to recover the same attempt.";
      else {
        pending = null;
        remember();
        message = error.message;
        if (error.status === 409) {
          editId = null;
          try { await onSaved(); } catch { /* Keep the conflict and last coherent snapshot visible. */ }
        }
      }
    } finally { setBusy(false); }
  }

  function renderEditor(row, requirement, choices) {
    const editorRow = text(body, "tr", "", "requirement-editor");
    row.after(editorRow);
    const cell = text(editorRow, "td", "");
    cell.colSpan = 6;
    const fields = text(cell, "fieldset", "", "checklist-fields");
    text(fields, "legend", "Edit " + requirement.name);
    const grid = text(fields, "div", "", "checklist-edit-grid");
    const inputs = {};
    for (const [field, label] of [["status", "Status"], ["scheduled_date", "Expected completion date"], ["deadline", "Deadline"]]) {
      const wrapper = text(grid, field === "scheduled_date" ? "div" : "label", field === "scheduled_date" ? "" : label);
      if (field === "scheduled_date") {
        const heading = text(wrapper, "div", "", "date-field-heading");
        text(heading, "label", label).htmlFor = "checklist-scheduled-date";
        addDateHelp(heading);
      }
      const input = field === "status" ? statusSelect({label: "Checklist status", choices, value: draft[field]}) : document.createElement("input");
      if (field !== "status") { input.type = "date"; input.value = draft[field] || ""; input.setAttribute("aria-label", label); }
      if (field === "scheduled_date") input.id = "checklist-scheduled-date";
      wrapper.append(input);
      const change = text(wrapper, "span", "", "manual-change-label");
      inputs[field] = {input, wrapper, change};
      input.addEventListener("input", () => { draft[field] = input.value || null; syncDraft(); });
      input.addEventListener("change", () => { draft[field] = input.value || null; syncDraft(); });
    }
    const actions = text(fields, "div", "", "actions");
    const save = text(actions, "button", "Save changes", "primary");
    save.type = "button";
    save.addEventListener("click", () => {
      if (save.disabled || busy || pending) return;
      pending = {providerId: provider.id, providerName: provider.name, requirementId: requirement.id, confirmed: false,
        body: {operation_id: crypto.randomUUID(), expected_version: requirement.version, ...draft}};
      remember();
      sendAttempt();
    });
    const cancel = text(actions, "button", "Cancel");
    cancel.type = "button";
    cancel.addEventListener("click", () => { editId = null; draft = null; draw(); });
    syncDraft = () => {
      let changed = false, valid = true;
      for (const [field, item] of Object.entries(inputs)) {
        const edited = (item.input.value || null) !== (requirement[field] || null);
        changed ||= edited;
        valid &&= item.input.checkValidity();
        item.input.disabled = Boolean(pending);
        item.wrapper.classList.toggle("manual-change", edited);
        item.change.textContent = !item.input.checkValidity() ? "Enter a complete valid date." : edited ? "Will change" : "Unchanged";
      }
      save.disabled = busy || Boolean(pending) || !valid || !changed;
    };
  }

  function renderRequirementDetails(row, requirement, actionHidden) {
    const details = requirementDetails(requirement);
    const next = row.nextElementSibling;
    const anchor = next?.classList.contains("requirement-editor") ? next : row;
    const adjacent = anchor.nextElementSibling;
    const existing = adjacent?.classList.contains("requirement-suggestions") ? adjacent : null;
    if (!details) {
      existing?.remove();
      return;
    }
    const detailsRow = existing || document.createElement("tr");
    if (!existing) {
      detailsRow.className = "requirement-suggestions";
      detailsRow.dataset.requirementId = requirement.id;
      anchor.after(detailsRow);
    }
    const cell = detailsRow.firstElementChild || text(detailsRow, "td", "");
    cell.colSpan = actionHidden ? 5 : 6;
    if (cell.firstElementChild !== details) cell.replaceChildren(details);
  }

  function draw(preservedEditor = null) {
    const preservedSync = syncDraft;
    body.replaceChildren();
    syncDraft = null;
    document.getElementById("checklist-action-heading").hidden = roleSelect.value !== "manager" || Boolean(provider?.archived_at);
    if (!provider) { showNotice(); return; }
    const indicators = new Map(monitoring.requirements.map(row => [row.requirement_id, row]));
    const catalog = new Map(options.map(row => [row.requirement_id, row]));
    provider.requirements.forEach((requirement, index) => {
      const row = text(body, "tr", "", "requirement-row " + (index % 2 ? "stripe-even" : "stripe-odd"));
      row.dataset.requirementId = requirement.id;
      row.classList.toggle("editing", editId === requirement.id);
      const name = text(row, "td", requirement.name);
      if (requirement.checklist_template_id === null) text(name, "span", "Additional · this provider only", "provider-additional-label");
      if (editId === requirement.id) text(name, "span", "Editing", "editing-label");
      text(row, "td", "").append(statusBadge(requirement.status, catalog.get(requirement.id)?.status_tone));
      text(row, "td", requirement.scheduled_date || "Not set");
      text(row, "td", requirement.deadline || "Not set");
      const indicator = indicators.get(requirement.id);
      const label = text(row, "td", monitoringLabel(indicator), "indicator " + (indicator.completion === "outstanding" && indicator.deadline_state === "past" ? "overdue" : indicator.completion));
      label.dataset.monitoring = "";
      const action = text(row, "td", "");
      action.hidden = roleSelect.value !== "manager" || Boolean(provider.archived_at);
      if (!action.hidden) {
        const edit = text(action, "button", "Edit", "checklist-edit-button");
        edit.type = "button";
        edit.addEventListener("click", () => {
          if (busy || pending) return;
          editId = requirement.id;
          draft = {status: requirement.status, scheduled_date: requirement.scheduled_date, deadline: requirement.deadline};
          draw();
          body.querySelector(".checklist-fields select").focus();
        });
      }
      if (editId === requirement.id) {
        if (preservedEditor) { row.after(preservedEditor); syncDraft = preservedSync; }
        else renderEditor(row, requirement, catalog.get(requirement.id)?.statuses || [requirement.status]);
      }
      renderRequirementDetails(row, requirement, action.hidden);
    });
    syncControls();
  }

  retry.addEventListener("click", sendAttempt);
  return {
    recoverLegacy,
    refreshRequirementDetails() {
      if (!provider) return;
      const rows = body.querySelectorAll(".requirement-row");
      const actionHidden = document.getElementById("checklist-action-heading").hidden;
      provider.requirements.forEach((requirement, index) => renderRequirementDetails(rows[index], requirement, actionHidden));
    },
    render(nextProvider, nextMonitoring, nextOptions) {
      const previous = provider?.requirements.find(r => r.id === editId);
      const next = nextProvider?.requirements.find(r => r.id === editId);
      const unchanged = provider?.id === nextProvider?.id && previous && next && previous.version === next.version;
      const preservedEditor = unchanged ? body.querySelector(".requirement-editor") : null;
      if (!preservedEditor) { editId = null; draft = null; }
      provider = nextProvider;
      monitoring = nextMonitoring;
      options = nextOptions;
      draw(preservedEditor);
    },
    setBusy(value) { busy = value; syncControls(); },
    resetDraft() { editId = null; draft = null; draw(); },
    syncRole() { editId = null; draft = null; draw(); },
    onSnapshotLoaded(edits = []) {
      if (legacyResult?.kind === "saved" && provider?.id === legacyResult.provider.id
          && edits.some(event => event.id === legacyResult.event.id && event.operation_id === legacyResult.event.operation_id)) {
        forgetLegacy();
        legacyMessage = "This older checklist save was already saved. The current checklist and history are loaded.";
        renderLegacy();
      }
      if (pending?.confirmed && provider?.id === pending.providerId) {
        pending = null;
        remember();
        message = "Checklist changes saved. The checklist and history are up to date.";
        draw();
      }
    }
  };
}
