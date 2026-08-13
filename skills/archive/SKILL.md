---
description: Push every file in a ticket's tracking directory to the ticket — task plan, findings, the run.jsonl timing log, adversary rounds — so the local record survives where the ticket lives. Bytes move from disk to the backend without passing through the worker. Reports what it pushed; moves nothing and deletes nothing.
---

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
`task_plan.md`, `findings.md`, `run.jsonl` and `run-derived.jsonl` are the usual set, but a
run may also have left `adversary-round-2.md` or similar, and a file you do not recognise is
exactly the one worth preserving.

**`run-derived.jsonl` is why the no-filter rule earns its keep.** It was added by BILL-494 and
required no change here — a known-list filter would have silently dropped it, and it is the
only record that survives an orchestrator dying mid-run.

Skip only: dotfiles, `*.bak`, `*.tmp`, and anything over **1 MB** (report it by name and
size as skipped — do not silently drop it).

**That 1 MB skip is not the limit that binds.** The one that binds is the backend's comment
ceiling, two orders of magnitude below it — see step 3.

## Step 3 — The bytes never pass through you

**You are not a transcription service. A tracking file's contents must never appear in
anything you type** — not in a tool argument, not in a heredoc, not in a `--body` string.
Every backend has a path where a program reads the file from disk; take it.

This is the rule the rest of the step implements, and it is worth stating plainly because the
violation looks like success. On AATK-86 the worker retyped five files as `save_comment`
arguments: 56,797 output tokens, 8m32s, and a 68,743-byte argument for `run.jsonl` alone.
Across the fleet the stage ran at ~11 KB of tracking directory per minute — a rate, which
means it grows without bound as runs get longer. Nothing in the record showed it, because a
faithful transcription and a slow one look identical afterwards.

The other half is correctness: a file you retype is a file you can silently alter. Linear's
own `create_attachment` tool warns about exactly this — *"Opaque base64 copied through
model-visible text is easy to corrupt."* Bytes that go from disk to the wire without a model
in between cannot be corrupted that way at all.

### Composing a comment body — on disk, always

Where a comment is the right carrier (see the backend table), build it as a file and hand the
**path** to the poster:

```bash
BODY="$(mktemp -t archive-body)"
{
  printf '## 📁 %s — %s local record\n\n' "$NAME" "$TICKET"
  printf '%s\n\n' "$BLURB"
  printf '```%s\n' "$LANG"          # by extension: jsonl, json, md, txt
  cat -- "$SRC"                     # <- the only place the contents move
  if [ -n "$(tail -c 1 -- "$SRC")" ]; then printf '\n'; fi
  printf '```\n'
} > "$BODY"
```

`cat` does the copying. You supply the header, the one-line blurb and the fence language, and
those are the only things you author.

**That `tail -c 1` guard is load-bearing and was found by the step-5 read-back, not by
review.** The obvious form of this recipe closes with `printf '\n```\n'`, which appends a
newline the file did not have — every tracking file already ends in one, so the archived copy
comes back exactly one byte longer than the original, every time. It survives every plausible
eyeball check: the comment renders identically and the diff is invisible in a fenced block.
`$(…)` strips trailing newlines, so the guard emits a newline only when the file genuinely
lacks one, which is the case the fence actually needs protecting from.

### The stable header, and re-runs

**Match on the `## 📁 <filename>` header before posting.** If a comment with that header
already exists on the ticket, **edit it** rather than posting a duplicate — running this twice
on an unchanged directory must be a clean no-op. If the backend cannot edit comments, post a
new one and say so in your report so the stale one can be removed by hand.

### Per backend

| system | carrier | how the bytes move |
|---|---|---|
| `github` | comment | `gh issue comment $NUMBER --body-file "$BODY"` — edit: `gh api -X PATCH repos/$OWNER/$REPO/issues/comments/$ID -F body=@"$BODY"` |
| `linear` | **attachment** + a pointer comment | `prepare_attachment_upload` → `curl -X PUT --data-binary @"$DIR/$NAME"` → `create_attachment_from_upload` |
| `jira` | **attachment** + a pointer comment | the install's attachment endpoint, fed the path; comment via `addCommentToJiraIssue` |

**Never `-f body=…` — always `-F body=@"$BODY"`.** `-f` takes a literal string, which puts you
back to typing the file. `-F` with `@` makes `gh` read it.

**Linear and JIRA get attachments because their comment APIs take the body as an argument**,
and an argument is something you have to type. The attachment path is `curl`-driven, so the
bytes go from disk to the wire untouched, and the 2 GB attachment ceiling retires the comment
ceiling entirely for those backends. Post a short pointer comment carrying the stable header
and the attachment's title, so a re-run can still match on the header and the ticket still
reads as a set of named records.

Linear's upload is a three-call sequence with a **60-second** signed URL, and the tool is
explicit that you must **finish one file before preparing the next** — batching the prepares
expires the early URLs. Send every header in `uploadRequest.headers` verbatim, casing
included, or the PUT returns 403.

### When the carrier is a comment and the file is too big

GitHub's ceiling is **65,536 characters**; Linear's is the same. This is the case that has
been one bad run away from firing: AATK-86's `run.jsonl` went up at 65,138 characters — 398
bytes of headroom, on a file that grows with every span, finding and ruling.

On an attachment backend there is nothing to do; the ceiling does not apply.

On GitHub, split **mechanically and on line boundaries** — never by hand, and never mid-line,
because a half-written JSON line reads as corrupt rather than as truncated:

```bash
split -l "$LINES_PER_PART" -- "$DIR/$NAME" "$TMP/part-"
```

Choose `$LINES_PER_PART` by measuring, not by guessing: `wc -c` the file, divide by the
ceiling with room for the header, and divide the line count by that. Each part gets the header
family and is composed and posted exactly as above:

```
## 📁 run.jsonl — BILL-501 local record (part 2 of 3)
```

**Then check each part's composed body against the ceiling before posting, because an even
line split is not an even byte split.** Measured on AATK-86's `run.jsonl` — 67,096 bytes over
103 lines, split at 52 lines per part — the two parts came out 23,269 and 43,733 bytes. A
`run.jsonl` mixes 200-byte spans with 4,000-byte adversary results, so the line-count estimate
can be off by nearly 2×. If any part is still over, re-split with a smaller
`$LINES_PER_PART`; do not post it and hope.

Parts reassemble by plain concatenation — `split -l` leaves each part's trailing newline
intact, so joining them back needs no separator added. State the part count in your report.

## Step 4 — `run.jsonl` cannot contain the record of its own push

You are reading `run.jsonl` while the orchestrator is still writing to it. The copy you
push is missing, by construction, at least the `finished` line for your own span and the
`run_closed` line after it.

**Say so under the header** — in the comment on a comment backend, in the pointer comment on
an attachment backend:

> Captured mid-run: this copy omits its own archive span and `run_closed`. The complete
> file is in the archive directory.

This is a self-reference limit, not a defect, and naming it is what keeps it from being
read as a truncated or broken log later. Do not attempt to predict the missing lines.

## Step 5 — Verify, then report

**Read back what you pushed and compare it to disk.** Your own account of a successful post is
not evidence that the bytes arrived, and the failure this catches is invisible by eye — see
the `tail -c 1` note in step 3, which is a defect this check found and a review did not.

| system | how to read back |
|---|---|
| `github` | `gh api repos/$OWNER/$REPO/issues/$NUMBER/comments --paginate`, extract each fenced body, concatenate the parts in order |
| `linear` | `get_attachment(id=…)` — the attachment id from `create_attachment_from_upload` |
| `jira` | the install's attachment fetch |

**Do not fetch a Linear asset URL with plain `curl`.** `uploads.linear.app` returns **HTTP
401** to an unauthenticated request, and the 194-byte error page will happily be compared
against your file and reported as a mismatch you then go looking for in the wrong place.
`get_attachment` is the authenticated path.

Compare with a program — `shasum -a 256` both sides, or `cmp`. Never by eye, and never by
length alone.

A mismatch is `ARCHIVE PARTIAL` with the file named — never `CLEAN` with a caveat.

```
ARCHIVE <verdict>
Ticket:  <TICKET> (<system>)
Pushed:  <n> records for <m> files  (<k> posted, <j> edited)

📄 <filename>   <bytes>   <comment|attachment>   <posted|edited|parts 1-3>   <sha ok>
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
