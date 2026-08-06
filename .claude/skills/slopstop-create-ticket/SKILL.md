---
description: Publish drafted tickets to whichever ticket system the project uses — create each issue, assign its key, link parents to children, and resolve cross-reference placeholders. The only place backend-specific creation lives; callers pass a draft and get back a letter-to-key map.
---

<!-- GENERATED from slopstop 19893b6-dirty by install-for-project.sh — do not edit.
     Edit skills/create-ticket/ in the slopstop repo and re-run. (universal §5) -->

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
```

Verdict is exactly one of:

- **`CREATE CLEAN: <n> tickets`** — all created, all linked, no `%%` remaining.
- **`CREATE PARTIAL: <n> of <m>`** — name each failure and what exists already.
  **Never delete a created ticket to "clean up"** — a half-published tree is recoverable by
  hand, and deleting live tickets that other tickets already reference is not.
- **`CREATE BLOCKED: <reason>`** — an argument or the system was unusable; nothing created.

Report the letter → key map even on `PARTIAL`. It is the only record of what the draft's
tokens now mean, and without it the caller cannot finish the job by hand.
