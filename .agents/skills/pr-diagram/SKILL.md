---
name: pr-diagram
description: Use when a pull request is ready to open, has just been opened, or is being refreshed after code changes. Not for read-only pull-request questions or status checks.
---

# PR Diagram

Add exactly one code-verified Mermaid diagram of the change to the PR description.
Never edit application code, tests, or repository files while applying this skill.

## Read the Change

Read the **Changes** section of the repository's `AGENTS.md` first. Resolve the
current branch's PR, base, head, and existing description with `gh pr view`.
Read the full PR-range diff, not only uncommitted changes or the latest commit:
use the actual PR base and head with `git diff BASE...HEAD` and its name/status
list. If revisions are unavailable locally, fetch them or read the PR diff.
For a PR not yet opened, use the intended base and the complete proposed branch
diff and description. Do not guess the base from a branch name.

Read the relevant current code and base-revision code for moves/deletions. Build
a small evidence list mapping each node and arrow to its file, symbol, and
revision; this list is for verification, not another section in the PR.

## Choose One View

| Change | Diagram |
| --- | --- |
| A new or newly connected request path | `sequenceDiagram`: the implemented request flow. |
| A module split or responsibility move | `flowchart LR`: Before and After subgraphs showing the split. |

If both apply, choose the view that explains the main behavioral change; do not
add a second diagram. If neither can be supported by the diff, report that rather
than inventing a path or editing code to create one.

- Use at most **eight nodes total**: sequence participants, or boxes across both
  Before and After views. A repeated before/after file counts twice.
- Every node must name an actual file or function changed, added, moved, or deleted
  in the PR diff. Base-only nodes must be clearly labeled Before.
- Omit abstract actors such as User, Model, Database, and unmodified dependencies.
- Check every arrow against the code: caller/callee, import/re-export, return,
  conditional path, or definition moved between the two revisions. Label its
  meaning. At file level, a call through a helper in that file is valid; identify
  the helper when needed. Do not imply direct calls, writes, ordering, or failure
  behavior the implementation does not contain.
- Keep only the calls or relationships needed to explain the change. Use Mermaid
  aliases for readable labels; verify syntax and the eight-node limit.

## Preserve and Publish

Keep **Summary**, **Test plan**, their contents/checklist states, and all other
non-diagram text intact. Place a `## Change diagram` section before Test plan,
with one fenced `mermaid` block between `<!-- pr-diagram:start -->` and
`<!-- pr-diagram:end -->`. On subsequent runs, replace that marked section instead
of appending. An unmarked, single existing change diagram can be replaced in
place. If multiple diagrams or ambiguous ownership prevent preserving the body
with exactly one diagram, report the conflict rather than deleting author text.

For an existing PR, confirm its head and body have not changed since reading;
if they have, re-read and reconcile before editing. Write the complete preserved
body to a temporary file and use `gh pr edit PR --body-file FILE` within the
authorized PR workflow. For a PR ready to open, supply that body file to the
owning workflow; this skill does not independently open a PR, push, or merge.

Re-read the resulting body: verify one Mermaid block, at most eight nodes,
code-backed arrows, and unchanged Summary/Test plan. Report the PR URL and the
diagram type. If remote editing is unavailable, deliver the prepared body file
and state that it has not been applied.
