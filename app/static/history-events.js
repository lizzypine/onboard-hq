"use strict";

function savedTime(value) {
  const fraction = value.match(/\.(\d+)(?:Z|[+-]\d{2}:\d{2})$/)?.[1] || "";
  return BigInt(Date.parse(value)) * 1000n + BigInt((fraction + "000000").slice(3, 6));
}

export function historyEvents(providerId, updates, edits, requirementId = null) {
  const entries = [];
  for (const record of edits) {
    if (record.provider_id === providerId && (requirementId === null || record.requirement_id === requirementId)) {
      entries.push({kind: "edit", id: record.id, at: record.created_at, record});
    }
  }
  for (const update of updates) {
    if (update.provider_id !== providerId) continue;
    if (requirementId === null && (!update.suggestions.length || update.processing_state !== "completed")) {
      entries.push({kind: "update", id: update.id, at: update.created_at, record: update});
    }
    for (const record of update.suggestions) {
      if (requirementId !== null && record.requirement_id !== requirementId) continue;
      entries.push({kind: "suggestion", id: record.id, at: record.decision?.reviewed_at || update.created_at, record, update});
    }
  }
  return entries.sort((a, b) => {
    const first = savedTime(a.at), second = savedTime(b.at);
    return first < second ? 1 : first > second ? -1 : a.kind.localeCompare(b.kind) || b.id - a.id;
  });
}
