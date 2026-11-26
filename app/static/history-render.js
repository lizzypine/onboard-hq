"use strict";

function text(parent, tag, value, className = "") {
  const node = document.createElement(tag);
  node.textContent = value;
  node.className = className;
  parent.append(node);
  return node;
}

export function renderUpdateEvidence(parent, update, heading = "h3") {
  text(parent, heading, "Original update");
  text(parent, "blockquote", update.update_text);
  text(parent, "p", "Submitted: " + new Date(update.created_at).toLocaleString());
  text(parent, "p", update.processing_state === "processing" ? "Analysis unfinished. No checklist changes were applied." : update.message);
  if (update.ambiguities.length) {
    text(parent, heading, "Warnings and ambiguities");
    const list = text(parent, "ul", "");
    update.ambiguities.forEach(warning => text(list, "li", warning));
  }
}

export function renderSuggestionEvidence(parent, suggestion) {
  text(parent, "h5", "Supporting text");
  text(parent, "blockquote", suggestion.supporting_text);
  if (suggestion.date_text) text(parent, "p", "Original date wording: " + suggestion.date_text);
  if (suggestion.date_explanation) text(parent, "p", "Original inference: " + suggestion.date_explanation);
  if (suggestion.date_requires_confirmation) text(parent, "p", "This proposed date required explicit Manager confirmation.");
}

function change(parent, label, before, after) {
  text(parent, "p", label + ": " + (before || "Not set") + " → " + (after || "Not set"));
}

export function renderHistoryEntry(parent, entry) {
  const card = text(parent, "article", "", "history-entry");
  card.dataset.eventKind = entry.kind;
  card.dataset.eventId = entry.id;
  const record = entry.record;
  if (entry.kind === "edit") {
    card.setAttribute("aria-label", "Manager checklist edit: " + record.requirement_name);
    text(card, "h3", "Manager checklist edit");
    text(card, "h4", record.requirement_name);
    text(card, "p", "Saved by simulated Manager: " + new Date(entry.at).toLocaleString());
    for (const [label, field] of [["Status", "status"], ["Expected completion date", "scheduled_date"], ["Deadline", "deadline"]]) {
      change(card, label, record["previous_" + field], record["applied_" + field]);
    }
    return;
  }
  if (entry.kind === "update") {
    card.setAttribute("aria-label", "Saved update");
    renderUpdateEvidence(card, record);
    return;
  }
  const decision = record.decision;
  card.setAttribute("aria-label", (decision ? "Review: " : "Proposal: ") + record.requirement);
  text(card, "h3", record.requirement);
  if (decision) {
    text(card, "h4", {approved: "Approved", corrected: "Approved with corrections", rejected: "Rejected"}[decision.outcome]);
    text(card, "p", "Reviewed by simulated Manager: " + new Date(decision.reviewed_at).toLocaleString());
    if (decision.outcome === "rejected") {
      text(card, "p", "No checklist change was applied.");
      change(card, "Status", decision.previous_status, decision.previous_status);
      change(card, "Expected completion date", decision.previous_scheduled_date, decision.previous_scheduled_date);
    } else {
      change(card, "Status", decision.previous_status, decision.applied_status);
      change(card, "Expected completion date", decision.previous_scheduled_date, decision.applied_scheduled_date);
      text(card, "p", "Applied status: " + decision.applied_status);
      text(card, "p", "Applied date: " + (decision.applied_scheduled_date || "Not set"));
    }
  } else {
    text(card, "h4", entry.update.processing_state === "completed" ? "Awaiting manager review" : "Analysis is unfinished; this cannot be reviewed.");
    text(card, "p", "Pending review controls are beneath the matching checklist requirement.");
  }
  text(card, "p", "Proposed status: " + record.proposed_status);
  text(card, "p", "Proposed date: " + (record.proposed_date || "Not specified"));
  renderUpdateEvidence(card, entry.update, "h4");
  renderSuggestionEvidence(card, record);
}
