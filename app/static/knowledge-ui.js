"use strict";

export const byId = id => document.getElementById(id);
export const versionPath = id => "/knowledge/versions/" + id;
export const versionLabel = (id, revision) => "Version " + id + (revision ? " · " + revision : "");

const hawaiiDate = new Intl.DateTimeFormat("en-CA", {
  timeZone: "Pacific/Honolulu", year: "numeric", month: "2-digit", day: "2-digit"
});

export function dateOrUnknown(value) {
  if (!value) return "Unknown";
  if (/^\d{4}-\d{2}-\d{2}$/.test(value)) return value;
  return hawaiiDate.format(new Date(value));
}

export function element(parent, tag, value = "", className = "") {
  const node = document.createElement(tag);
  node.textContent = value;
  if (className) node.className = className;
  parent.append(node);
  return node;
}

export function action(parent, label, activate, className = "") {
  const button = element(parent, "button", label, className);
  button.type = "button";
  button.addEventListener("click", activate);
  return button;
}

export function metadata(parent, entries) {
  const list = element(parent, "dl", "", "knowledge-metadata");
  for (const [label, value] of entries) {
    element(list, "dt", label);
    element(list, "dd", value ?? "Unknown");
  }
}

export function officialLink(parent, url) {
  if (!url) return;
  try {
    const address = new URL(url);
    if (address.protocol !== "https:") return;
    const link = element(parent, "a", "Official source ↗");
    link.href = address.href;
    link.target = "_blank";
    link.rel = "noopener noreferrer";
  } catch { /* Invalid provenance is displayed without a link. */ }
}

export function originalLink(parent, versionId) {
  const link = element(parent, "a", "Download original");
  link.href = versionPath(versionId) + "/original";
  return link;
}

export function readSavedIdentity(key, fallback) {
  try {
    return JSON.parse(sessionStorage.getItem(key)) ?? fallback;
  } catch { return fallback; }
}

export function rememberIdentity(key, value) {
  try {
    if (value) sessionStorage.setItem(key, JSON.stringify(value));
    else sessionStorage.removeItem(key);
  } catch { /* An unavailable store still permits read recovery in this page. */ }
}

export function isUuid(value) {
  return typeof value === "string" && /^[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}$/i.test(value);
}

export function markdownPreview(parent, source) {
  parent.replaceChildren();
  let block = null;
  for (const line of source.split(/\r?\n/)) {
    const heading = line.match(/^\s{0,3}#{1,6}\s+(.+)$/);
    const bullet = line.match(/^\s*[-*+]\s+(.+)$/);
    if (!line.trim()) {
      block = null;
    } else if (heading) {
      element(parent, "h3", heading[1]);
      block = null;
    } else if (bullet) {
      if (block?.tagName !== "UL") block = element(parent, "ul");
      element(block, "li", bullet[1]);
    } else {
      if (block?.tagName !== "P") block = element(parent, "p");
      block.append((block.textContent ? "\n" : "") + line);
    }
  }
}
