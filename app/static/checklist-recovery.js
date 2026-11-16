"use strict";

export const legacyAttemptKey = "onboard-hq:pending-checklist-edit";
const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export function inspectLegacyAttempt(storage) {
  try {
    const value = JSON.parse(storage.getItem(legacyAttemptKey));
    if (value && uuid.test(value.providerId) && uuid.test(value.requirementId) && uuid.test(value.body?.id)
        && typeof value.providerName === "string" && typeof value.body.status === "string"
        && Number.isInteger(value.body.expected_version) && value.body.expected_version >= 0
        && [value.body.scheduled_date, value.body.deadline].every(d => d === null || typeof d === "string")) return value;
  } catch { /* Keep the original entry; unavailable storage is not proof of a failed save. */ }
  return null;
}

export async function recoverLegacyAttempt({api, attempt}) {
  try {
    const providers = await api("/providers?state=all");
    const provider = providers.find(p => p.creation_request_id.toLowerCase() === attempt.providerId.toLowerCase());
    if (!provider) return {kind: "unavailable", provider: null, event: null};
    const history = await api("/providers/" + provider.id + "/checklist-edits");
    const event = history.find(e => e.operation_id.toLowerCase() === attempt.body.id.toLowerCase());
    if (!event) return {kind: "unresolved", provider, event: null};
    const matches = event.provider_id === provider.id && event.expected_version === attempt.body.expected_version
      && event.applied_status === attempt.body.status && event.applied_scheduled_date === attempt.body.scheduled_date
      && event.applied_deadline === attempt.body.deadline;
    return {kind: matches ? "saved" : "unresolved", provider, event};
  } catch {
    return {kind: "unavailable", provider: null, event: null};
  }
}
