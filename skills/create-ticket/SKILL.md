---
description: Publish drafted tickets to whichever ticket system the project uses — create each issue, assign its key, link parents to children, and resolve cross-reference placeholders. The only place backend-specific creation lives; callers pass a draft and get back a letter-to-key map.
---

# Create tickets — the one place backends differ

You are a worker agent with **no prior conversation**. You take drafted ticket bodies and
publish them to a ticket system.

**You are an abstraction boundary, and that is your reason to exist.** Every caller drafts
tickets the same way and hands them to you; only you know that GitHub needs a second call
to rename the issue after creation, that Linear takes a parent id at creation time, and
that JIRA calls the relationship an issue link. **Adding a ticket system is a change inside
this file and nowhere else.** Never leak a backend detail back to a caller — not in your
report, not as a required argument.

## Step 1 — Arguments, and blocking on a missing one

- **`--system`** — `github` | `linear` | `jira`. Missing → `CREATE BLOCKED: no --system`.
  **Never infer it** from which MCP servers happen to be connected; the project declares it.
- **`--prefix`** — the ticket key prefix (`BILL`). Missing → `CREATE BLOCKED: no --prefix`.
- **`--draft`** — path to the drafted tree, or to a single drafted body. Missing →
  `CREATE BLOCKED: no --draft`.
- **`--tracking-dir` / `--archive-dir`** — needed for the collision check below. **Never
  resolve these yourself**; the orchestrator is the sole resolver.
- Backend coordinates: `--owner`/`--repo` for `github`, `--team` for `linear`,
  `--project`/`--cloud-id` for `jira`.

An unknown `--system` → `CREATE BLOCKED: unsupported system '<x>'`. Do not guess a
neighbouring backend — creating tickets in the wrong tracker is not recoverable by a retry.

## Step 2 — Create, in draft order

Create parents before children, so a child always has a real parent to point at.

### `github`

1. `gh issue create --repo $OWNER/$REPO --title "<title>" --body-file <tmp>`.
   **Write the body to a temp file.** Drafted markdown contains backticks and `$`; a
   heredoc-inlined body is shell-hazardous and can execute part of itself.
   Capture the issue number `$N` from the printed URL.
2. **Assign the key: `$KEY = $PREFIX-$N`.** This is the invariant the whole system rests
   on — `BILL-N` *is* GitHub issue `#N`, so every later step resolves an issue number by
   stripping digits, with no mapping file to keep in sync.
3. **Collision check before committing to the key.** `$KEY` is in use if *any* holds:
   `$TRACKING_DIR/$KEY/` exists and is non-empty; `$ARCHIVE_DIR/$KEY/` exists and is
   non-empty; or an issue already carries `$KEY:` or `[$KEY]` in its title
   (`gh issue list --search "$KEY" --json number,title --repo "$OWNER/$REPO"`, then match
   the prefix exactly — a substring match will false-positive on `BILL-12` vs `BILL-120`).
   On collision, try `$PREFIX-${N}a`, `${N}b` … `${N}z`, **re-running all three checks each
   time**. First clean suffix wins. All of `a`–`z` taken → `CREATE BLOCKED: key collision,
   $PREFIX-${N}a through ${N}z all in use`. The issue stays open; report its URL rather
   than deleting it.
4. Rewrite the title to `"$KEY: <title>"`. On failure, warn and continue — the issue exists
   and the key is already correct; a cosmetic title is not worth failing a run over.

### `linear`

`save_issue(team=$TEAM, title=…, description=…, parentId=<parent's id or null>)`. Linear
mints its own identifier — **use it as `$KEY` verbatim**. Do not synthesise a
`$PREFIX-N` key and do not rename anything to match; the tracker's own identifier is the
key, and inventing a parallel one is how two names for one ticket start.

### `jira`

`createJiraIssue(cloudId=$CLOUD_ID, projectKey=$PROJECT, summary=…, description=…)`. As
with Linear, JIRA's returned key **is** `$KEY`.

## Step 3 — Link parents to children

Umbrella → leaf, after both exist.

- **`github`** — the sub-issues API takes the child's **database id**, not its number.
  Passing the number silently links the wrong issue or 404s:
  ```bash
  cid=$(gh api "repos/$OWNER/$REPO/issues/$CHILD" --jq .id)
  gh api -X POST "repos/$OWNER/$REPO/issues/$PARENT/sub_issues" -F sub_issue_id="$cid"
  ```
  `Blocked by:` has no native field — it stays as body text.
- **`linear`** — already done, via `parentId` at creation.
- **`jira`** — an issue link of the project's configured subtask/relates type.

## Step 3a — Apply the mode label, where the draft asks for one

A draft may declare a ticket's **mode** — `refactor` or `backfill`. Mode is carried by a
label, never by body text (`:run`'s invariant-tickets section is the one definition). Exactly
two names, fixed, not configurable:

| mode | label |
|---|---|
| refactor | `slopstop-refactor` |
| backfill | `slopstop-backfill` |
| normal | *no label* — absence is the declaration; do not invent a third name |

**Ensure, then apply.** Two of the three backends reject an unknown label rather than
creating it, so applying without ensuring fails on a fresh project — and it fails at exactly
the moment the ticket most needs the label, because an unlabelled ticket runs as normal and
skips the gates the mode exists to impose.

- **`github`** — the label must exist first. Check `gh label list --repo "$OWNER/$REPO"
  --json name -q '.[].name'` for an exact match; create it if absent
  (`gh label create "<label>" --repo "$OWNER/$REPO" --description "<desc>"`); then
  `gh issue edit "$N" --repo "$OWNER/$REPO" --add-label "<label>"`.
- **`linear`** — the label must exist first. `list_issue_labels(name: "<label>")`, then
  `create_issue_label(name: "<label>")` if absent, then attach it via `save_issue`.
  **Never write the label with a `:` or `/` in it.** Linear reads `group:label` and
  `group/label` as label-*group* syntax, so a colon-separated name silently becomes a group
  plus a differently-named child. The hyphen is load-bearing.
- **`jira`** — labels are free-form; no creation step exists or is needed. Set the `labels`
  field on the issue.

**Idempotent by construction.** An existing label is used as-is — never recreated, never
recoloured, never edited. Re-running against a ticket that already carries the label is a
no-op, not a duplicate.

**Never apply both labels to one ticket.** A ticket carrying both freezes the whole
repository — refactor freezes every test file, backfill every production file — and `:run`
stops it. If a draft asks for both, that is a drafting defect: report
`CREATE PARTIAL` naming the ticket, and apply neither.

Descriptions, when creating:
- `slopstop-refactor` → `"slopstop: production code only — no test file may change"`
- `slopstop-backfill` → `"slopstop: tests only — no production file may change"`

## Step 4 — Resolve placeholders

A draft cross-references tickets that did not exist when it was written, using `%%A%%`
tokens — a shape that cannot collide with prose. Once every ticket exists, build the
letter → key map and rewrite each published body.

**Then grep every published body for `%%`.** Any remaining hit is an unresolved reference:
report it as a failure, naming the ticket and the token. A dangling `%%B%%` in a live
ticket is worse than a missing link, because it reads as a typo rather than a broken
reference and nobody chases it.

## Step 5 — Report

```
CREATE <verdict>
System:  <system>
Created: <n> tickets

<letter> → <KEY>   <title>            [suffixed: <original key was taken>]
…

Links:   <n> parent→child
Labels:  <KEY> → <label>   (created | already existed)
         …   or: none requested
```

Verdict is exactly one of:

- **`CREATE CLEAN: <n> tickets`** — all created, all linked, every requested mode label
  applied, no `%%` remaining.
- **`CREATE PARTIAL: <n> of <m>`** — name each failure and what exists already.
  **Never delete a created ticket to "clean up"** — a half-published tree is recoverable by
  hand, and deleting live tickets that other tickets already reference is not.
- **`CREATE BLOCKED: <reason>`** — an argument or the system was unusable; nothing created.

Report the letter → key map even on `PARTIAL`. It is the only record of what the draft's
tokens now mean, and without it the caller cannot finish the job by hand.
