"use strict";

export function setupProviderLifecycle({api, roleSelect, setBusy, onChanged, onUnavailable}) {
  const archive = document.getElementById("archive-provider");
  const restore = document.getElementById("restore-provider");
  const status = document.getElementById("provider-lifecycle-status");
  let provider = null, busy = false, working = false, message = "", pendingRead = null;

  function sync() {
    const manager = roleSelect.value === "manager";
    archive.hidden = !manager || !provider || Boolean(provider.archived_at);
    restore.hidden = !manager || !provider || !provider.archived_at;
    archive.disabled = restore.disabled = busy || working;
    status.textContent = message;
  }

  async function change(archived) {
    if (busy || working || !provider || roleSelect.value !== "manager") return;
    const target = provider;
    if (archived && !window.confirm("Archive " + target.name + "?\n\nTheir checklist and history will be preserved. You can restore them from Archived. Unsaved changes will be discarded.")) return;
    working = true;
    setBusy(true);
    const action = archived ? "archive" : "restore";
    const verb = archived ? "archived" : "restored";
    let confirmed = false;
    message = archived ? "Archiving provider…" : "Restoring provider…";
    sync();
    try {
      let actual, failure = null;
      try {
        actual = await api("/providers/" + target.id + "/" + action, {
          method: "POST", headers: {"X-Demo-Role": roleSelect.value}
        });
        confirmed = true;
      } catch (error) {
        failure = error;
        actual = await api("/providers/" + target.id);
      }
      const loaded = await onChanged(actual);
      pendingRead = null;
      const current = loaded.archived_at ? "archived" : "active";
      message = confirmed && Boolean(loaded.archived_at) === archived
        ? "Provider " + verb + ". "
        : (failure?.status ? failure.message + " " : "The save response was unconfirmed. ") + "Current provider state is " + current + ". ";
      message += "Current checklist and history loaded.";
      document.getElementById("provider").focus();
    } catch {
      pendingRead = {id: target.id, archived};
      onUnavailable(target.id, archived);
      message = confirmed ? "Provider " + verb + ", but the saved view could not load. Use Refresh data."
        : "The " + action + " could not be confirmed. Use Refresh data and check Active or Archived before trying again.";
    } finally {
      working = false;
      setBusy(false);
      sync();
    }
  }

  archive.addEventListener("click", () => change(true));
  restore.addEventListener("click", () => change(false));

  async function refresh() {
    if (!pendingRead) return false;
    if (busy || working) return true;
    const target = pendingRead;
    working = true;
    setBusy(true);
    message = "Checking this provider's saved state…";
    sync();
    try {
      const actual = await api("/providers/" + target.id);
      const loaded = await onChanged(actual);
      pendingRead = null;
      message = "Current provider state is " + (loaded.archived_at ? "archived" : "active") + ". Current checklist and history loaded.";
      document.getElementById("provider").focus();
    } catch {
      onUnavailable(target.id, target.archived);
      message = "This provider's current state is unavailable. Use Refresh data before continuing.";
    } finally {
      working = false;
      setBusy(false);
      sync();
    }
    return true;
  }

  const controller = {
    render(nextProvider) {
      if (!working && provider?.id !== nextProvider?.id) message = "";
      if (!working && nextProvider) pendingRead = null;
      provider = nextProvider;
      sync();
    },
    setBusy(value) { busy = value; sync(); },
    syncRole() { sync(); },
    refresh,
    clearRecovery() { pendingRead = null; message = ""; sync(); },
  };
  sync();
  return controller;
}
