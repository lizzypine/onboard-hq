"use strict";

export function orderChecklist(requirements) {
  return [...requirements].sort((a, b) => {
    if (Boolean(a.deadline) !== Boolean(b.deadline)) return a.deadline ? -1 : 1;
    return (a.deadline || "").localeCompare(b.deadline || "") || a.name.localeCompare(b.name);
  });
}
