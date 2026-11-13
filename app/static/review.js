"use strict";

function text(parent, tag, value, className = "") {
  const element = document.createElement(tag);
  element.textContent = value;
  element.className = className;
  parent.append(element);
  return element;
}

function editableCell(row, name, type, saved, initial, proposed, field) {
  const cell = text(row, "td", "");
  cell.dataset.reviewField = field;
  const savedLabel = saved === null ? "Not available" : saved || "Not set";
  text(cell, "span", "Saved: " + savedLabel, "review-saved");
  const input = document.createElement("input");
  input.type = type;
  input.setAttribute("aria-label", name);
  input.value = initial;
  input.required = type === "text";
  cell.append(input);
  const marker = text(cell, "span", "", "review-change-label");
  text(cell, "span", proposed ? "Originally proposed: " + proposed : "No date proposed", "review-original");
  return {cell, input, marker, saved, proposed};
}

function compare(field, isDate = false) {
  const value = isDate ? field.input.value : field.input.value.trim();
  const invalidDate = isDate && !field.input.checkValidity();
  field.cell.classList.toggle("review-invalid", invalidDate);
  if (isDate) field.input.setAttribute("aria-invalid", String(invalidDate));
  if (invalidDate) {
    field.cell.classList.remove("review-change");
    field.marker.textContent = field.input.validity.valueMissing
      ? "A date is required for this inferred suggestion." : "Enter a complete valid date.";
    return;
  }
  const changed = value !== field.saved;
  field.cell.classList.toggle("review-change", changed);
  if (isDate && !value && field.saved) {
    field.marker.textContent = "Date will be cleared";
  } else if (isDate && !value && field.proposed) {
    field.marker.textContent = "Proposed date removed";
  } else if (!changed) {
    field.marker.textContent = "Unchanged";
  } else {
    field.marker.textContent = value === field.proposed ? "Proposed change" : "Your correction";
  }
}

export function renderReviewControls(card, suggestion, current, {busy, onDecide}) {
  const fields = text(card, "fieldset", "", "review-fields");
  fields.disabled = busy;
  text(fields, "legend", "Manager decision");
  const scroll = text(fields, "div", "", "table-scroll");
  scroll.tabIndex = 0;
  scroll.setAttribute("role", "region");
  scroll.setAttribute("aria-label", "Scrollable manager decision");
  const table = text(scroll, "table", "", "review-table");
  table.setAttribute("aria-label", "Review " + suggestion.requirement);
  const header = text(text(table, "thead", ""), "tr", "");
  for (const label of ["Requirement", "Status", "Requirement date", "Deadline"]) {
    text(header, "th", label).scope = "col";
  }
  const row = text(text(table, "tbody", ""), "tr", "");
  text(row, "td", suggestion.requirement);
  const status = editableCell(row, "Reviewed status", "text", current?.status ?? null,
    suggestion.proposed_status, suggestion.proposed_status, "status");
  const initialDate = suggestion.proposed_date || current?.scheduled_date || "";
  const date = editableCell(row, "Reviewed date", "date", current ? current.scheduled_date || "" : null,
    initialDate, suggestion.proposed_date || "", "date");
  date.input.required = suggestion.date_requires_confirmation;
  text(row, "td", current ? current.deadline || "Not set" : "Not available");

  let confirmation = null;
  if (suggestion.date_requires_confirmation) {
    const label = text(fields, "label", "", "confirmation");
    confirmation = document.createElement("input");
    confirmation.type = "checkbox";
    label.append(confirmation, document.createTextNode("Confirm inferred date"));
  }
  const stale = !current || current.version !== suggestion.requirement_version;
  if (stale) text(fields, "p", "The checklist changed after this proposal. Reanalyze before approving; you can still reject it.");
  const actions = text(fields, "div", "", "actions");
  const approve = text(actions, "button", "Approve");
  const correct = text(actions, "button", "Approve with corrections");
  const reject = text(actions, "button", "Reject");
  [approve, correct, reject].forEach(button => { button.type = "button"; });

  function dateAction() {
    if (date.input.value === initialDate) return "preserve";
    return date.input.value ? "set" : "clear";
  }
  function sync() {
    compare(status);
    compare(date, true);
    const edited = status.input.value.trim() !== suggestion.proposed_status || dateAction() !== "preserve";
    const confirmed = !confirmation || (confirmation.checked && date.input.value);
    const invalid = stale || !status.input.value.trim() || !date.input.checkValidity() || !confirmed;
    approve.disabled = Boolean(invalid || edited);
    correct.disabled = Boolean(invalid || !edited);
  }
  status.input.addEventListener("input", sync);
  date.input.addEventListener("input", () => {
    if (confirmation) confirmation.checked = false;
    sync();
  });
  if (confirmation) confirmation.addEventListener("change", sync);
  approve.addEventListener("click", () => onDecide(suggestion, {action: "approve", date_confirmed: Boolean(confirmation?.checked)}));
  correct.addEventListener("click", () => {
    const body = {action: "correct", date_confirmed: Boolean(confirmation?.checked)};
    if (status.input.value.trim() !== suggestion.proposed_status) body.corrected_status = status.input.value.trim();
    const action = dateAction();
    if (action !== "preserve") body.date_action = action;
    if (action === "set") body.corrected_date = date.input.value;
    onDecide(suggestion, body);
  });
  reject.addEventListener("click", () => onDecide(suggestion, {action: "reject"}));
  sync();
}
