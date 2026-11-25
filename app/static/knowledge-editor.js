"use strict";

import {action, dateOrUnknown, element, markdownPreview, metadata, officialLink, originalLink, versionLabel, versionPath} from "./knowledge-ui.js";

function field(parent, label, value, type = "text") {
  const wrapper = element(parent, "label", label);
  const input = element(wrapper, "input");
  input.type = type;
  input.value = value ?? "";
  if (type === "text") input.maxLength = 500;
  return input;
}

function select(parent, label, selected, choices) {
  const input = element(element(parent, "label", label), "select");
  for (const choice of choices) element(input, "option", choice).value = choice;
  if (!choices.includes(selected)) element(input, "option", selected + " (not configured)").value = selected;
  input.value = selected;
  return input;
}

function checkbox(parent, label) {
  const wrapper = element(parent, "label", "", "knowledge-check");
  const input = element(wrapper, "input");
  input.type = "checkbox";
  wrapper.append(label);
  return input;
}

function scopeEditor(parent, scopes, options, selectedType, edit) {
  const box = element(parent, "fieldset", "", "knowledge-scopes");
  element(box, "legend", "Applicability");
  const container = element(box, "div");
  const drafts = scopes.map(scope => ({...scope}));
  function draw() {
    container.replaceChildren();
    drafts.forEach((scope, index) => {
      const row = element(container, "div", "", "knowledge-scope-row");
      const label = "Scope " + (index + 1);
      const type = select(row, label + " provider type", scope.provider_type, options.providerTypes);
      const region = select(row, label + " jurisdiction", scope.jurisdiction, [options.default_scope.jurisdiction]);
      const topic = select(row, label + " topic", scope.topic, options.topics);
      for (const [input, name] of [[type, "provider_type"], [region, "jurisdiction"], [topic, "topic"]]) {
        input.addEventListener("change", () => { scope[name] = input.value; });
        input.disabled = !edit;
      }
      if (edit) {
        const remove = action(row, "Remove scope " + (index + 1), () => {
          drafts.splice(index, 1);
          draw();
          box.dispatchEvent(new Event("change", {bubbles: true}));
          (container.querySelector("select") || add).focus();
        });
        remove.disabled = drafts.length === 1;
      }
    });
    add.hidden = !edit || drafts.length >= 128;
  }
  const add = action(box, "Add scope", () => {
    const provider_type = options.providerTypes.includes(selectedType)
      ? selectedType : options.default_scope.provider_type;
    drafts.push({...options.default_scope, provider_type});
    draw();
    container.lastElementChild.querySelector("select").focus();
    box.dispatchEvent(new Event("change", {bubbles: true}));
  });
  draw();
  return drafts;
}

function renderOriginal(parent, version, onError) {
  officialLink(parent, version.document.original_url);
  if (version.status !== "draft") {
    originalLink(parent, version.id);
    return;
  }
  const download = action(parent, "Download original", async () => {
    download.disabled = true;
    try {
      const response = await fetch(versionPath(version.id) + "/original", {headers: {"X-Demo-Role": "manager"}});
      if (!response.ok) throw new Error("download unavailable");
      const url = URL.createObjectURL(await response.blob());
      const link = document.createElement("a");
      link.href = url;
      const format = {"application/pdf": "pdf", "text/html": "html", "text/plain": "txt"};
      link.download = "knowledge-" + version.id + "." + format[version.media_type];
      link.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch {
      onError("The retained original could not download. Try again.");
    } finally { download.disabled = false; }
  });
}

function metadataFields(parent, version, edit) {
  const grid = element(parent, "div", "", "knowledge-date-fields");
  const revision = field(grid, "Stated source revision", version?.stated_revision);
  const from = field(grid, "Effective from", version?.effective_from, "date");
  const through = field(grid, "Effective through", version?.effective_to, "date");
  for (const input of [revision, from, through]) input.readOnly = !edit;
  return () => ({
    stated_revision: revision.value.trim() || null,
    effective_from: from.value || null,
    effective_to: through.value || null
  });
}

function issueFields(parent, issues, edit) {
  if (!edit && !issues.length) return () => [];
  const fieldset = element(parent, "fieldset");
  element(fieldset, "legend", "Unresolved review issues");
  const resolved = new Map();
  for (const issue of issues) {
    if (edit) resolved.set(issue, checkbox(fieldset, "Resolve: " + issue));
    else element(fieldset, "p", issue);
  }
  let added;
  if (edit) {
    const label = element(fieldset, "label", issues.length ? "Additional unresolved issues" : "Unresolved issues, one per line");
    added = element(label, "textarea");
    added.rows = 2;
  }
  return () => [...issues.filter(issue => !resolved.get(issue)?.checked),
    ...(added?.value.split(/\r?\n/).map(issue => issue.trim()).filter(Boolean) || [])];
}

export function renderSourceEditor(parent, {version, document: doc, options, selectedType, submit, onError}) {
  parent.replaceChildren();
  const edit = !version || version.status === "draft";
  const root = element(parent, "div");
  if (version) {
    const links = element(root, "div", "", "knowledge-actions");
    renderOriginal(links, version, onError);
    const provenance = element(root, "details", "", "knowledge-citation");
    element(provenance, "summary", "Provenance and passage locations");
    const body = element(provenance, "div", "", "knowledge-citation-body");
    metadata(body, [
      ["Retained version", versionLabel(version.id, version.stated_revision)], ["Publisher", doc.publisher],
      ["Retrieved", dateOrUnknown(version.retrieved_at)], ["Reviewed", dateOrUnknown(version.reviewed_at)],
      ["Effective from", dateOrUnknown(version.effective_from)], ["Effective through", dateOrUnknown(version.effective_to)],
      ["SHA-256", version.checksum]
    ]);
    const list = element(body, "ul");
    for (const chunk of version.chunks) {
      element(list, "li", [chunk.section, chunk.page ? "Page " + chunk.page : null,
        "Characters " + chunk.char_start + "–" + chunk.char_end].filter(Boolean).join(" · "));
    }
  }

  const form = element(root, "form");
  const internal = doc.source_kind === "internal";
  const label = element(form, "label", internal ? "Internal instructions" : "Extracted official text");
  const sourceText = element(label, "textarea");
  sourceText.value = version?.text || "";
  const displayedText = sourceText.value;
  sourceText.readOnly = !edit || !internal;
  sourceText.required = true;
  sourceText.rows = 6;
  sourceText.maxLength = 2000000;
  if (internal) {
    const preview = element(form, "details", "", "knowledge-citation");
    element(preview, "summary", "Preview instructions");
    const previewBody = element(preview, "div", "", "knowledge-preview knowledge-citation-body");
    const renderPreview = () => { if (preview.open) markdownPreview(previewBody, sourceText.value); };
    preview.addEventListener("toggle", renderPreview);
    sourceText.addEventListener("input", renderPreview);
  }

  const getDates = metadataFields(form, version, edit);
  const scopes = scopeEditor(form, version?.scopes || [options.default_scope], options, selectedType, edit);
  const reviewIssues = issueFields(form, version?.review_issues || [], edit);
  const fields = () => ({
    text: version && (sourceText.readOnly || sourceText.value === displayedText) ? version.text : sourceText.value,
    scopes, review_issues: reviewIssues(), ...getDates()
  });
  const original = JSON.stringify(fields());
  let locked = false;
  if (!edit) {
    const actions = element(form, "div", "", "knowledge-actions");
    if (version.status === "published") {
      const confirm = action(actions, "Confirm withdrawal", () => submit("withdraw", {expected_revision: version.draft_revision}));
      confirm.hidden = true;
      const withdraw = action(actions, "Withdraw version", () => {
        confirm.hidden = false;
        withdraw.hidden = true;
        confirm.focus();
      });
      return {lock(value) { confirm.disabled = withdraw.disabled = value; }};
    }
    return {lock() {}};
  }

  const reviewed = version && checkbox(form, "I reviewed the source, applicability and unresolved issues.");
  const unsupported = element(form, "p", "", "knowledge-warning");
  const actions = element(form, "div", "", "knowledge-actions");
  const save = element(actions, "button", version ? "Save draft" : "Create draft", "primary");
  save.type = "submit";
  const publish = version && action(actions, "Publish reviewed version", () => {
    submit("publish", {expected_revision: version.draft_revision, confirmed_review: true});
  });

  function sync() {
    const dirty = JSON.stringify(fields()) !== original;
    const invalidTopic = scopes.some(scope => !options.topics.includes(scope.topic.toLowerCase()));
    unsupported.hidden = !invalidTopic;
    unsupported.textContent = invalidTopic ? "Select supported topics before publishing." : "";
    save.disabled = locked || !dirty || !sourceText.value.trim();
    if (publish) {
      if (dirty) reviewed.checked = false;
      reviewed.disabled = locked || dirty || invalidTopic || Boolean(version.review_issues.length);
      publish.disabled = reviewed.disabled || !reviewed.checked;
    }
  }

  form.addEventListener("input", sync);
  form.addEventListener("change", sync);
  form.addEventListener("submit", event => {
    event.preventDefault();
    if (save.disabled) return;
    const draft = fields();
    if ((draft.effective_from && draft.effective_to && draft.effective_to < draft.effective_from)
        || draft.review_issues.some(issue => issue.length > 500) || draft.review_issues.length > 100
        || new Set(draft.review_issues).size !== draft.review_issues.length
        || new Set(draft.scopes.map(scope => JSON.stringify(scope))).size !== draft.scopes.length) {
      onError("Use an ordered effective period and distinct scopes and review issues. Limit issues to 100 entries of 500 characters.");
      return;
    }
    if (version) draft.expected_revision = version.draft_revision;
    submit(version ? "edit" : "create", draft);
  });
  sync();
  return {
    lock(value) {
      locked = value;
      for (const input of form.querySelectorAll("input, select, textarea, button")) input.disabled = value;
      if (!value) {
        for (const remove of form.querySelectorAll(".knowledge-scope-row button")) remove.disabled = scopes.length === 1;
      }
      sync();
    }
  };
}
