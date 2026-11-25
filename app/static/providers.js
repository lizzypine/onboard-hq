"use strict";

import {createProviderWizard} from "./provider-wizard.js?v=5";
import {clearCreationAttempt, readCreationAttempt, writeCreationAttempt} from "./provider-recovery.js?v=4";

export function providerLabel(provider, providers) {
  const matches = providers.filter(p => p.name === provider.name);
  if (matches.length < 2) return provider.name;
  return provider.name + " · " + provider.provider_type + " · " + (provider.proposed_start_date || "Start not set") + " · Ref " + provider.id;
}

export function setupProviderCreation({api, roleSelect, setBusy, onCreated}) {
  const open = document.getElementById("add-provider");
  const dialog = document.getElementById("provider-dialog");
  const status = document.getElementById("provider-creation-status");
  const retryCatalog = document.getElementById("retry-provider-catalog");
  const discard = document.getElementById("discard-provider-recovery");
  let busy = false, pending = null, message = "", readError = false;
  try { pending = readCreationAttempt(); } catch { readError = true; }
  if (pending) message = "A provider save needs confirmation. In Manager mode, use Add provider to recover the same attempt.";
  if (readError) message = "The saved provider draft could not be read. Check the provider list before discarding browser recovery data.";

  const wizard = createProviderWizard({dialog, onSubmit: submit, onCancel: () => {
    if (busy) return;
    wizard.close();
    if (!pending && !readError) message = "";
    sync(); open.focus();
  }});

  function sync() {
    open.hidden = roleSelect.value !== "manager";
    open.disabled = busy;
    discard.hidden = !readError || roleSelect.value !== "manager";
    discard.disabled = busy;
    status.textContent = message;
    wizard.setBusy(busy);
  }

  function complete() {
    try {
      clearCreationAttempt();
      pending = null;
      message = "Provider added. Their checklist is loaded.";
    } catch {
      message = "Provider saved and loaded. Browser recovery data could not be cleared; recovering this attempt again is safe.";
    }
    wizard.close(); sync();
  }

  async function loadCatalog(preserve = false, explanation = "") {
    setBusy(true); retryCatalog.hidden = true;
    try {
      const types = await api("/provider-types");
      if (preserve) wizard.replaceCatalog(types);
      else wizard.open(types);
      message = types.length ? explanation : "No configured requirements are available. Ask an administrator to configure provider templates.";
      wizard.showError(message);
    } catch {
      message = "Provider requirements could not be loaded. Retry loading requirements or cancel.";
      wizard.showError(message);
      retryCatalog.hidden = false;
    } finally { setBusy(false); sync(); }
  }

  async function submit(draft) {
    if (busy || roleSelect.value !== "manager" || readError) return;
    if (!pending) {
      const attempt = {payload: {...draft, creation_request_id: crypto.randomUUID()}, savedId: null};
      try { writeCreationAttempt(attempt); } catch {
        message = "This browser could not retain save recovery. No request was sent. Allow browser storage and try again.";
        wizard.showError(message); sync(); return;
      }
      pending = attempt;
    }
    const attempt = pending;
    setBusy(true);
    message = attempt.savedId ? "Loading the saved provider…" : "Saving fictional provider and checklist…";
    wizard.showRecovery(attempt, message);
    sync();
    try {
      let provider;
      if (attempt.savedId) provider = await api("/providers/" + attempt.savedId);
      else {
        provider = await api("/providers", {method: "POST",
          headers: {"Content-Type": "application/json", "X-Demo-Role": roleSelect.value},
          body: JSON.stringify(attempt.payload)});
        attempt.savedId = provider.id;
        try { writeCreationAttempt(attempt); } catch { /* The original frozen payload was retained before POST and remains retry-safe. */ }
      }
      await onCreated(provider.id, Boolean(provider.archived_at));
      if (pending === attempt) complete();
    } catch (error) {
      if (!attempt.savedId && (error.code === "template_changed" || [404, 422].includes(error.status))) {
        try { clearCreationAttempt(); } catch { /* The server confirmed this request did not create a provider. */ }
        pending = null;
        await loadCatalog(true, error.message);
      } else {
        message = attempt.savedId ? "Provider saved, but the dashboard could not load. Use Refresh data or reload the saved provider."
          : !error.status || error.status >= 500 ? "The save could not be confirmed. Retry save to recover the same provider."
          : error.message;
        wizard.showRecovery(attempt, message);
      }
    } finally { setBusy(false); sync(); }
  }

  open.addEventListener("click", () => {
    if (busy || roleSelect.value !== "manager") return;
    retryCatalog.hidden = true;
    if (pending) { wizard.showRecovery(pending, message); sync(); }
    else if (readError) { wizard.open([]); wizard.showError(message); sync(); }
    else { wizard.open([]); loadCatalog(); }
  });
  retryCatalog.addEventListener("click", () => { if (!busy && roleSelect.value === "manager") loadCatalog(true); });
  discard.addEventListener("click", () => {
    if (busy || roleSelect.value !== "manager" || !readError) return;
    try { clearCreationAttempt(); readError = false; message = "Recovery data discarded. Review saved providers before adding another."; }
    catch { message = "Browser recovery data could not be cleared. Check browser storage settings."; }
    sync();
  });
  const controller = {
    setBusy(value) { busy = value; sync(); },
    syncRole() { if (roleSelect.value !== "manager") wizard.close(); sync(); },
    onProviderLoaded(id) { if (pending?.savedId === id) complete(); },
  };
  controller.syncRole();
  return controller;
}
