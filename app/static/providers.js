"use strict";

function text(parent, tag, value) {
  const node = document.createElement(tag);
  node.textContent = value;
  parent.append(node);
  return node;
}

export function providerLabel(provider, providers) {
  const matches = providers.filter(p => p.name === provider.name);
  if (matches.length < 2) return provider.name;
  let length = 8;
  while (length < provider.id.length && matches.some(p => p.id !== provider.id && p.id.startsWith(provider.id.slice(0, length)))) length++;
  return provider.name + " · " + provider.provider_type + " · " + (provider.proposed_start_date || "Start not set") + " · Ref " + provider.id.slice(0, length);
}

export function setupProviderCreation({api, roleSelect, setBusy, onCreated}) {
  const open = document.getElementById("add-provider");
  const form = document.getElementById("provider-form");
  const fields = document.getElementById("provider-fields");
  const name = document.getElementById("new-provider-name");
  const start = document.getElementById("new-provider-start");
  const typeSelect = document.getElementById("new-provider-type");
  const save = document.getElementById("save-provider");
  const message = document.getElementById("provider-creation-status");
  const preview = document.getElementById("provider-preview");
  let busy = false;
  let types = [];
  let creationId = null;
  let savedId = null;

  function selectedType() {
    return types.length === 1 ? types[0] : types.find(t => t.id === typeSelect.value);
  }
  function sync() {
    open.hidden = roleSelect.value !== "manager" || !form.hidden;
    open.disabled = busy;
    fields.disabled = busy;
    typeSelect.disabled = types.length < 2;
    save.disabled = busy || roleSelect.value !== "manager" || !creationId || !selectedType() || !name.value.trim() || !start.checkValidity();
  }
  function close() {
    form.hidden = true;
    creationId = null;
    savedId = null;
    sync();
  }
  function renderPreview() {
    const type = selectedType();
    const body = document.getElementById("provider-preview-rows");
    body.replaceChildren();
    preview.hidden = !type;
    document.getElementById("provider-template-count").textContent = type
      ? type.requirements.length + " requirements start Outstanding. Dates and deadlines start Not set." : "";
    if (!type) return;
    for (const requirement of type.requirements) {
      const row = text(body, "tr", "");
      [requirement, "Outstanding", "Not set", "Not set"].forEach(value => text(row, "td", value));
    }
  }
  function renderTypes() {
    typeSelect.replaceChildren();
    types.forEach(type => { const option = text(typeSelect, "option", type.name); option.value = type.id; });
    document.getElementById("provider-type-single").hidden = types.length !== 1;
    document.getElementById("provider-type-name").textContent = types.length === 1 ? types[0].name : "";
    document.getElementById("provider-type-picker").hidden = types.length < 2;
    renderPreview();
    sync();
  }

  open.addEventListener("click", async () => {
    if (busy || roleSelect.value !== "manager") return;
    creationId = crypto.randomUUID();
    savedId = null;
    name.value = "";
    start.value = "";
    types = [];
    form.hidden = false;
    renderTypes();
    message.textContent = "Loading configured provider requirements…";
    setBusy(true);
    try {
      types = await api("/provider-types");
      renderTypes();
      message.textContent = types.length ? "" : "No configured requirements are available. Ask an administrator to configure provider templates.";
    } catch {
      message.textContent = "Provider requirements could not be loaded. Cancel and reopen Add provider to retry.";
    } finally {
      setBusy(false);
      if (!form.hidden) name.focus();
    }
  });

  form.addEventListener("submit", async event => {
    event.preventDefault();
    if (save.disabled || busy || roleSelect.value !== "manager") return;
    const payload = {id: creationId, name: name.value.trim(), provider_type_id: selectedType().id,
      proposed_start_date: start.value || null};
    let saved = false;
    setBusy(true);
    message.textContent = "Saving fictional provider…";
    try {
      const provider = await api("/providers", {method: "POST",
        headers: {"Content-Type": "application/json", "X-Demo-Role": roleSelect.value}, body: JSON.stringify(payload)});
      saved = true;
      savedId = provider.id;
      await onCreated(provider.id);
      close();
      message.textContent = "Provider added. Their checklist is loaded.";
    } catch (error) {
      if (saved) message.textContent = "Provider saved, but the dashboard could not load. Use Refresh data or retry this form.";
      else message.textContent = error.status ? error.message : "The save could not be confirmed. Retry this form to recover the same provider.";
    } finally { setBusy(false); }
  });
  document.getElementById("cancel-provider").addEventListener("click", () => { close(); open.focus(); });
  name.addEventListener("input", sync);
  start.addEventListener("input", sync);
  typeSelect.addEventListener("change", () => { renderPreview(); sync(); });
  const controller = {
    setBusy(value) { busy = value; sync(); },
    syncRole() {
      if (roleSelect.value !== "manager") { close(); message.textContent = ""; }
      sync();
    },
    onProviderLoaded(id) {
      if (savedId === id) { close(); message.textContent = "Provider saved. Their checklist is loaded."; }
    }
  };
  controller.syncRole();
  return controller;
}
