"use strict";

import {historyEvents} from "./history-events.js";
import {renderHistoryEntry} from "./history-render.js";

export function setupRequirementHistory({dialog, trigger, onRefresh}) {
  const filter = dialog.querySelector("#history-requirement");
  const context = dialog.querySelector("#history-context");
  const current = dialog.querySelector("#history-current");
  const entries = dialog.querySelector("#history-entries");
  const notice = dialog.querySelector("#history-status");
  const refresh = dialog.querySelector("#refresh-history");
  let provider = null, updates = [], edits = [], selectedId = null, busy = false;
  let opener = null, openerId = null, openingProvider = null;
  let deferredFocus = null;

  function focusOpener(source, requirementId) {
    const target = source?.isConnected ? source : requirementId === null ? trigger
      : document.querySelector('.requirement-row[data-requirement-id="' + requirementId + '"] .requirement-history-trigger');
    (target || trigger).focus();
  }

  function syncControls() {
    trigger.disabled = busy || !provider;
    refresh.disabled = busy || !provider;
    filter.disabled = busy || !provider;
  }

  function draw() {
    const requirement = provider.requirements.find(item => item.id === selectedId);
    context.textContent = provider.name + " · " + (requirement?.name || "All requirements") + (provider.archived_at ? " · Archived" : "");
    current.replaceChildren();
    current.hidden = !requirement;
    if (requirement) {
      for (const [label, value] of [["Status", requirement.status], ["Expected completion date", requirement.scheduled_date], ["Deadline", requirement.deadline]]) {
        const item = document.createElement("p");
        item.textContent = label + ": " + (value || "Not set");
        current.append(item);
      }
    }
    entries.replaceChildren();
    const events = historyEvents(provider.id, updates, edits, selectedId);
    if (!events.length) {
      const empty = document.createElement("p");
      empty.textContent = selectedId === null ? "No saved updates yet." : "No saved activity for this requirement.";
      entries.append(empty);
    }
    events.forEach(entry => renderHistoryEntry(entries, entry));
  }

  function open(requirementId = null, source = trigger) {
    if (!provider || busy || (requirementId !== null && !provider.requirements.some(item => item.id === requirementId))) return;
    selectedId = requirementId;
    filter.value = requirementId === null ? "" : String(requirementId);
    opener = source; openerId = requirementId; openingProvider = provider.id;
    deferredFocus = null;
    notice.textContent = "";
    draw();
    dialog.showModal();
    dialog.querySelector(".history-body").scrollTop = 0;
  }

  trigger.addEventListener("click", () => open());
  dialog.querySelectorAll("[data-close-history]").forEach(button => button.addEventListener("click", () => dialog.close()));
  dialog.addEventListener("keydown", event => {
    if (event.key !== "Tab") return;
    const controls = [...dialog.querySelectorAll("button,select")].filter(node => !node.disabled && node.getClientRects().length);
    const first = controls[0], last = controls.at(-1);
    if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
    else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
  });
  dialog.addEventListener("close", () => {
    if (provider?.id === openingProvider) {
      if (busy) deferredFocus = {source: opener, requirementId: openerId, providerId: openingProvider};
      else focusOpener(opener, openerId);
    }
    opener = null;
  });
  filter.addEventListener("change", () => {
    selectedId = filter.value === "" ? null : Number(filter.value);
    draw();
  });
  refresh.addEventListener("click", async () => {
    if (busy || !provider) return;
    notice.textContent = "Refreshing history…";
    try {
      await onRefresh();
      notice.textContent = "History is up to date.";
    } catch {
      notice.textContent = "History could not refresh. Showing the last loaded records.";
    }
  });

  return {
    open,
    setBusy(value) {
      busy = value; syncControls();
      if (!busy && deferredFocus) {
        if (provider?.id === deferredFocus.providerId && document.activeElement === document.body) {
          focusOpener(deferredFocus.source, deferredFocus.requirementId);
        }
        deferredFocus = null;
      }
    },
    render(nextProvider, nextUpdates, nextEdits) {
      const sameProvider = provider?.id === nextProvider?.id;
      provider = nextProvider; updates = nextUpdates; edits = nextEdits;
      if (!sameProvider || !provider) {
        deferredFocus = null;
        openingProvider = null;
        if (dialog.open) dialog.close();
        selectedId = null;
        entries.replaceChildren(); current.replaceChildren(); context.textContent = "";
      }
      filter.replaceChildren();
      for (const [id, name] of [["", "All requirements"], ...(provider?.requirements || []).map(item => [item.id, item.name])]) {
        const option = document.createElement("option");
        option.value = id; option.textContent = name; filter.append(option);
      }
      if (selectedId !== null && !provider?.requirements.some(item => item.id === selectedId)) {
        selectedId = null;
        if (dialog.open) dialog.close();
      }
      filter.value = selectedId === null ? "" : String(selectedId);
      if (dialog.open) draw();
      syncControls();
    }
  };
}
