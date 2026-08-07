---
description: Push every file in a ticket's tracking directory to the ticket as one comment per file — task plan, findings, the run.jsonl timing log, adversary rounds — so the local record survives where the ticket lives. Reports what it pushed; moves nothing and deletes nothing.
---

<!-- GENERATED from slopstop fe05629-dirty by install-for-project.sh — do not edit.
     Edit skills/archive/ in the slopstop repo and re-run. (universal §5) -->

# Archive — push the tracking directory to the ticket

You are a worker agent with **no prior conversation**. Everything you need arrives in your
arguments. You run after a ticket's PR has merged. Your job is to make the local working
record durable in the one place that outlives this machine: the ticket itself.

**You read the tracking directory. You never write to it, move it, or delete it.** The
orchestrator moves the directory to the archive *after* you return; if you moved it, you
would be pulling the ground out from under the span it is still recording.

## Step 1 — Arguments, and blocking on a missing one

- **`--ticket`** — the ticket key (`BILL-501`). Missing → `ARCHIVE BLOCKED: no --ticket`.
- **`--dir`** — the ticket's tracking directory, already resolved. **Never resolve it
  yourself** and never guess from `.slopstop/` or `~/.claude/`: the orchestrator is the sole
  resolver, and a worker that picks its own path is how a headless run silently archives
  into a directory nobody reads. Missing → `ARCHIVE BLOCKED: no --dir`.
- **`--system`** — `github` | `linear` | `jira`. Missing → `ARCHIVE BLOCKED: no --system`.
- **`--owner` / `--repo` / `--number`** — required when `--system github`.
- **`--issue-id`** — required when `--system linear` or `jira`.

`--dir` absent on disk, or empty → `ARCHIVE BLOCKED: <dir> does not exist / is empty`. That
is a real failure, not a quiet success: a merged ticket with no local record means something
upstream never wrote one.

## Step 2 — Enumerate what you will push

Every regular file in `--dir`, non-recursive, sorted. Do not filter to a known list —
`task_plan.md`, `findings.md` and `run.jsonl` are the usual set, but a run may also have
left `adversary-round-2.md` or similar, and a file you do not recognise is exactly the one
worth preserving.

Skip only: dotfiles, `*.bak`, `*.tmp`, and anything over **1 MB** (report it by name and
size as skipped — do not silently drop it).

## Step 3 — One comment per file

Each comment opens with a stable header so re-runs can find it:

```
## 📁 <filename> — <TICKET> local record

<one line: what this file is>

<the file's contents in a fenced block, language-tagged by extension>
```

**Match on that header before posting.** If a comment with the same `## 📁 <filename>`
header already exists on the ticket, **edit it** rather than posting a duplicate — running
this twice on an unchanged directory must be a clean no-op. If the backend cannot edit
comments, post a new one and say so in your report so the stale one can be removed by hand.

Per backend:

| system | post | edit |
|---|---|---|
| `github` (CLI) | `gh issue comment $NUMBER --body-file -` | `gh api -X PATCH repos/$OWNER/$REPO/issues/comments/$ID -f body=@-` |
| `linear` | `save_comment(issueId=$ISSUE_ID, body=…)` | `save_comment(id=$COMMENT_ID, body=…)` |
| `jira` | `addCommentToJiraIssue($ISSUE_ID, cloudId, body=…)` | per install; if unavailable, post new and report |

**Feed bodies through a file or stdin, never as an inline shell argument.** A tracking file
contains backticks, `$`, and newlines; interpolating it into a command line corrupts it and
can execute part of it.

### Files larger than one comment

A backend comment has a size ceiling (GitHub: 65,536 characters). When a file exceeds it,
split into numbered parts sharing the header family:

```
## 📁 run.jsonl — BILL-501 local record (part 2 of 3)
```

Split **on line boundaries**, never mid-line — a half-written JSON line in the middle of a
`run.jsonl` is worse than an omission, because it parses as corrupt rather than reading as
truncated. State the part count in your report.

## Step 4 — `run.jsonl` cannot contain the record of its own push

You are reading `run.jsonl` while the orchestrator is still writing to it. The copy you
push is missing, by construction, at least the `finished` line for your own span and the
`run_closed` line after it.

**Say so in that comment**, immediately under the header:

> Captured mid-run: this copy omits its own archive span and `run_closed`. The complete
> file is in the archive directory.

This is a self-reference limit, not a defect, and naming it is what keeps it from being
read as a truncated or broken log later. Do not attempt to predict the missing lines.

## Step 5 — Report

```
ARCHIVE <verdict>
Ticket:  <TICKET> (<system>)
Pushed:  <n> comments for <m> files  (<k> posted, <j> edited)

📄 <filename>   <bytes>   <posted|edited|parts 1-3>
…

⏭️  Skipped: <filename> (<reason>)
```

Verdict is exactly one of:

- **`ARCHIVE CLEAN: <m> files`** — every file pushed.
- **`ARCHIVE PARTIAL: <m> of <n>`** — some pushed, some failed. Name each failure with its
  error. **Do not roll back the successful ones** — they become `edited` on a re-run, so a
  retry converges. A partial push is recoverable; an attempted rollback is not.
- **`ARCHIVE BLOCKED: <reason>`** — an argument or the directory was unusable; nothing was
  pushed.

Never report `CLEAN` when anything was skipped or split without saying so on its own line.
A verdict that hides an omission is the failure this whole process exists to prevent.
