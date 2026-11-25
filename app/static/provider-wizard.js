"use strict";

import {addDateHelp} from "./date-help.js?v=4";
import {statusBadge} from "./statuses.js";

const normalize = value => value.replace(/^ +| +$/g, "").toLowerCase();
const labels = ["Name", "Provider type", "Proposed start date", "Requirements", "Review"];
const displayDate = value => value ? new Intl.DateTimeFormat("en-US", {month: "short", day: "numeric", year: "numeric", timeZone: "UTC"}).format(new Date(value + "T12:00:00Z")) : "Not set";

function text(parent, tag, value = "", className = "") {
  const node = document.createElement(tag);
  node.textContent = value;
  node.className = className;
  parent.append(node);
  return node;
}

function button(parent, label, action, className = "provider-quiet") {
  const node = text(parent, "button", label, className);
  node.type = "button";
  node.addEventListener("click", action);
  return node;
}

export function createProviderWizard({dialog, onSubmit, onCancel}) {
  const form = dialog.querySelector("#provider-form");
  const content = dialog.querySelector("#provider-step-content");
  const scroll = dialog.querySelector("#provider-scroll");
  const forward = dialog.querySelector("#save-provider");
  const back = dialog.querySelector("#provider-back");
  const notice = dialog.querySelector("#provider-modal-status");
  let types = [], draft, step = 0, counter = 0, extra = null, editing = null;
  let returning = false, busy = false, recovery = null;
  const selected = () => types.find(kind => kind.id === draft.typeId);
  function configuredChoices(name) {
    const catalog = selected()?.configured_statuses;
    const key = normalize(name);
    return catalog && Object.hasOwn(catalog, key) ? catalog[key] : null;
  }
  const choices = name => configuredChoices(name) || selected()?.additional_statuses || [];

  function additionProblem(item, exclude = item.id) {
    if (!item.name.trim()) return "Give this requirement a name.";
    const key = normalize(item.name.trim());
    const names = [...(selected()?.requirements || []), ...draft.additions.filter(a => a.id !== exclude).map(a => a.name)];
    if (names.some(name => normalize(name) === key)) return "This requirement is already on the checklist. Use a different name.";
    if (!choices(item.name).includes(item.status)) return "Choose a status available for this requirement and provider type.";
    return "";
  }

  function additionsValid() { return draft.additions.every(item => !additionProblem(item)); }
  function editorValid() {
    return extra && !additionProblem(extra, editing) && [...content.querySelectorAll(".provider-extra-fields input,.provider-extra-fields select")].every(input => input.checkValidity());
  }
  function valid() {
    if (!draft.name.trim() || !types.length) return false;
    if (step === 0) return true;
    if (!selected()) return false;
    if (step === 2) return content.querySelector("input").checkValidity();
    return step < 3 || (!extra && additionsValid());
  }

  function sync() {
    form.querySelectorAll("input,select,button").forEach(node => { node.disabled = busy; });
    forward.disabled = busy || (!recovery && !valid());
    forward.textContent = busy ? (recovery?.savedId ? "Loading…" : "Please wait…")
      : recovery ? (recovery.savedId ? "Reload saved provider" : "Retry save")
      : step === 4 ? "Add provider" : returning ? "Save and review →" : step === 3 ? "Review provider →" : "Continue →";
    content.querySelectorAll(".provider-row-action").forEach(node => { node.disabled = busy || Boolean(extra); });
    const save = content.querySelector("#save-extra-requirement");
    if (save) save.disabled = busy || !editorValid();
    const error = content.querySelector("#extra-requirement-error");
    if (error) error.textContent = extra.name.trim() ? additionProblem(extra, editing) : "";
  }

  function input(parent, label, id, value, type, update) {
    const heading = text(parent, "div", "", type === "date" ? "date-field-heading" : "");
    text(heading, "label", label).htmlFor = id;
    if (label === "Expected completion date") addDateHelp(heading);
    if (type === "date") text(heading, "span", "Optional", "provider-hint");
    const node = document.createElement("input");
    node.id = id; node.type = type; node.value = value || "";
    if (type === "date") { node.min = "0001-01-01"; node.max = "9999-12-31"; }
    else { node.required = true; node.autocomplete = "off"; }
    parent.append(node);
    const changed = () => { update(node.value); sync(); };
    node.addEventListener("input", changed);
    node.addEventListener("change", changed);
    return node;
  }

  function fillStatuses(select, value) {
    select.replaceChildren();
    for (const status of new Set([...choices(extra.name), value])) {
      const option = text(select, "option", status); option.value = status;
    }
    select.value = value;
  }

  function tone(item, additional) {
    const values = configuredChoices(item.name) || (additional ? selected()?.additional_statuses : null);
    const status = item.status.trim().toLowerCase();
    if (!values || !values.some(value => value.toLowerCase() === status)) return "unknown";
    if (status === values.at(-1).toLowerCase()) return "finished";
    return ["pending", "scheduled", "submitted"].includes(status) ? "progress" : "attention";
  }

  function table(parent, editable, includeStandard = true) {
    const scroll = text(parent, "div", "", "table-scroll");
    scroll.tabIndex = 0; scroll.setAttribute("role", "region");
    scroll.setAttribute("aria-label", "Scrollable provider checklist");
    const result = text(scroll, "table");
    result.setAttribute("aria-label", editable ? "New provider checklist preview" : "Review all requirements");
    const header = text(text(result, "thead"), "tr");
    for (const name of ["Requirement", "Status", "Expected completion date", "Deadline"]) {
      const cell = text(header, "th", name); cell.scope = "col";
      if (name === "Expected completion date") addDateHelp(cell);
    }
    const body = text(result, "tbody");
    const standards = includeStandard ? (selected()?.requirements || []).map(name => ({name, status: "Outstanding"})) : [];
    for (const item of [...standards, ...draft.additions]) {
      const additional = item.id !== undefined;
      const row = text(body, "tr");
      if (additional) { row.dataset.additionalId = item.id; row.tabIndex = -1; }
      const name = text(row, "td", item.name);
      if (additional) text(name, "span", "Additional · this provider only", "provider-additional-label");
      if (additional && editable) {
        const actions = text(name, "div", "", "provider-row-actions");
        button(actions, "Edit", () => { editing = item.id; extra = {...item}; render(); focusExtra(); }, "provider-quiet provider-row-action").setAttribute("aria-label", "Edit " + item.name);
        button(actions, "Remove", () => { draft.additions = draft.additions.filter(a => a.id !== item.id); render(); }, "provider-quiet provider-row-action").setAttribute("aria-label", "Remove " + item.name);
      }
      text(row, "td").append(statusBadge(item.status, tone(item, additional)));
      text(row, "td", displayDate(item.scheduled_date));
      text(row, "td", displayDate(item.deadline));
      if (additional && editable && additionProblem(item)) text(name, "p", additionProblem(item), "provider-error");
    }
  }

  function heading(title, description) {
    text(content, "p", "Step " + (step + 1) + " of 5", "provider-eyebrow");
    text(content, "h3", title, "provider-step-title").tabIndex = -1;
    text(content, "p", description, "provider-step-description");
  }

  function renderName() {
    heading("Who are we onboarding?", "Start with the provider’s name. You’ll review everything before adding them.");
    const entry = text(content, "div", "", "provider-entry");
    input(entry, "Provider name", "new-provider-name", draft.name, "text", value => { draft.name = value; }).placeholder = "Dr. Avery Example";
    text(entry, "p", "Use a fictional name for this prototype.", "provider-hint");
  }

  function renderType() {
    heading("Choose their provider type", "The provider type determines their standard onboarding checklist.");
    const entry = text(content, "div", "", "provider-entry");
    text(entry, "label", "Provider type").htmlFor = "new-provider-type";
    const picker = text(entry, "select"); picker.id = "new-provider-type"; picker.required = true;
    text(picker, "option", "Select a provider type").value = "";
    for (const type of types) text(picker, "option", type.name).value = type.id;
    picker.value = draft.typeId || "";
    picker.addEventListener("change", () => { draft.typeId = Number(picker.value) || null; sync(); });
    text(entry, "p", "Review the standard checklist next. Additional requirements apply only to this provider.", "provider-hint");
  }

  function renderStart() {
    heading("When do they plan to start?", "Leave this blank if the proposed start date hasn’t been confirmed.");
    const entry = text(content, "div", "", "provider-entry");
    input(entry, "Proposed start date", "new-provider-start", draft.start, "date", value => { draft.start = value || null; });
    button(entry, "Skip for now →", () => { draft.start = null; entry.querySelector("input").value = ""; advance(); });
  }

  function focusExtra() { content.querySelector("#additional-requirement-name")?.focus(); }

  function saveExtra() {
    if (!editorValid() || busy) return;
    const saved = {...extra, name: extra.name.trim()};
    if (editing === null) draft.additions.push(saved);
    else draft.additions = draft.additions.map(item => item.id === editing ? saved : item);
    extra = null; editing = null; render();
    const row = content.querySelector('[data-additional-id="' + saved.id + '"]');
    row?.focus(); row?.scrollIntoView({block: "nearest"});
    notice.textContent = saved.name + " saved to this checklist draft. You can add another requirement.";
  }

  function renderExtra(parent) {
    const fields = text(parent, "fieldset", "", "provider-extra-fields");
    text(fields, "legend", editing === null ? "New additional requirement" : "Edit additional requirement");
    const grid = text(fields, "div", "", "provider-extra-grid");
    let statuses;
    input(text(grid, "div", "", "provider-wide"), "Requirement name", "additional-requirement-name", extra.name, "text", value => {
      extra.name = value; if (statuses) fillStatuses(statuses, extra.status);
    });
    const wrapper = text(grid, "div", "", "provider-wide");
    text(wrapper, "label", "Status").htmlFor = "additional-requirement-status";
    statuses = text(wrapper, "select"); statuses.id = "additional-requirement-status"; statuses.required = true;
    fillStatuses(statuses, extra.status);
    statuses.addEventListener("change", () => { extra.status = statuses.value; sync(); });
    input(text(grid, "div"), "Expected completion date", "additional-requirement-date", extra.scheduled_date, "date", value => { extra.scheduled_date = value || null; });
    input(text(grid, "div"), "Deadline", "additional-requirement-deadline", extra.deadline, "date", value => { extra.deadline = value || null; });
    const error = text(fields, "p", "", "provider-error"); error.id = "extra-requirement-error"; error.setAttribute("role", "alert");
    const actions = text(fields, "div", "", "actions");
    button(actions, "Save requirement", saveExtra, "primary").id = "save-extra-requirement";
    button(actions, "Cancel requirement", () => { extra = null; editing = null; render(); content.querySelector("#add-extra-requirement")?.focus(); });
    text(fields, "p", "Save this requirement to the checklist above before adding another.", "provider-hint");
  }

  function renderRequirements() {
    heading("Build their onboarding checklist", "Review the standard requirements, then add anything specific to " + draft.name.trim() + ".");
    const head = text(content, "div", "", "provider-list-heading");
    text(head, "h4", "Provider checklist");
    text(head, "span", ((selected()?.requirements.length || 0) + draft.additions.length) + " requirements", "provider-count");
    table(content, true);
    const section = text(content, "div", "", "provider-additional-section");
    text(section, "h4", "Add an additional requirement");
    text(section, "p", "Fill out one requirement and save it to the checklist, then add another. These apply only to this provider.", "provider-hint");
    if (extra) renderExtra(section);
    else button(section, "+ Add requirement", () => { extra = {id: ++counter, name: "", status: "Outstanding", scheduled_date: null, deadline: null}; editing = null; render(); focusExtra(); }, "provider-add-requirement").setAttribute("aria-label", "Add requirement");
    const add = section.querySelector(".provider-add-requirement");
    if (add) add.id = "add-extra-requirement";
  }

  function details(parent, editable) {
    const box = text(parent, "div", "", "provider-review-box");
    for (const [label, value, index, action] of [
      ["Provider name", draft.name.trim(), 0, "Edit name"],
      ["Provider type", selected()?.name || "Submitted selection", 1, "Edit type"],
      ["Proposed start date", displayDate(draft.start), 2, "Edit date"],
    ]) {
      const row = text(box, "div", "", "provider-detail");
      const field = text(row, "div");
      text(field, "span", label, "provider-detail-label");
      text(field, "span", value, "provider-detail-value");
      if (editable) button(row, action, () => { step = index; returning = true; render(); focusStep(); });
    }
  }

  function renderReview() {
    heading("Review before adding", recovery ? "This submitted provider and checklist are frozen. Recover this save before starting another provider." : "Check their details and complete checklist before adding them.");
    details(content, !recovery);
    if (recovery) {
      text(content, "p", recovery.savedId ? "The provider was saved. Reload their current checklist and history." : "Retry save confirms the original attempt without resetting later progress.", "provider-hint");
      text(content, "p", "Closing this window keeps the save available for recovery.", "provider-hint");
      if (draft.additions.length) table(content, false, false);
      return;
    }
    const head = text(content, "div", "", "provider-list-heading");
    text(head, "h4", "Onboarding checklist");
    button(head, "Edit checklist", () => { step = 3; returning = true; render(); focusStep(); });
    table(content, false);
    text(content, "p", "The provider and all requirements will be saved together.", "provider-hint");
  }

  function render() {
    const progress = dialog.querySelector("#provider-progress"); progress.replaceChildren();
    labels.forEach((name, index) => {
      const item = text(progress, "li", "", index === step ? "current" : index < step ? "done" : "");
      if (index === step) item.setAttribute("aria-current", "step");
      text(item, "span", index < step ? "✓" : String(index + 1), "provider-step-dot");
      text(item, "span", name, "provider-step-name");
    });
    content.replaceChildren();
    [renderName, renderType, renderStart, renderRequirements, renderReview][step]();
    back.hidden = step === 0 || Boolean(recovery);
    sync(); scroll.scrollTop = 0;
  }

  function focusStep() { (content.querySelector("input,select") || content.querySelector(".provider-step-title"))?.focus(); }
  function advance() {
    if (busy) return;
    if (recovery) { onSubmit(); return; }
    if (!valid()) return;
    notice.textContent = "";
    if (step === 4) {
      onSubmit({name: draft.name.trim(), provider_type_id: selected().id,
        checklist_template_id: selected().checklist_template_id, template_fingerprint: selected().template_fingerprint,
        proposed_start_date: draft.start || null,
        additional_requirements: draft.additions.map(({name, status, scheduled_date, deadline}) => ({name: name.trim(), status, scheduled_date, deadline}))});
      return;
    }
    step = returning ? (additionsValid() ? 4 : 3) : step + 1;
    if (step === 4) returning = false;
    render(); focusStep();
  }

  form.addEventListener("submit", event => { event.preventDefault(); advance(); });
  back.addEventListener("click", () => { if (!busy && step > 0) { step--; returning = false; render(); focusStep(); } });
  dialog.querySelector("#cancel-provider").addEventListener("click", () => { if (!busy) onCancel(); });
  dialog.querySelector("#close-provider").addEventListener("click", () => { if (!busy) onCancel(); });
  dialog.addEventListener("cancel", event => { event.preventDefault(); if (!busy) onCancel(); });
  dialog.addEventListener("keydown", event => {
    if (event.key !== "Tab") return;
    const controls = [...dialog.querySelectorAll("button,input,select,textarea,[tabindex]")]
      .filter(node => !node.disabled && node.tabIndex >= 0 && node.getClientRects().length);
    if (!controls.length) { event.preventDefault(); return; }
    const first = controls[0], last = controls.at(-1);
    if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
    else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
  });

  return {
    open(catalog) {
      types = catalog; draft = {name: "", typeId: null, start: null, additions: []};
      step = 0; counter = 0; extra = null; editing = null; returning = false; recovery = null;
      notice.textContent = ""; render(); if (!dialog.open) dialog.showModal(); focusStep();
    },
    close() { if (dialog.open) dialog.close(); },
    setBusy(value) { busy = value; if (draft) sync(); },
    showError(message) { notice.textContent = message; },
    showRecovery(attempt, message) {
      const data = attempt.payload;
      draft = {name: data.name, typeId: data.provider_type_id, start: data.proposed_start_date,
        additions: data.additional_requirements.map(item => ({...item, id: ++counter}))};
      recovery = attempt; extra = null; editing = null; step = 4; returning = false;
      render(); notice.textContent = message; if (!dialog.open) dialog.showModal(); focusStep();
    },
    replaceCatalog(catalog) { types = catalog; recovery = null; step = selected() ? 3 : 1; returning = true; render(); focusStep(); },
  };
}
