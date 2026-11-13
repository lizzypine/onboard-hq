"use strict";

import {statusBadge, statusSelect} from "./statuses.js";

const pendingKey = "onboard-hq:pending-checklist-edit";

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
    if (value && uuid.test(value.providerId) && uuid.test(value.requirementId) && uuid.test(value.body?.id)
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

export function setupChecklist({api, roleSelect, setBusy, onSaved}) {
  const body = document.getElementById("requirements");
  const notice = document.getElementById("checklist-status");
  const retry = document.getElementById("retry-checklist");
  let provider = null, monitoring = null, options = [];
  let busy = false, editId = null, draft = null, syncDraft = null;
  let pending = restoreAttempt();
  let message = pending ? "A checklist save needs confirmation. Retry the saved attempt." : "";

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
      : message;
    retry.hidden = !pending || !sameProvider || roleSelect.value !== "manager";
    retry.disabled = busy;
  }

  function syncControls() {
    body.querySelectorAll(".checklist-fields").forEach(fieldset => { fieldset.disabled = busy; });
    body.querySelectorAll(".checklist-edit-button").forEach(button => { button.disabled = busy || Boolean(pending); });
    if (syncDraft) syncDraft();
    showNotice();
  }

  async function sendAttempt() {
    if (busy || !pending || provider?.id !== pending.providerId || roleSelect.value !== "manager") return;
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
    for (const [field, label] of [["status", "Status"], ["scheduled_date", "Requirement date"], ["deadline", "Deadline"]]) {
      const wrapper = text(grid, "label", label);
      const input = field === "status" ? statusSelect({label: "Checklist status", choices, value: draft[field]}) : document.createElement("input");
      if (field !== "status") { input.type = "date"; input.value = draft[field] || ""; input.setAttribute("aria-label", label); }
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
        body: {id: crypto.randomUUID(), expected_version: requirement.version, ...draft}};
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

  function draw() {
    body.replaceChildren();
    syncDraft = null;
    document.getElementById("checklist-action-heading").hidden = roleSelect.value !== "manager";
    if (!provider) { showNotice(); return; }
    const indicators = new Map(monitoring.requirements.map(row => [row.requirement_id, row]));
    const catalog = new Map(options.map(row => [row.requirement_id, row]));
    provider.requirements.forEach((requirement, index) => {
      const row = text(body, "tr", "", "requirement-row " + (index % 2 ? "stripe-even" : "stripe-odd"));
      row.dataset.requirementId = requirement.id;
      row.classList.toggle("editing", editId === requirement.id);
      const name = text(row, "td", requirement.name);
      if (editId === requirement.id) text(name, "span", "Editing", "editing-label");
      text(row, "td", "").append(statusBadge(requirement.status, catalog.get(requirement.id)?.status_tone));
      text(row, "td", requirement.scheduled_date || "Not set");
      text(row, "td", requirement.deadline || "Not set");
      const indicator = indicators.get(requirement.id);
      const label = text(row, "td", monitoringLabel(indicator), "indicator " + (indicator.completion === "outstanding" && indicator.deadline_state === "past" ? "overdue" : indicator.completion));
      label.dataset.monitoring = "";
      const action = text(row, "td", "");
      action.hidden = roleSelect.value !== "manager";
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
      if (editId === requirement.id) renderEditor(row, requirement, catalog.get(requirement.id)?.statuses || [requirement.status]);
    });
    syncControls();
  }

  retry.addEventListener("click", sendAttempt);
  return {
    render(nextProvider, nextMonitoring, nextOptions) { provider = nextProvider; monitoring = nextMonitoring; options = nextOptions; editId = null; draft = null; draw(); },
    setBusy(value) { busy = value; syncControls(); },
    resetDraft() { editId = null; draft = null; draw(); },
    syncRole() { editId = null; draft = null; draw(); },
    onSnapshotLoaded() {
      if (pending?.confirmed && provider?.id === pending.providerId) {
        pending = null;
        remember();
        message = "Checklist changes saved. The checklist and history are up to date.";
        draw();
      }
    }
  };
}
