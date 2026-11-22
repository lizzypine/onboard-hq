"use strict";

const key = "onboard-hq:provider-creation:v1";
const id = value => Number.isSafeInteger(value) && value > 0;
const nonblank = value => typeof value === "string" && Boolean(value.trim());
const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const fingerprint = /^[a-f0-9]{64}$/;

function date(value) {
  if (value === null) return true;
  if (typeof value !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(value) || value.startsWith("0000")) return false;
  const parsed = new Date(value + "T12:00:00Z");
  return !Number.isNaN(parsed.getTime()) && parsed.toISOString().slice(0, 10) === value;
}

function fields(value, names) {
  return value && typeof value === "object" && !Array.isArray(value)
    && Object.keys(value).length === names.length && names.every(name => Object.hasOwn(value, name));
}

function valid(attempt) {
  if (!fields(attempt, ["payload", "savedId"]) || !(attempt.savedId === null || id(attempt.savedId))) return false;
  const body = attempt.payload;
  return fields(body, ["creation_request_id", "name", "provider_type_id", "checklist_template_id", "template_fingerprint", "proposed_start_date", "additional_requirements"])
    && typeof body.creation_request_id === "string" && uuid.test(body.creation_request_id)
    && nonblank(body.name) && id(body.provider_type_id) && id(body.checklist_template_id)
    && typeof body.template_fingerprint === "string" && fingerprint.test(body.template_fingerprint)
    && date(body.proposed_start_date) && Array.isArray(body.additional_requirements)
    && body.additional_requirements.every(item => fields(item, ["name", "status", "scheduled_date", "deadline"])
      && nonblank(item.name) && nonblank(item.status) && date(item.scheduled_date) && date(item.deadline));
}

export function readCreationAttempt() {
  const raw = sessionStorage.getItem(key);
  if (raw === null) return null;
  let attempt;
  try { attempt = JSON.parse(raw); } catch { throw new Error("The saved provider draft could not be read."); }
  if (!valid(attempt)) throw new Error("The saved provider draft could not be read.");
  return attempt;
}

export function writeCreationAttempt(attempt) {
  if (!valid(attempt)) throw new Error("The provider save recovery data is invalid.");
  sessionStorage.setItem(key, JSON.stringify(attempt));
}

export function clearCreationAttempt() {
  sessionStorage.removeItem(key);
}
