---
description: PR the active ticket branch — simplify → test → commit → push → create PR → review (CodeRabbit, Greptile, or Claude /code-review). Backend via [pr_review] in .project-conf.toml (default coderabbit). Loops on 🔴/🟡 findings (fix → simplify → commit → re-poll) until clean. ⚪ findings presented for human judgment. Posts a ticket comment linking back to the PR/review once it runs (any backend).
disable-model-invocation: true
---

# /slopstop:pr

## Project scope

Read `.project-conf.toml` from cwd; if absent, fall back to the main worktree at `dirname "$(git rev-parse --git-common-dir)"`. Set `$PREFIX` (`prefix` field), `$SYSTEM` (`system` field). Stop with a clear error if `prefix` is absent; stop if it doesn't match `^[A-Za-z][A-Za-z0-9]*$`. Only operate on `$PREFIX-\d+` branches.

Resolve `$TRACKING_DIR` and `$ARCHIVE_DIR` **together**, via the shared resolution ladder:
→ Read `~/.claude/commands/slopstop-start-refs/tracking-dir-resolution.md`

Missing from both: stop with `"No .project-conf.toml in cwd or main worktree. Run /slopstop:gh-init or create the file manually with system + key."`

## Autonomous mode

If `[autonomous] enabled = true`: prompts skipped per **Autonomous behavior** at the bottom; otherwise unchanged.

## Arguments

- `--base <branch>` — override the PR target (default: the repo's default branch).
- `--no-simplify` — skip Step 1's simplify pass.
- `--no-test` — skip Step 2's test run **and** Step 2e's slop gate. Does **not** skip Step 2d; no flag does.
- `--no-adversary` — skip Step 2e only. Does **not** skip Step 2d.
- `--no-poll` — skip the review step (Step 6) entirely.
- `--pr-tier <standard|large>` — forces the size classifier to **at least** the named tier; only **higher**, never lower (see `pr-size-classifier.md`).
- `--inline` — run simplify (Step 1), slop detection (Step 2e) and Claude code review (Step 6-claude) without spawning sub-agents; all reasoning executes in the current context. Use when `:pr` runs inside a delegated worktree agent, where sub-agent completion notifications route to the top-level loop instead of back to the spawning context. **`--inline` also forces the claude review backend** (see Pre-flight) — the bot backends are interactive-only. No effect on the CC gate or the pre-PR health gate.

The active ticket comes from `git branch --show-current`. If empty: `"No active $PREFIX ticket to PR."` and stop.

## Pre-flight (run in parallel)

- **Resolve the active ticket.** `$BRANCH = git branch --show-current`; first `$PREFIX-\d+` match (case-insensitive on `$PREFIX`, canonical-cased) → `$TICKET`. No match → stop: `"Branch '$BRANCH' does not encode a $PREFIX ticket ID. Check out a ticket branch first, or run :start / :exp to create one."`
- **In-flight check.** `$TRACKING_DIR/$TICKET/` must exist → else `"$TICKET is not in-flight. Run :start $TICKET first."`
- On the main/master branch → refuse: `"Refusing: on the main branch, not a feature branch."`
- `$DIRTY` = `git status --porcelain` (used by **Step 3 only** — Steps 1 and 2e scope to the branch diff, not the working tree; see BILL-337). `$DEFAULT_BRANCH` = `gh repo view --json defaultBranchRef --jq .defaultBranchRef.name`. `$BASE` = `--base` if given, else `base-branch` from config, else `$DEFAULT_BRANCH`.
- **`[pr_review]` config** (all optional): `$PR_BACKEND` = `backend` else `"coderabbit"` (valid: `"coderabbit"`, `"greptile"`, `"claude"`); `$PR_EFFORT` resolves via the effort fallback chain (BILL-333) — `effort` (specific key) → `[tiers.medium].effort` → `"inherit"`; `$PR_FIX` = `fix` else `false` (both Claude-only); `$PR_CR_FIX` = `coderabbit_fix` else `true`; `$PR_GR_FIX` = `greptile_fix` else `true` (set either to `false` for presentation-only behavior).
  - **Then, if `--inline` was passed, set `$PR_BACKEND = "claude"`.** The bot backends are interactive-only: their poll runs long enough that `--inline`'s only current caller — `:run`'s headless `claude -p` fleet agent — may not survive it, and a dead one-shot reports a timeout no review ever contradicts. When that overrode a different configured value, log it once, never silently: `[--inline] backend 'greptile' is interactive-only — using Claude review`. Resolving **here** rather than at Step 6 is deliberate: `$PR_BACKEND` then means one thing for the whole run, so Steps 5c, 6, 7f and 8 need no override branch and cannot disagree about which backend actually reviewed.
- **Redundant-config check** (autonomous only, informational — never changes control flow):
  → Read `~/.claude/commands/slopstop-pr-refs/pr-autonomous.md`
- **Remotes** (both default `"origin"`): `$PR_REMOTE` = `pr-remote` (feature branches push here); `$ORIGIN_REMOTE` = `origin-remote` (the PR opens against this remote's repo). **Repo:** `$OWNER`/`$REPO` = `pr-repo` if present, else parse from `key`.
- An open PR already exists for `$BRANCH` → refuse: `"PR already exists for $BRANCH: <url>. Use /slopstop:merge to ship it, or push more commits to update."` **Classify PR size (tier), before Step 0 runs:** `trivial`/`standard`/`large`, **printed with its signals before any gate is skipped (C14)**. Gates only Step 0b, Step 2e, Step 6; **Step 1, Step 2's targeted run, Step 2d, Step 2f, and Step 0c are never tier-gated** (C4, C13, universal §1's "No exceptions on size"). `--pr-tier` forces a higher tier only. → Read `~/.claude/commands/slopstop-pr-refs/pr-size-classifier.md`

## Step 0 — Pre-PR health gate

**Run the full suite before touching anything.** 0a resolve the test command → 0b run it and classify every failure as a **regression** (it passed at Phase 0 time) or an **expected failure** (this ticket's not-yet-green red test) → 0c the cyclomatic-complexity gate. Any regression hard-stops in autonomous mode; expected failures only warn. Command not determinable → skip this gate with a warning:
→ Read `~/.claude/commands/slopstop-pr-refs/pr-test-gates.md`

## Step 1 — Simplify pass on uncommitted changes

Skip if `--no-simplify`, or if the branch diff is empty. Snapshot the diff before and after and compare: identical → continue silently; different → show the delta and ask `continue / abort`. `--inline` runs the inline procedure instead of spawning the code-simplifier agent. **Scope is the branch, not the working tree.** A clean tree means nothing is *uncommitted*, not that nothing was *done* — and `:plan` Step 3a commits after every work item, so every autonomous and fleet run reaches `:pr` with nothing outstanding. Gating this step on that state disabled it for the entire fleet pipeline. Step 1 diffs from the merge-base of `$ORIGIN_REMOTE/$BASE` and HEAD, using a single ref so the diff spans committed and uncommitted work alike.
→ Read `~/.claude/commands/slopstop-pr-refs/pr-simplify.md`

## Step 2 — Run relevant tests before committing

Skip if `--no-test`. Same test-command resolution as Step 0a; pass → Step 2d, fail → offer `fix` / `commit anyway` / `abort`:
→ Read `~/.claude/commands/slopstop-pr-refs/pr-test-gates.md`

## Step 2d — Red-test tamper gate (mechanical)

**No flag skips this gate.** Not `--no-adversary`, not `--no-test`, not `[autonomous] on_slop_findings`. It skips on exactly one condition, and that condition is a **recorded fact, not an agent-supplied argument**:

> Skip Step 2d only if `task_plan.md` records **no Phase 0** — no `**Test command:**` line and no Phase 0 section, i.e. `:plan` never established a baseline. Otherwise it runs.

That distinction is the whole gate. The fleet agent composes its own `:pr` invocation, so any flag-keyed skip is a switch the *policed party* controls — an agent could disable its own tamper gate with `--no-test`, a flag that nominally just means "don't run the suite", while this gate runs no tests at all (it is `git log` plus `git diff`: no cost, no latency, no dependency on the suite). An agent cannot retroactively erase a baseline `:plan` already recorded. The same reasoning excludes `on_slop_findings`: that knob governs Step 2e's judgment review and is effectively pinned to `"skip"` in any fleet-capable config, so sharing it would mean this gate never runs for exactly the agents it exists to police.

**Do NOT skip on a clean working tree.** An empty `$DIRTY` means nothing is *uncommitted*, not that nothing was *done* — test tampering is committed work presenting a clean tree, so a clean tree is precisely when this gate must still run.

Diff **every file in the Phase 0 commit** across the range since that commit — the frozen set comes from `git show --name-only` against it, never a test-file glob, so inline tests inside source files are covered too. A changed expected value, a removed or skipped test, or **no Phase 0 commit at all** is 🔴 → **hard stop**. Interactive: require an explicit `override` with a reason, recorded to `pipeline.json`. Autonomous: `[autonomous] on_redtest_tamper`, default **`hard-stop`**, with deliberately no `skip` value. Clean → silent pass, proceed to Step 2e.

This runs in the agent's **own** session, so it is a self-check — which is why it is a mechanical diff rather than a judgement, and why `:run` re-checks it from outside in its own tamper check (`run-verification.md`). Baseline resolution, frozen-file derivation, hunk classification, and the known evasions:
→ Read `~/.claude/commands/slopstop-pr-refs/pr-slop-detection.md` (§ Step 2d)

## Step 2e — Slop-detection (judgment); Step 2f — Vacuity gate (mechanical)

Skip if `--no-adversary` or `--no-test` — **Step 2e only; Step 2f below skips on nothing.** Step 2e reviews the diff against `task_plan.md`'s Phase 0 red tests for AI-specific patterns that make tests pass without solving the problem. `--inline` runs it inline; otherwise spawn a slop-detection agent. 🔴 (test manipulation, expectation inversion, test deletion) → hard stop, explicit override, recorded to `pipeline.json`. 🟡 (implementation testing, tautological tests, scope creep, fake error handling) → surface and warn; proceeding needs no override. Autonomous consults `[autonomous] on_slop_findings`. **Step 2f is mechanical and no flag skips it — same claim, same reason, as Step 2d:** re-runs every test function changed since the merge-base against the **base** implementation (the branch point, not `$RED` — this covers tests Step 2d never froze), with `meta.stubs` copied in at their `meta.red_sha` content so a stub-backed test reaches its assertion instead of failing to collect. 🔴 on a changed test that passes cleanly at that base with no declared backfill; ⚪ inconclusive if it still can't be collected.
→ Read `~/.claude/commands/slopstop-pr-refs/pr-slop-detection.md` (§ Step 2e, § Step 2f)

## Step 3 — Commit (with a ticket-anchored message)

Skip if `$DIRTY` is empty after Step 1. `git add -A`, then: subject `[$TICKET] <imperative summary>` (≤72 chars), body of 1–3 short paragraphs explaining WHY (pull from `task_plan.md`'s Plan section), trailer `Refs: $TICKET`. Commit with `-m` flags or a HEREDOC — the body is multi-paragraph, so a single `-m` will not do. If pre-commit hooks fail: print their output verbatim and stop. Never `--no-verify`.

## Step 4 — Find the GitHub backend, then push

4a locate the code-hosting backend (MCP, else the `$GH` CLI) → 4b push: `-u` when there is no upstream, plain when ahead, skip when in sync. Push failure stops with the git output verbatim; never `--force`:
→ Read `~/.claude/commands/slopstop-pr-refs/pr-push-and-create.md`

## Step 5 — Create the PR

5a build title and body → 5b create it against the **canonical** repo (`--repo $OWNER/$REPO`, so a fork push-remote doesn't retarget the PR), capturing `$PR` and `$PR_URL` → 5c trigger the review bot, skipped for the claude backend and for `--no-poll`. **Skipping the trigger is not skipping the poll** — auto-review is not self-verifying:
→ Read `~/.claude/commands/slopstop-pr-refs/pr-push-and-create.md`

## Step 6 — Review pass (backend-dependent)

**Skip entirely if `--no-poll` was passed.** Continue to Step 8. Dispatch on `$PR_BACKEND` — already resolved in Pre-flight, where `--inline` forced it to `"claude"` because the bot backends are **interactive-only**. So this dispatch needs no `--inline` branch: a fleet agent simply arrives with `$PR_BACKEND == "claude"`.

- **`"coderabbit"`** → Step 6-cr (runs regardless of the 5c trigger), then Step 7.
- **`"greptile"`** → Step 6-greptile (runs regardless of the 5c trigger), then Step 7.
- **`"claude"`** → Step 6-claude, then Step 7f.

### Step 6-cr — poll for CodeRabbit feedback

**Runs unconditionally**, whether or not 5c posted a trigger. Poll for a `coderabbitai[bot]` walkthrough comment referencing `$HEAD_SHA` — the reliable completion signal for both first and incremental reviews:
→ Read `~/.claude/commands/slopstop-pr-refs/pr-cr-polling.md`

### Step 6-greptile — poll for Greptile feedback

**Runs unconditionally.** Poll for a submitted `greptile-dev[bot]` review referencing `$HEAD_SHA`:
→ Read `~/.claude/commands/slopstop-pr-refs/pr-greptile-polling.md`

### Step 6-claude — Claude code review

`--inline` runs the review inline. Otherwise build `--effort $PR_EFFORT --comment` (plus `--fix` when `$PR_FIX == true`) and invoke `Skill({skill: "code-review", args: ...})`:
→ Read `~/.claude/commands/slopstop-pr-refs/pr-claude-review.md`

## Step 7 — Verify, classify, and present bot review findings

Bot backends only; the Claude path skips to Step 7f. `$BOT_NAME` = `coderabbitai[bot]` or `greptile-dev[bot]`; `$BOT_FIX` = `$PR_CR_FIX` or `$PR_GR_FIX`. For each inline comment: **read the actual code at the cited line and verify the premise** before classifying 🔴 Should fix / 🟡 Could fix / ⚪ Skip. Then `$BOT_FIX == true` with 🔴/🟡 present → the fix-and-iterate loop; `false` → stop after presenting. ⚪ is always human judgment:
→ CodeRabbit: Read `~/.claude/commands/slopstop-pr-refs/pr-verification-classification.md` · Greptile: Read `~/.claude/commands/slopstop-pr-refs/pr-greptile-polling.md` (§ Step 7)

## Step 7f — Link the review back to the ticket

**Runs for all three backends** — every one of them posts onto the PR, so every one needs a pointer back from the ticket. Skip only if `--no-poll` (Step 6 never ran, so there is no review to link). The comment is a durable pointer and must **not** touch ticket status. Failure warns and continues; it never blocks PR completion:
→ Read `~/.claude/commands/slopstop-pr-refs/pr-ticket-linkback.md`

## Step 8 — Confirm

Print the summary: PR, commit, and every gate's outcome — **including which were skipped and why**:
→ Read `~/.claude/commands/slopstop-pr-refs/pr-confirm-summary.md`

## Stage end — resume state and Next:

Before finishing: write resume state to `progress.md` in `$TRACKING_DIR/$TICKET/` (resolved per `tracking-dir-resolution.md`, never re-derived here) and verify the write before printing the `Next:` line, in that order (C7) — Step 8's own summary (`pr-confirm-summary.md`) already sources from this tracking-dir state rather than conversation. This is **advisory, not a gate** (D2): nothing here blocks or prompts, and running `:pr` again in a session that already ran it — the ordinary fix-findings-and-re-poll loop — proceeds normally with no warning; the fleet's single headless process running `:plan` → `:pr` end to end continues to work with no required session boundary between stages (C6). On entry (Pre-flight), this stage rehydrates from `$TRACKING_DIR/$TICKET/` — `task_plan.md`, `progress.md`, `gates.json` — rather than from conversation state.
`Next: /slopstop:merge (fresh session)`.

## Rules

- Never `git push --force`, `git reset --hard`, `git commit --no-verify`, or `gh pr merge --admin`.
- Auto-apply 🔴 and 🟡 in Step 7's fix loop when the backend's `*_fix` is `true` (the default); set `coderabbit_fix`/`greptile_fix` to `false` for presentation-only. ⚪ is always presented for human judgment.
- All commits anchored to `$TICKET` via a `Refs: $TICKET` trailer.
- Review backend from `[pr_review].backend`, default `coderabbit`; `--inline` forces `claude` (bot backends are interactive-only). Simplify or the `code-review` skill unavailable → warn and ask; soft prerequisites, not hard stops.
- Bot timeout (20 min) → not a failure; continue to Step 8.
- Step 7f runs for every backend that actually reviewed (i.e. not `--no-poll`). A link-post failure warns and continues — it never blocks PR completion. Steps 0b, 0c, 2, 2d, 2e, 2f, 6 each write a `gates.json` entry unconditionally (`~/.claude/commands/slopstop-start-refs/gates-json.md`).

## Autonomous behavior

Applies only when `[autonomous] enabled = true` in `.project-conf.toml`. All autonomous prompt-skip decisions (simplify confirmation, test failure, red-findings fix loop, metrics emit):
→ Read `~/.claude/commands/slopstop-pr-refs/pr-autonomous.md`
