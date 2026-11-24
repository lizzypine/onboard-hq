"use strict";

import {renderSourceEditor} from "./knowledge-editor.js";
import {action, byId, element, isUuid, readSavedIdentity, rememberIdentity, versionLabel, versionPath} from "./knowledge-ui.js";

const operationKey = "onboard-hq:pending-source-operation:v1";
const manager = {"X-Demo-Role": "manager"};
const labels = {draft: "Draft", published: "Published", superseded: "Superseded", withdrawn: "Withdrawn"};
const receipts = {create: "Draft created.", edit: "Draft saved.", publish: "Version published.", withdraw: "Version withdrawn."};

export function setupKnowledgeManager({api, getRole, getProvider}) {
  const section = byId("knowledge-sources");
  const catalog = byId("source-catalog");
  const catalogStatus = byId("source-catalog-status");
  const dialog = byId("source-dialog");
  const editor = byId("source-editor");
  const editorStatus = byId("source-editor-status");
  const reload = byId("reload-sources");
  const reloadVersion = byId("reload-source-version");
  const checkers = [byId("check-source-operation"), byId("check-editor-operation")];
  const dismissers = [byId("dismiss-source-operation"), byId("dismiss-editor-operation")];

  const restored = readSavedIdentity(operationKey, null);
  let pending = isUuid(restored?.id) && Object.hasOwn(receipts, restored.action) ? restored : null;
  let checking = false;
  let dismissible = false;
  let loading = null;
  let view = null;
  let focusKey = null;
  const active = () => getRole() === "manager";
  const current = context => active() && dialog.open && view === context;
  const read = path => api(path, {headers: manager});

  function remember(operation) {
    pending = operation;
    dismissible = false;
    rememberIdentity(operationKey, operation && {id: operation.id, action: operation.action, documentId: operation.documentId});
    syncRecovery();
  }

  function syncRecovery() {
    for (const control of checkers) {
      control.hidden = !pending || Boolean(pending.sending);
      control.disabled = checking;
    }
    for (const control of dismissers) control.hidden = !dismissible || !pending || checking;
    view?.form?.lock(Boolean(pending));
  }

  function renderCatalog(documents) {
    catalog.replaceChildren();
    if (!documents.length) element(catalog, "p", "No licensing sources have been imported.");
    for (const doc of documents) {
      const row = element(catalog, "article", "", "knowledge-source-row");
      row.setAttribute("aria-label", doc.title);
      const identity = element(row, "div", "", "knowledge-source-identity");
      element(identity, "h3", doc.title);
      const kind = doc.source_kind === "official" ? "Official guidance" : "Internal procedure";
      element(identity, "p", kind + " · " + doc.publisher, "knowledge-muted");
      if (!doc.versions.length) element(identity, "p", "No source versions.", "knowledge-muted");
      const versions = element(row, "div", "", "knowledge-source-versions");
      for (const version of doc.versions) {
        const line = element(versions, "div", "", "knowledge-source-version");
        const description = element(line, "div", "", "knowledge-source-description");
        element(description, "span", labels[version.status], "knowledge-badge " + version.status);
        element(description, "span", versionLabel(version.id, version.stated_revision), "knowledge-muted");
        const label = version.status === "draft" ? "Review draft" : "View " + version.status + " version";
        const button = action(line, label, event => open(doc, version.id, event.currentTarget));
        button.dataset.sourceVersion = version.id;
      }
      if (doc.source_kind === "internal") {
        const button = action(versions, "Create internal draft", event => open(doc, null, event.currentTarget));
        button.dataset.sourceDocument = doc.id;
      }
    }
  }

  async function loadCatalog(message = "") {
    const token = Symbol();
    loading = token;
    reload.hidden = true;
    catalogStatus.textContent = "Loading licensing sources…";
    try {
      const documents = await read("/knowledge/documents");
      if (!active() || loading !== token) return;
      renderCatalog(documents);
      catalogStatus.textContent = message || (pending && !pending.sending ? "A source operation needs confirmation." : "");
      return documents;
    } catch {
      if (!active() || loading !== token) return;
      catalogStatus.textContent = message ? message + " The source catalog could not refresh." : "Licensing sources could not load.";
      reload.hidden = false;
    }
  }

  async function loadEditor(context, message = "") {
    context.form = null;
    const token = Symbol();
    context.loading = token;
    editor.replaceChildren();
    editorStatus.textContent = message || "Loading saved source…";
    reloadVersion.hidden = true;
    try {
      const [version, options, types] = await Promise.all([
        context.versionId ? read(versionPath(context.versionId)) : null,
        read("/knowledge/review-options"),
        api("/provider-types")
      ]);
      if (!current(context) || context.loading !== token) return;
      const doc = version?.document || context.document;
      byId("source-context").textContent = [
        doc.title, doc.source_kind === "official" ? "Official guidance" : "Internal procedure",
        labels[version?.status]
      ].filter(Boolean).join(" · ");
      context.form = renderSourceEditor(editor, {
        version, document: doc, options: {...options, providerTypes: types.map(type => type.name)},
        selectedType: getProvider()?.provider_type,
        submit: (kind, draft) => submit(context, kind, draft),
        onError: text => { editorStatus.textContent = text; }
      });
      editorStatus.textContent = message;
      syncRecovery();
      return true;
    } catch {
      if (!current(context) || context.loading !== token) return;
      editorStatus.textContent = message ? message + " The saved version could not refresh." : "The saved version could not load.";
      reloadVersion.hidden = false;
    }
  }

  function open(doc, versionId, invoker) {
    if (!active() || dialog.open) return;
    const context = {document: doc, versionId, invoker};
    view = context;
    focusKey = invoker.dataset;
    byId("source-context").textContent = doc.title;
    dialog.showModal();
    dialog.scrollTop = 0;
    loadEditor(context);
    if (pending && !pending.sending) reconcile();
  }

  async function showReceipt(operation, receipt) {
    if (pending !== operation) return;
    if (operation.id !== receipt.operation_id || operation.action !== receipt.action) {
      throw new Error("Operation identity did not match.");
    }
    const message = receipts[receipt.action];
    if (!active()) return;
    const documents = await loadCatalog(message);
    if (!active()) return;
    const context = dialog.open ? view : null;
    if (!documents) {
      if (context) editorStatus.textContent = message + " The source catalog could not refresh.";
      return;
    }
    const document = documents.find(doc => doc.versions.some(version => version.id === receipt.version_id));
    if (!document || (operation.documentId != null && operation.documentId !== document.id)) {
      throw new Error("Operation source did not match.");
    }
    const matchingCreate = operation.action === "create" && context?.versionId === null
      && context.document.id === document.id;
    if (context?.versionId === receipt.version_id || matchingCreate) {
      context.versionId = receipt.version_id;
      focusKey = {sourceVersion: receipt.version_id};
      if (!await loadEditor(context, message)) return;
    } else if (context) {
      editorStatus.textContent = "The source operation was confirmed in the catalog.";
    }
    remember(null);
  }

  async function reconcile() {
    const operation = pending;
    if (!active() || !operation || checking || operation.sending) return;
    checking = true;
    const status = dialog.open ? editorStatus : catalogStatus;
    status.textContent = "Checking saved source operation…";
    syncRecovery();
    try {
      const receipt = await read("/knowledge/operations/" + operation.id);
      await showReceipt(operation, receipt);
    } catch (error) {
      if (!active() || pending !== operation) return;
      dismissible = error.status === 404;
      const message = dismissible
        ? "There is no saved receipt yet. Check again or dismiss this unconfirmed operation."
        : "The operation could not be confirmed. Check again for a saved receipt.";
      catalogStatus.textContent = message;
      if (dialog.open) editorStatus.textContent = message;
    } finally {
      checking = false;
      syncRecovery();
    }
  }

  async function submit(context, kind, draft) {
    if (!current(context) || pending) return;
    const id = crypto.randomUUID();
    const body = JSON.stringify({...draft, operation_id: id});
    const base = versionPath(context.versionId);
    const path = {create: "/knowledge/documents/" + context.document.id + "/drafts", edit: base,
      publish: base + "/publish", withdraw: base + "/withdraw"}[kind];
    const operation = {id, action: kind, sending: true,
      documentId: kind === "create" ? context.document.id : undefined};
    remember(operation);
    editorStatus.textContent = kind === "publish" ? "Indexing and publishing source…" : "Saving source operation…";
    try {
      const receipt = await api(path, {method: kind === "edit" ? "PUT" : "POST",
        headers: {...manager, "Content-Type": "application/json"}, body});
      await showReceipt(operation, receipt);
    } catch (error) {
      if (pending !== operation) return;
      const definite = error.status && error.status < 500;
      if (definite) remember(null);
      const message = definite ? error.message : (kind === "publish" ? "Publication" : "The source operation")
        + " could not be confirmed. " + (error.status ? error.message + " " : "") + "Check for a saved receipt.";
      catalogStatus.textContent = message;
      if (current(context)) {
        editorStatus.textContent = message;
        reloadVersion.hidden = error.status !== 409 || !context.versionId;
      }
    } finally {
      operation.sending = false;
      syncRecovery();
    }
  }

  dialog.querySelector(".knowledge-close").addEventListener("click", () => dialog.close());
  dialog.addEventListener("close", () => {
    if (dialog.open) return;
    const invoker = view?.invoker;
    view = null;
    if (!active()) return;
    const replacement = [...catalog.querySelectorAll("button")].find(button => focusKey &&
      ((focusKey.sourceVersion && button.dataset.sourceVersion === String(focusKey.sourceVersion))
        || (focusKey.sourceDocument && button.dataset.sourceDocument === focusKey.sourceDocument)));
    (replacement || (invoker?.isConnected && invoker) || catalog.querySelector("button") || reload).focus();
  });
  reload.addEventListener("click", () => loadCatalog());
  reloadVersion.addEventListener("click", () => { if (view) loadEditor(view); });
  for (const button of checkers) button.addEventListener("click", reconcile);
  for (const button of dismissers) button.addEventListener("click", () => {
    remember(null);
    if (dialog.open) editorStatus.textContent = "Unconfirmed operation dismissed. Reload the saved version before deciding.";
    catalogStatus.textContent = "Unconfirmed operation dismissed.";
    if (view?.versionId) reloadVersion.hidden = false;
  });

  return {
    syncRole() {
      section.hidden = !active();
      if (!active()) {
        loading = null;
        if (dialog.open) dialog.close();
        catalog.replaceChildren();
        return;
      }
      syncRecovery();
      loadCatalog();
      if (pending && !pending.sending) reconcile();
    }
  };
}
