"use strict";

export function statusSelect({label, choices, value}) {
  const select = document.createElement("select");
  select.setAttribute("aria-label", label);
  for (const status of new Set([...choices, value])) {
    const option = document.createElement("option");
    option.value = status;
    option.textContent = status;
    select.append(option);
  }
  select.value = value;
  select.required = true;
  return select;
}

export function statusBadge(value, tone) {
  const badge = document.createElement("span");
  badge.className = "status-badge status-" + (tone || "unknown");
  badge.textContent = value;
  return badge;
}
