"use strict";

export const EXPECTED_DATE_HELP = "When this item is expected to be completed—for example, the scheduled drug screening date. The deadline is the latest date it must be completed.";

let ready = false, explanation = null, trigger = null, pinned = false, timer = null;

function hide() {
  clearTimeout(timer);
  if (explanation?.matches(":popover-open")) explanation.hidePopover();
  trigger?.setAttribute("aria-expanded", "false");
  trigger = null;
  pinned = false;
}

function show(button, keepOpen = false) {
  clearTimeout(timer);
  const parent = button.closest("dialog[open]") || document.body;
  if (trigger !== button || explanation.parentNode !== parent) hide();
  parent.append(explanation);
  trigger = button;
  pinned ||= keepOpen;
  explanation.showPopover();
  trigger.setAttribute("aria-expanded", "true");
  position();
}

function position() {
  if (!trigger || !explanation.matches(":popover-open")) return;
  if (!trigger.isConnected) { hide(); return; }
  const bounds = trigger.getBoundingClientRect();
  const {width, height} = explanation.getBoundingClientRect();
  explanation.style.left = Math.max(12, Math.min(bounds.left, innerWidth - width - 12)) + "px";
  const top = bounds.bottom + height + 12 < innerHeight ? bounds.bottom + 6 : bounds.top - height - 6;
  explanation.style.top = Math.max(12, Math.min(top, innerHeight - height - 12)) + "px";
}

function leave() {
  clearTimeout(timer);
  if (!pinned && document.activeElement !== trigger) timer = setTimeout(hide, 200);
}

export function addDateHelp(parent) {
  setupDateHelp();
  const button = document.createElement("button");
  button.type = "button";
  button.className = "date-help";
  button.textContent = "?";
  button.setAttribute("aria-label", "About expected completion date");
  button.setAttribute("aria-describedby", "date-explanation");
  button.setAttribute("aria-expanded", "false");
  parent.append(document.createTextNode(" "), button);
  return button;
}

export function setupDateHelp() {
  if (ready) return;
  ready = true;
  explanation = document.createElement("div");
  explanation.id = "date-explanation";
  explanation.className = "date-explanation";
  explanation.popover = "manual";
  explanation.setAttribute("role", "tooltip");
  explanation.textContent = EXPECTED_DATE_HELP;
  document.body.append(explanation);
  document.addEventListener("pointerover", event => {
    const button = event.target.closest(".date-help");
    if (button) show(button);
    else if (explanation.contains(event.target)) clearTimeout(timer);
  });
  document.addEventListener("pointerout", event => {
    if (event.target.closest(".date-help") || explanation.contains(event.target)) leave();
  });
  document.addEventListener("focusin", event => {
    const button = event.target.closest(".date-help");
    if (button) show(button);
    else if (!pinned) hide();
  });
  document.addEventListener("focusout", event => {
    if (event.target.closest(".date-help") && !pinned) hide();
  });
  document.addEventListener("click", event => {
    const button = event.target.closest(".date-help");
    if (button) {
      if (pinned && trigger === button) hide();
      else show(button, true);
    } else if (!explanation.contains(event.target)) hide();
  });
  document.addEventListener("keydown", event => {
    if (event.key === "Escape" && explanation.matches(":popover-open")) {
      event.preventDefault();
      event.stopPropagation();
      hide();
    }
  }, true);
  document.addEventListener("close", event => { if (event.target.tagName === "DIALOG") hide(); }, true);
  window.addEventListener("resize", hide);
  document.addEventListener("scroll", position, true);
  document.querySelectorAll("[data-date-help]").forEach(addDateHelp);
}
