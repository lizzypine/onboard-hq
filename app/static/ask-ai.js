"use strict";

import {outcomes, renderAnswer} from "./ask-ai-answer.js";
import {action, byId, dateOrUnknown, element, isUuid, readSavedIdentity, rememberIdentity} from "./knowledge-ui.js";

const storageKey = "onboard-hq:pending-questions:v1";

function restoreQuestions() {
  const entries = readSavedIdentity(storageKey, []);
  if (!Array.isArray(entries)) return new Map();
  return new Map(entries.filter(entry => Number.isSafeInteger(entry?.provider_id)
    && entry.provider_id > 0 && isUuid(entry.request_id)).map(entry => [entry.provider_id, entry]));
}

export function setupAskAI({api, getProvider, getRole, onBindingsChanged}) {
  const trigger = byId("open-ask");
  const dialog = byId("ask-dialog");
  const question = byId("ask-question");
  const status = byId("ask-status");
  const answer = byId("ask-answer");
  const history = byId("ask-history");
  const historyItems = byId("ask-history-items");
  const send = byId("ask-submit");
  const check = byId("check-answer");
  const dismiss = byId("dismiss-question");

  const pending = restoreQuestions();
  const actions = new Map();
  let selection = null;
  let view = null;
  let busy = false;

  const current = context => Boolean(context && dialog.open && context === view && getProvider()?.id === context.provider.id);

  function remember() {
    rememberIdentity(storageKey, [...pending.values()].map(({provider_id, request_id}) => ({provider_id, request_id})));
  }

  function syncControls() {
    trigger.disabled = busy || !selection;
    for (const button of actions.values()) button.disabled = trigger.disabled;
    const waiting = Boolean(view && pending.has(view.provider.id));
    send.disabled = waiting || !question.value.trim();
    check.disabled = Boolean(view?.checking);
  }

  function showStatus(value = "", {recover = false, abandon = false} = {}) {
    status.textContent = value;
    check.hidden = !recover;
    dismiss.hidden = !abandon;
    syncControls();
  }

  async function showHistorical(context, entry) {
    answer.textContent = "Loading saved answer…";
    const opening = Symbol();
    context.opening = opening;
    try {
      const saved = await api("/qa/" + entry.id);
      if (!current(context) || context.opening !== opening || saved.provider_id !== context.provider.id) return;
      if (saved.state === "processing") answer.textContent = "This question is still processing. Refresh question history to check again.";
      else renderAnswer(answer, saved, {api, getRole}, true);
    } catch {
      if (current(context) && context.opening === opening) answer.textContent = "The saved answer could not load. Select it again to check.";
    }
  }

  async function loadHistory(context) {
    const loading = Symbol();
    context.historyLoad = loading;
    const visible = () => current(context) && context.historyLoad === loading;
    historyItems.textContent = "Loading question history…";
    try {
      const entries = await api("/providers/" + context.provider.id + "/answers");
      if (!visible()) return;
      historyItems.replaceChildren();
      if (!entries.length) element(historyItems, "p", "No saved questions yet.");
      for (const entry of entries) {
        if (entry.provider_id !== context.provider.id) continue;
        const row = element(historyItems, "div", "", "knowledge-history-row");
        action(row, entry.question, () => showHistorical(context, entry));
        element(row, "p", [
          dateOrUnknown(entry.created_at), outcomes[entry.outcome] || "Processing",
          entry.outdated ? "Outdated guidance" : ""
        ].filter(Boolean).join(" · "), "knowledge-muted");
      }
    } catch {
      if (visible()) historyItems.textContent = "Question history is unavailable.";
    }
    if (visible()) action(historyItems, "Refresh question history", () => loadHistory(context));
  }

  function receive(context, attempt, saved) {
    if (!current(context) || pending.get(attempt.provider_id) !== attempt) return;
    if (saved.provider_id !== attempt.provider_id || saved.request_id !== attempt.request_id) {
      showStatus("The response could not be matched to this question.", {recover: true});
      return;
    }
    if (saved.state === "processing") {
      showStatus("This question is still processing. You can check it in Question history if you start a new question.",
        {recover: true, abandon: true});
      return;
    }
    pending.delete(attempt.provider_id);
    remember();
    context.opening = null;
    showStatus();
    renderAnswer(answer, saved, {api, getRole});
    if (history.open) loadHistory(context);
  }

  async function reconcile(context) {
    const attempt = pending.get(context.provider.id);
    if (!attempt || context.checking) return;
    context.checking = true;
    showStatus("Checking saved question…", {recover: true});
    try {
      const saved = await api("/qa/requests/" + attempt.request_id);
      receive(context, attempt, saved);
    } catch (error) {
      if (current(context) && pending.get(context.provider.id) === attempt) {
        const missing = error.status === 404 && !attempt.sending;
        showStatus(missing ? "No saved answer is visible yet. Check again or start a new question."
          : "The saved question could not be confirmed. Check again for its answer.", {recover: true, abandon: missing});
      }
    } finally {
      context.checking = false;
      syncControls();
    }
  }

  byId("ask-form").addEventListener("submit", async event => {
    event.preventDefault();
    const context = view;
    const wording = question.value.trim();
    if (!context || !current(context) || !wording || pending.has(context.provider.id)) return;
    const body = Object.freeze({
      request_id: crypto.randomUUID(), provider_id: context.provider.id,
      requirement_id: context.requirement?.id ?? null, question: wording
    });
    const attempt = {...body, sending: true};
    pending.set(body.provider_id, attempt);
    remember();
    context.opening = null;
    answer.replaceChildren();
    showStatus("Asking…");
    try {
      const saved = await api("/qa/ask", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(body)});
      receive(context, attempt, saved);
    } catch (error) {
      if (!current(context) || pending.get(body.provider_id) !== attempt) return;
      if (error.status && error.status < 500) {
        pending.delete(body.provider_id);
        remember();
        showStatus(error.message);
      } else {
        showStatus("Service unavailable. Check whether this question was saved.", {recover: true});
      }
    } finally {
      attempt.sending = false;
      if (current(view) && view !== context && pending.get(body.provider_id) === attempt
          && view.provider.id === body.provider_id) reconcile(view);
    }
  });

  function open(requirementId = null, invoker = trigger) {
    const provider = getProvider();
    if (!provider || busy || dialog.open) return;
    const requirement = provider.requirements.find(item => item.id === requirementId);
    if (requirementId !== null && (!requirement || !actions.has(requirementId))) return;
    view = {provider, requirement, invoker};
    byId("ask-scope").textContent = [provider.name, provider.provider_type, "Hawaii", requirement?.name].filter(Boolean).join(" · ");
    dialog.showModal();
    dialog.scrollTop = 0;
    question.focus();
    showStatus();
    if (pending.has(provider.id)) reconcile(view);
    if (history.open) loadHistory(view);
  }

  function clearQuestion() {
    question.value = "";
    answer.replaceChildren();
    history.open = false;
    historyItems.replaceChildren();
    showStatus();
  }

  trigger.addEventListener("click", () => open());
  dialog.querySelector(".knowledge-close").addEventListener("click", () => dialog.close());
  dialog.addEventListener("close", () => {
    if (dialog.open || !view) return;
    const {invoker, provider} = view;
    view = null;
    clearQuestion();
    if (getProvider()?.id === provider.id) (invoker.isConnected ? invoker : trigger).focus();
  });
  question.addEventListener("input", syncControls);
  for (const example of dialog.querySelectorAll(".knowledge-examples button")) {
    example.addEventListener("click", () => { question.value = example.textContent; syncControls(); question.focus(); });
  }
  check.addEventListener("click", () => { if (view) reconcile(view); });
  dismiss.addEventListener("click", () => {
    if (!view) return;
    pending.delete(view.provider.id);
    remember();
    view.opening = null;
    clearQuestion();
    question.focus();
  });
  history.addEventListener("toggle", () => { if (view && history.open) loadHistory(view); });

  return {
    syncProvider(provider) {
      if (selection?.id === provider?.id) return;
      view = null;
      if (dialog.open) dialog.close();
      clearQuestion();
      actions.clear();
      selection = provider;
      syncControls();
      if (!provider) return;
      const captured = provider;
      api("/knowledge/providers/" + captured.id + "/requirement-topics").then(bindings => {
        if (selection !== captured) return;
        for (const requirement of captured.requirements) {
          if (!bindings[requirement.id]?.length) continue;
          const button = action(document.createDocumentFragment(), "Ask about this requirement",
            event => open(requirement.id, event.currentTarget), "knowledge-requirement");
          button.setAttribute("aria-haspopup", "dialog");
          actions.set(requirement.id, button);
        }
        syncControls();
        onBindingsChanged();
      }).catch(() => { /* The general modal and parent checklist remain available. */ });
    },
    setBusy(value) { busy = value; syncControls(); },
    requirementAction(requirement) { return actions.get(requirement.id); },
    open
  };
}
