---
description: Merge PR + advance ticket one state + update tracking files + push docs to ticket + delete branch. Confirms once; shows computed next state. Chains :archive (file move) automatically when the ticket lands in a terminal state after merge. Tells you to run :archive manually for intermediate-state workflows.
disable-model-invocation: true
---

# /slopstop:merge

## Project scope

Read `.project-conf.toml` from cwd; if absent, fall back to the main worktree at `dirname "$(git rev-parse --git-common-dir)"`. Set `$PREFIX` (`prefix` field), `$SYSTEM` (`system` field). Stop with a clear error if `prefix` is absent; stop if it doesn't match `^[A-Za-z][A-Za-z0-9]*$`. Only operate on `$PREFIX-\d+` branches.

Resolve `$TRACKING_DIR` and `$ARCHIVE_DIR` **together**, via the shared resolution ladder:
→ Read `~/.claude/commands/slopstop-start-refs/tracking-dir-resolution.md`

Missing from both: stop with `"No .project-conf.toml in cwd or main worktree. Run /slopstop:gh-init or create the file manually with system + key."`

## Autonomous mode

Active when either is true: `[autonomous] enabled = true` in `.project-conf.toml` (the same trigger `:start`, `:pr` and `:plan` use), or `--autonomous` passed for this invocation only. Either way prompts are skipped per **Autonomous behavior** at the bottom; nothing else changes.

## Arguments

- **Positional `<TICKET>`** (e.g. `BILL-132`) — target a ticket from *outside* its branch, for the orchestrator pattern where `:merge` runs at the root against a finished worktree. Sets `$TARGET_GIVEN = true`; `$BRANCH` is then resolved from the PR's `headRefName` in Step 1b, and two pre-flight gates are skipped (see Pre-flight). Absent → `$TARGET_GIVEN = false` and behavior is unchanged.
- `--pr <N>` — disambiguate when the branch has more than one PR.
- `--strategy <squash|merge|rebase>` — default is `merge` (real merge commit; preserves per-commit traceability for `git bisect`). Use `squash`/`rebase` only when a specific PR genuinely benefits from collapsed history.
- `--autonomous` — force autonomous mode for this invocation even when config doesn't enable it.

With no positional arg the active ticket comes from `git branch --show-current`. If empty: `"No active $PREFIX ticket to merge."` and stop.

## Pre-flight

**Parse arguments first.** A positional arg matching `^$PREFIX-\d+$` → `$TICKET = arg`, `$TARGET_GIVEN = true`. Present but non-matching → refuse: `"$ARG doesn't match this project's prefix ($PREFIX)."`

Then, in parallel:

- **Resolve the active ticket.** `$TARGET_GIVEN = false` → parse `$TICKET` from `git branch --show-current` (first `$PREFIX-\d+` match, case-insensitive, canonical-cased); no match → stop: `"Branch '$BRANCH' does not encode a $PREFIX ticket ID. Check out a ticket branch first, or run :start / :exp to create one."` Set `$BRANCH` from the current branch. `$TARGET_GIVEN = true` → `$TICKET` is already set and `$BRANCH` waits for Step 1b.
- **In-flight check.** `$TRACKING_DIR/$TICKET/` must exist → else `"$TICKET is not in-flight. Run :start $TICKET first."`
- `$DIRTY` = `git status --porcelain`. Non-empty → refuse: `"Refusing: working tree has uncommitted changes. Commit or stash first."`
- `$ORIGIN_REMOTE` = `origin-remote` from config, else `"origin"`. Used by fetch, pull, and the multi-remote loop.
- **Two gates apply only when `$TARGET_GIVEN = false`:**
  - **Main-branch refusal** — `$BRANCH` is `main`/`master` → `"Refusing to merge: cwd is on the main branch, not a feature branch."` When a ticket was named explicitly, sitting on the primary branch is the *intended* posture, so this is skipped.
  - **`$AHEAD`** = `git rev-list --count @{upstream}..HEAD` (0 if no upstream). Non-zero → `"Refusing: branch has N commits not pushed to $ORIGIN_REMOTE. Push first."` Skipped when a ticket was named, because the agent's `:pr` step already pushed.
- **GitHub auth** is deferred to Step 1a — it is only checked on the CLI backend.

## Step 1 — Resolve the PR

1a detect the GitHub PR backend → 1b find the PR → 1c read its details → 1d decide adopt mode, then the pre-merge gates and soft warnings:
→ Read `~/.claude/commands/slopstop-merge-refs/merge-pr-resolution.md`

Three outcomes from that file drive everything downstream, so they are named here:

- **`$ADOPT = true` when the PR is already `MERGED`.** The recovery path for a PR merged outside `:merge` — Step 4 is **skipped**, `$MERGE_COMMIT` comes from 1c, and Steps 5–10 run normally.
- **A `CLOSED` PR is refused, a `MERGED` one is adopted.** Both are non-OPEN; collapsing them would either refuse a recoverable merge or advance a ticket whose work was abandoned.
- **The Definition of Done gate blocks the merge.** Any item scoring `not-met` or `unverifiable` refuses; it warns instead only under `[autonomous] on_dod_not_met = "warn"`, and a plain interactive run has no override. Skipped in adopt mode. How the DoD is located and scored:
  → Read `~/.claude/commands/slopstop-merge-refs/merge-dod-gate.md`

## Step 2 — Detect ticket system and compute the next state

Resolve the backend from config (`system` is authoritative — never inferred from MCP availability), fetch the current state, and compute the **advance-one** target: `$NEXT_TRANSITION` (JIRA), `$NEXT_STATE` (Linear), or `$NEXT_GH_ACTION` (GitHub). Already terminal → every `$NEXT_*` is `null`, the merge still proceeds, and Step 5 becomes a no-op:
→ Read `~/.claude/commands/slopstop-merge-refs/merge-ticket-system.md`

## Step 3 — Confirm with the user

**Adopt mode:** every plan line must state that **no merge will be performed** — the `PR:` line's strategy becomes `already merged <mergedAt> — adopting`. The operator must never come away believing `:merge` merged something it did not. Confirmation is otherwise unchanged.

**Definition of Done results are surfaced here**, one line per item with its verdict and evidence — except in adopt mode, where the gate never ran and there is nothing to report. Step 1 has already refused any non-`met` item, so these lines report what was checked; they are not something the operator can confirm past.

Three paths, in precedence order:

1. **`[workflow] skip_confirm = true`** and autonomous mode NOT already active → skip the prompt, emit the auto-confirm log, proceed as `yes`. Log block:
   → Read `~/.claude/commands/slopstop-merge-refs/merge-confirm-prompt.md`
2. **Autonomous mode active** → skip the prompt and proceed as `yes`; log format in `merge-autonomous.md` → Confirmation skip. The two log blocks have **different prefix lines** — do not substitute one for the other.
3. **Otherwise interactive** — show the plan and get explicit `yes` / `no` / `merge-only`:
   → Read `~/.claude/commands/slopstop-merge-refs/merge-confirm-prompt.md`

## Step 4 — Merge the PR

**Skipped entirely when `$ADOPT` is true** — the PR is already merged and `$MERGE_COMMIT` was captured in Step 1c. Re-merging is impossible and attempting it fails the run for no reason; go straight to Step 5.

Otherwise merge, then **read the PR back and assert `state == "MERGED"`** before capturing `$MERGE_COMMIT` — never trust the merge call's own return. On failure print the error verbatim and stop; no other state changes. Commands per backend, and the separate remote-branch delete the MCP path needs:
→ Read `~/.claude/commands/slopstop-merge-refs/merge-execute.md`

## Step 5 — Advance the ticket by one state

Skip if the `$NEXT_*` for this system is `null`. Otherwise apply it via the per-system MCP call or `gh` command:
→ Read `~/.claude/commands/slopstop-merge-refs/merge-execute-transition.md`

On transition error: print and continue. Not fatal — the PR is already merged.

## Step 6 — Update tracking files

Read `progress.md` in `$TRACKING_DIR/$TICKET/` and find the most recent `## Update` or `## Session` header.

- **Non-autonomous:** ask `"Tracking files last updated at <timestamp>. Update them now before pushing to ticket? (yes / skip)"`. `yes` → invoke `/slopstop:update` inline against `$TICKET` and wait; `skip` → proceed with current contents.
- **Autonomous:** always run `/slopstop:update` inline. No prompt, no staleness check.

## Step 7 — Push docs to ticket (:document)

Gated on `[workflow] skip_archive` (default `false`, `[workflow]`-scoped not `[autonomous]`, so it behaves identically in both modes). `false` → invoke `/slopstop:document`. `true` → skip it and post a single commit-id comment instead. **Both branches are best-effort** — record the outcome in `$DOC_RESULT` and continue; a doc-push failure never rolls back the merge:
→ Read `~/.claude/commands/slopstop-merge-refs/merge-doc-push.md`

## Step 8 — Local branch cleanup + propagate the merge to other remotes

Skip if `merge-only`. Full git sequences (8a switch+pull, 8b multi-remote push, 8c worktree/branch deletion):
→ Read `~/.claude/commands/slopstop-merge-refs/merge-cleanup.md`

## Step 9 — Confirm and recommend next step

Print the summary block, then exactly **one** of five `Next step:` blocks, chosen by classifying the **post-transition** state as terminal using data Step 2 already fetched — no new ticket-system call. Branches **A** (advanced into terminal) and **C** (already terminal) are the only ones that reach Step 10; **B** (intermediate), **D** (no forward transition) and **E** (merge-only) each tell the operator to run `:archive` themselves:
→ Read `~/.claude/commands/slopstop-merge-refs/merge-summary.md`

## Step 10 — Inline archive (terminal-state tickets only)

Runs **only** when the post-merge state is **terminal** — Step 9's branches A and C — and **never** when `skip_archive == true`. It moves the local tracking directory and, when the ticket has an umbrella, archives that umbrella's PRD/charter to it (`skills/document/references/document-archive-artifacts.md`); docs for `$TICKET` itself already went out in Step 7. Archive failure is non-fatal: surface it and continue, because the merge succeeded:
→ Read `~/.claude/commands/slopstop-merge-refs/merge-archive-chain.md`

## Stage end — resume state and Next:

Before finishing — after Step 9's summary and, when it ran, Step 10's archive chain — write resume state to `progress.md` in `$TRACKING_DIR/$TICKET/` (or, for a terminal-state ticket Step 10 already archived, the equivalent record now under `$ARCHIVE_DIR/$TICKET/`; resolved per `tracking-dir-resolution.md`, never re-derived here) and verify the write before printing the `Next:` line, in that order (C7). This is **advisory, not a gate** (D2): nothing above blocks or prompts, and running `:merge` again in a session that already ran it proceeds normally with no warning; the fleet's single headless process running `:plan` → `:pr` end to end continues to work with no required session boundary between stages (C6) — `:merge` runs from the orchestrator, not the fleet agent itself, but the same advisory posture applies here for consistency. On entry (Pre-flight), this stage rehydrates from `$TRACKING_DIR/$TICKET/` — `task_plan.md`, `progress.md`, `gates.json` — rather than from conversation state.
`Next: /slopstop:archive (fresh session)` for an intermediate-state ticket, or the next ticket to `:start` when this one reached a terminal state.

## Rules

- Confirms ONCE, in Step 3. All-or-nothing on the merge: if Step 4 fails, no other state changes.
- Advance ONE state, not auto-Done. Same-bucket transitions preferred. The target is shown in Step 3 and the user can say `no`.
- Chains `:archive` inline for terminal-state tickets (Step 10); intermediate-state workflows leave `$TRACKING_DIR/$TICKET/` untouched. Identical in interactive and autonomous mode — not gated by `[autonomous]`.
- `[workflow] skip_archive = true` (default `false`) disables Step 7's `:document` push and Step 10's archive chain entirely, replacing them with one commit-id comment.
- Steps 5 and 7 are best-effort — surface failures, never roll back the merge. Step 5 fails → continue to Step 6 (falls through to branch **D**). Step 8 fails → leave the local branch, continue to Step 9.
- **Closure happens here, not via a PR keyword.** Step 5 closes/advances the ticket through the API — for GitHub that is an explicit `state="closed"` plus the label swap, which has no `Closes #N` equivalent (and a 4-state workflow must reach In Review, not closed). So merging the PR **outside** `:merge` leaves the ticket open, the in-progress label applied, the tracking dir unarchived, and no docs pushed. **Recover by running `:merge <TICKET>` afterward** — Step 1d detects the merged PR and enters adopt mode, reaching the same end state. A PR closed *without* being merged still refuses, since advancing the ticket would misreport abandoned work.
- Branch deletion keys on the PR's `state: MERGED` — from Step 4 normally, or from Step 1c in adopt mode where Step 4 never runs. Squash and rebase merges work correctly.
- Never `git push --force`, `git reset --hard`, skip pre-commit hooks, or `gh pr merge --admin`.

## Autonomous behavior

Applies whenever autonomous mode is active. All autonomous decisions (strategy selection, confirmation skip, update tracking, target-state override, archive chain) and the `[workflow]` non-autonomous config:
→ Read `~/.claude/commands/slopstop-merge-refs/merge-autonomous.md`
