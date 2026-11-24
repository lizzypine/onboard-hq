"use strict";

import {action, dateOrUnknown, element, metadata, officialLink, originalLink, versionPath} from "./knowledge-ui.js";

export const outcomes = {
  supported: "Supported answer",
  more_information_needed: "More information needed",
  conflicting_guidance: "Conflicting guidance",
  cannot_answer: "Cannot answer from the available information",
  service_unavailable: "Service unavailable"
};

function retainedSource(parent, citation, {api, getRole}) {
  const view = element(parent, "div", "", "knowledge-retained");
  view.setAttribute("role", "region");
  view.setAttribute("aria-label", "Retained source");
  view.hidden = true;
  let loaded = false;
  const open = action(parent, "View retained source", async () => {
    view.hidden = !view.hidden;
    open.setAttribute("aria-expanded", String(!view.hidden));
    if (view.hidden || loaded) return;
    open.disabled = true;
    view.textContent = "Loading retained source…";
    try {
      const version = await api(versionPath(citation.version_id), {headers: {"X-Demo-Role": getRole()}});
      view.replaceChildren();
      element(view, "h4", "Retained source");
      element(view, "p", version.document.title + " · " + version.status);
      const links = element(view, "div", "", "knowledge-actions");
      originalLink(links, version.id);
      officialLink(links, version.document.original_url);
      element(view, "pre", version.text);
      loaded = true;
    } catch {
      view.textContent = "The retained version could not load. Close and reopen this source view to check again.";
    } finally { open.disabled = false; }
  });
  open.setAttribute("aria-expanded", "false");
  open.after(view);
}

function renderCitation(parent, citation, number, options) {
  const detail = element(parent, "details", "", "knowledge-citation");
  element(detail, "summary", "[" + number + "] " + citation.source_title);
  const body = element(detail, "div", "", "knowledge-citation-body");
  element(body, "p", citation.source_kind === "official" ? "Official guidance" : "Internal procedure", "knowledge-badge");
  element(body, "blockquote", citation.quote);
  const rows = [
    ["Authority", citation.publisher],
    ["Revision", citation.stated_revision],
    ["Section", citation.section],
    ["Page", citation.page],
    ["Characters", citation.char_start + "–" + citation.char_end],
    ["Reviewed", dateOrUnknown(citation.reviewed_at)],
    ["Effective from", dateOrUnknown(citation.effective_from)],
    ["Effective through", dateOrUnknown(citation.effective_to)]
  ];
  metadata(body, rows);
  const links = element(body, "div", "", "knowledge-actions");
  officialLink(links, citation.original_url);
  retainedSource(body, citation, options);
}

export function renderAnswer(parent, answer, options, historical = false) {
  parent.replaceChildren();
  if (historical) element(parent, "p", "Historical answer", "knowledge-badge");
  if (answer.outdated) {
    const warning = element(parent, "div", "", "knowledge-warning");
    element(warning, "strong", "Outdated guidance");
    element(warning, "p", answer.historical_source_warning);
  }
  element(parent, "h3", outcomes[answer.outcome], "answer-outcome " + answer.outcome);
  element(parent, "p", answer.question, "knowledge-answer-question");
  if (answer.requirement_name) element(parent, "p", answer.requirement_name, "knowledge-muted");
  for (const value of [answer.explanation, answer.conflict_explanation, answer.failure_message]) {
    if (value) element(parent, "p", value);
  }
  if (answer.missing_facts) {
    element(parent, "h4", "Information needed");
    element(parent, "p", answer.missing_facts);
  }
  let number = 0;
  for (const claim of answer.claims) {
    element(parent, "p", claim.text);
    for (const citation of claim.citations) renderCitation(parent, citation, ++number, options);
  }
}
