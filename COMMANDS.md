# slopstop commands

Seventeen slash commands. In Claude Code (CLI) they are namespaced `/slopstop:<name>`; the Claude
Desktop standalone install renames them `/slopstop-<name>`.

The first group is the **single-ticket loop** — the everyday path from picking up a ticket to
shipping it, laid out end to end in [WORKFLOW.md](WORKFLOW.md). The second is the **fleet
pipeline**, which decomposes a whole feature into a ticket tree and drives parallel agents against
it; [walkthrough/](walkthrough/) reads one real fleet run minute by minute. The third is
**utilities** you reach for occasionally.

| | |
|---|---|
| **Single-ticket loop** | [`:start`](#slopstopstart-key) · [`:plan`](#slopstopplan-constraint) · [`:update`](#slopstopupdate) · [`:pr`](#slopstoppr) · [`:merge`](#slopstopmerge) · [`:archive`](#slopstoparchive) |
| **Fleet pipeline** | [`:grill`](#slopstopgrill) · [`:design`](#slopstopdesign-topic) · [`:tickets`](#slopstoptickets-run-id) · [`:run`](#slopstoprun-run-id) · [`:single-ticket`](#slopstopsingle-ticket-key) |
| **Utilities** | [`:create-gh`](#slopstopcreate-gh) · [`:gh-init`](#slopstopgh-init) · [`:document`](#slopstopdocument) · [`:update-ticket`](#slopstopupdate-ticket) · [`:doc-sync`](#slopstopdoc-sync) · [`:focus`](#slopstopfocus-ticket) |

> **There is no `/slopstop:pause`.** It appears in older documentation and in draft design notes
> under `design/`, but no such skill ships. Use [`:update`](#slopstopupdate) to checkpoint before
> you walk away, and `:start <KEY>` to resume.

---

# Single-ticket loop

<a id="slopstopstart-key"></a>
## `/slopstop:start <KEY>` — start or resume a ticket


```
/slopstop:start MAZ-26
```

Two modes, decided automatically:

- **Fresh-start** (no local tracking dir for this ticket): fetches the ticket from Linear/JIRA/GitHub Issues, transitions it to In Progress, **creates a feature branch named `<type>/<TICKET>`** (e.g. `fix/MAZ-26`, `feat/MAZ-26`) — `<type>` is a Conventional-Commits-style prefix chosen interactively, with a heuristic suggestion when one can be inferred from the ticket's labels or title; a `skip` option opts out of branch creation entirely. If cwd is already on a non-default branch, the skill warns and asks whether to base the new branch off the default branch (typical, clean stack off trunk) or off the current branch (stacking on a feature branch). Then seeds `task_plan.md`, `findings.md`, `progress.md` at `.slopstop/ticket-active/MAZ-26/`.
- **Resume** (tracking dir already exists): reads the tracking files, prints a summary of where you left off, appends a `## Session <ts>` header to `progress.md`. No ticket-system call, no git.

<a id="slopstopplan-constraint"></a>
## `/slopstop:plan [constraint]` — investigate and plan


```
/slopstop:plan
/slopstop:plan focus on the database layer only
```

Replaces `task_plan.md`'s empty `## Plan` section with a thorough plan grounded in real codebase investigation. The optional textual constraint scopes both investigation and the plan **literally** — out-of-scope work is excluded even if the ticket implies it.

Internally:

1. **Phase 0 — Red tests first.** Identifies the project's test command (auto-detect or ask once, cache in `task_plan.md`). Writes failing tests for the **expected** behavior the ticket describes — not for the current implementation. Runs them; expects them to fail. If they pass instead, surfaces it (the bug may already be fixed, or the tests aren't exercising the right behavior). Commits the red tests as a separate `[$TICKET] Phase 0: red tests` commit.
2. **Phase A — Investigation.** Uses the `Explore` subagent (when available) to map relevant modules, entry points, dependencies, constraints, and risks. Writes structured findings to `findings.md`.
3. **Phase B — Plan drafting.** Each work item gets `Files`, `Depends on`, `Parallel-safe with`, detailed sub-steps, and a `Done when` criterion (preferably "test X turns green" from Phase 0). Includes an explicit parallelism analysis.
4. **Phase C — Decision.** If fewer than 2 items are parallel-safe → print "serial execution" and stop. Otherwise continue.
5. **Phase D-G (parallel path only).** Pre-conditions (clean tree, base SHA, agent count cap), per-agent prompts, confirm-and-launch, monitor every 15 minutes with auto-stop on hard-stuck agents (60+ min no commits AND repeating errors), auto-merge with confirmation in dependency order.

The plan is always saved to disk before agents launch, so an abort at any stage leaves you with a usable plan.

<a id="slopstopupdate"></a>
## `/slopstop:update` — mid-session checkpoint


```
/slopstop:update
```

Appends a `## Update <ts>` section to `progress.md` capturing: branch, HEAD, working-tree state, completed-since-last-snapshot, current state, next step. Pure local, no MCP calls. The ticket stays active.

Use this when you've made meaningful progress and want context to survive even if the Claude session unexpectedly ends.

<a id="slopstoppr"></a>
## `/slopstop:pr` — open a pull request


```
/slopstop:pr
/slopstop:pr --base develop
/slopstop:pr --no-test
/slopstop:pr --no-poll      # skip review step (docs-only PRs, or when review isn't configured)
```

End-to-end PR creation:

1. **Review.** Runs a forked clean-context review of the branch, looping until it applies nothing or 5 rounds.
2. **Pre-commit tests.** Auto-detects or asks for the test command, runs it. On failure, refuses to commit by default (offers `fix` / `commit anyway` / `abort`).
3. **Commit.** Stages everything, generates a ticket-anchored commit message (`[$TICKET] <summary>` with body from `task_plan.md`'s Plan section), commits with the standard Co-Authored-By trailer. Never `--no-verify`.
4. **Find GitHub backend.** Detects GitHub MCP (`mcp__plugin_github_github__*` or `mcp__github__*`) or falls back to `gh` CLI. Also resolves `gh` for CodeRabbit polling regardless of backend.
5. **Push.** `git push -u origin $BRANCH` (or regular push if upstream exists). Never `--force`.
6. **Open PR.** Uses GitHub MCP if available, else `gh` CLI. PR creation via MCP may return 403 on some repos (PAT scope); auto-falls back to `gh pr create`. Body pulls Summary / Test plan from `task_plan.md`.
7. **Review.** Backend-dependent — reads `[pr_review]` from `.project-conf.toml`. Pass `--no-poll` to skip entirely.
   - **CodeRabbit** (default, `backend = "coderabbit"` or block absent): triggers CodeRabbit if needed, then polls every 60s for up to 20 minutes. CodeRabbit does not review `.md`-only diffs.
   - **Claude** (`backend = "claude"`): invokes `/code-review --effort <level> --comment [--fix]`. Findings posted as inline PR comments. If `fix = true`, fixable findings are also committed and pushed after code-review completes.
8. **Categorize.** (CodeRabbit path only.) Each inline comment is verified against the actual code (CodeRabbit hallucinates), then classified: 🔴 Should fix (bug/security/correctness), 🟡 Could fix (style/idiom/refactor with ROI), ⚪ Skip (premise wrong / contradicts convention / pure nit). Stops after presenting — never auto-applies. The Claude path uses code-review's own verdict structure.

<a id="slopstopmerge"></a>
## `/slopstop:merge` — ship the code


```
/slopstop:merge
/slopstop:merge --pr 123
```

Merges with a real merge commit by default. `--strategy squash` and `--strategy rebase` exist for the occasional branch whose history is genuinely noise, but they are per-PR exceptions: squashing collapses a branch's commits into one, so `git bisect` can no longer land inside the branch and reports a whole feature as the first bad commit.

When the PR is review-approved and CI is green: merges the PR (GitHub MCP preferred, `gh` CLI fallback), **advances the ticket by one state in its workflow** (NOT auto-Done — same-bucket transitions like "In Progress" → "In Review" are preferred over jumping to Done so the team's review / QA gates aren't skipped), propagates the merged-onto branch to all configured remotes, and deletes the local feature branch. The proposed next state is shown in the confirmation prompt before anything irreversible happens.

**If the post-merge state is terminal, `:merge` chains straight into `:archive` inline** — no separate command, no config flag, same in interactive and autonomous sessions. If the ticket instead landed in an intermediate state (e.g. "In Review" — QA still needs to verify), `.slopstop/ticket-active/$TICKET/` is left in place and the summary tells you to run `/slopstop:archive` manually once it reaches Done.

> **`:merge` vs `:archive`** — properly separate steps, chained automatically when they can be:
> - `:merge` ships the **code**: PR merged (MCP preferred), ticket advanced one state, branch cleaned up.
> - `:archive` ships the **record**: pushes the final plan as the ticket description, posts the DoD-confirmation + findings comments, moves the local tracking dir to `ticket-archive/`. Refuses unless the ticket is already in a terminal state.
>
> For most teams: `:merge` lands the ticket in an intermediate QA/review state, so `:archive` waits until you run it manually after sign-off. For workflows where In Progress → Done has no intermediate state, `:merge`'s own Step 10 already ran `:archive` for you — there's nothing left to do.

<a id="slopstoparchive"></a>
## `/slopstop:archive` — close the local lifecycle

```
/slopstop:archive
/slopstop:archive MAZ-26    # archive a ticket you are not currently on
```

**A local file move, and nothing else.** After the ticket has reached a terminal state on the
ticket system, `mv`s `.slopstop/ticket-active/<TICKET>/` to `.slopstop/ticket-archive/<TICKET>/`.
If the destination already exists it is renamed with a timestamp rather than overwritten.

Refuses to run if the ticket is not already in a terminal state, and **has no `--force`**. The
friction is intentional: archive is the irreversible end of the local lifecycle.

> **The documentation push is `:merge`'s job, not `:archive`'s.** `:merge` Step 7 pushes the task
> plan, DoD-confirmation comment, and findings to the ticket; Step 10 then chains `:archive`
> automatically when the post-merge state is terminal. Older documentation credited the push to
> `:archive` — that has not been true for some time. If you need to push documentation without
> merging or archiving, use [`:document`](#slopstopdocument).



---

# Fleet pipeline

These five turn a feature-sized idea into a ticket tree and drive agents against it. The first
three run at declared model tiers and **hard-stop if the session's model does not match** —
`:design` and `:tickets` on the huge/large tiers, `:run` on medium. See
[CONFIG.md](CONFIG.md) for `[tiers]` and `[stage_tiers]`.

<a id="slopstopgrill"></a>
## `/slopstop:grill` — interview a plan until it holds

```
/slopstop:grill
/slopstop:grill <a plan, or a rough idea>
```

Interviews you relentlessly about a plan or design, resolving each branch of the decision tree
until there is nothing ambiguous left. Every question comes with options, a recommendation, and
the trade-off behind it. Typically run before breaking work into tickets — and invoked
automatically as the first phase of `:design`. Usable standalone on any plan.

<a id="slopstopdesign-topic"></a>
## `/slopstop:design <topic>` — Stage 1: PRD and feature charter

```
/slopstop:design I want a CLI that stores key-value pairs in a local JSON file …
```

Grills you to shared understanding, then writes a PRD and a feature charter into a fresh run
directory under `scratch/runs/<run-id>/` and stops at gate **G-design** for your approval. Mints
the run-id that tags every artifact downstream. Cuts no tickets and writes no code. **Huge tier
only.**

<a id="slopstoptickets-run-id"></a>
## `/slopstop:tickets <run-id>` — Stage 2: the ticket tree

```
/slopstop:tickets kvstore-20260725-1001
```

Reads the PRD and charter from the run dir and cuts an umbrella/leaf ticket tree to the
five-section leaf standard — each leaf carrying 2–5 numbered observable behaviors, an explicit
file map, and test expectations, so an agent with no conversation history can implement it. Then
drives a **huge-tier adversary loop** over the tree (up to 3 correction rounds) whose job is to
prove the tickets wrong, and stops at gate **G-tickets**. Launches nothing. **Large tier only.**

<a id="slopstoprun-run-id"></a>
## `/slopstop:run <run-id>` — Stage 3: orchestrate the fleet

```
/slopstop:run kvstore-20260725-1001
```

Launches one hermetically-sealed worktree agent per leaf ticket, in dependency order, against a
G-tickets-approved tree. Holds autonomous kill authority over its agents; verifies each one's
handoff with a frozen-test tamper check plus two fresh subagents (a requirements adversary and a
code reviewer) that read the worktree rather than the agent's claims; integrates only blessed
work; and stops at gate **G-final** with a report that has itself been through an adversary pass.
Never implements ticket work itself. **Medium tier only.**

<a id="slopstopsingle-ticket-key"></a>
## `/slopstop:single-ticket <KEY>` — retrofit one ticket to the standard

```
/slopstop:single-ticket BILL-204
```

Takes an existing raw ticket and rewrites it to the same five-section standard `:tickets`
produces, so it can be handled by `:plan --ticket-driven` or dropped into a fleet run. Interviews
you toward the missing structure with `:grill`, drafts the five sections, runs the huge-tier
adversary loop over the result, then confirms and pushes — preserving the original content below
a separator. Interactive only.

---

# Utilities

<a id="slopstopcreate-gh"></a>
## `/slopstop:create-gh` — create a GitHub issue and assign a matching ticket key *(GitHub only)*


```text
/slopstop:create-gh Add AGE graph schema endpoint
/slopstop:create-gh --title "Fix NPE on empty corpus" --labels "bug"
```

Creates a GitHub issue and assigns it the `$PREFIX-N` ticket key that equals the GitHub issue number — so `BILL-65` always means GitHub issue `#65`. This keeps the digit-stripping logic in all other skills working correctly without a mapping file.

**Why this exists:** GitHub assigns issue numbers sequentially. If you create issues outside the slopstop workflow (manually, via bots, etc.), the BILL sequence and the GitHub sequence drift apart. This skill closes that gap by creating the issue first and deriving the key from the returned number.

Steps:
1. Prompts for title (or takes it from args). Body and labels are optional.
2. Creates the GitHub issue → gets `#N` back.
3. Assigns `$PREFIX-N` as the key. Checks `.slopstop/ticket-active/`, `.slopstop/ticket-archive/`, and existing issue titles for collisions; falls back to an alphabetic suffix (`BILL-65a`, `BILL-65b`, …) in the rare case one occurs.
4. Rewrites the issue title to the canonical `"BILL-N: <title>"` form.
5. Prints the key and the `:start` invocation to use next.

**GitHub-only.** Stops immediately if `system` in `.project-conf.toml` is anything other than `"github"` — Linear and JIRA assign their own keys. Also stops if `.project-conf.toml` is absent from cwd.

Does not transition the ticket, create a branch, or touch git. Call `/slopstop:start $KEY` afterward to do that.

<a id="slopstopgh-init"></a>
## `/slopstop:gh-init` — bootstrap a GitHub repo

```
/slopstop:gh-init
```

Creates the status labels the workflow needs and writes a `.project-conf.toml` for the repo.
Idempotent — safe to re-run. The fast path for step 1 of setting up a new project; see
[SETUP-GUIDE.md](SETUP-GUIDE.md) for the manual equivalent.

<a id="slopstopdocument"></a>
## `/slopstop:document` — sync local docs to the ticket


```
/slopstop:document
/slopstop:document --dry-run
/slopstop:document --force
/slopstop:document MAZ-26      # explicit ticket key
```

Push the current local documentation to the ticket on Linear/JIRA/GitHub Issues, idempotently:

- **Description body** ← `task_plan.md` (with the current ticket description preserved as `## Original description (preserved)` appendix).
- **DoD-confirmation comment** ← walks each `## Definition of Done` item from `task_plan.md` with evidence (Phase 0 red tests turning green, ticket-anchored commits, PR link, manual verification notes from `progress.md`). Skipped cleanly if no DoD section.
- **Findings comment** ← `findings.md` body. Skipped cleanly if template-empty.

Per-artifact safety: each artifact is classified as `new`, `unchanged`, `divergent`, or `skip` against the ticket's current managed state. `new` → push. `unchanged` → silently skip. `divergent` → **STOP** with a per-artifact diff, push nothing. `--force` overrides the divergence stop.

Pure remote-sync operation: does NOT change ticket state, does NOT touch local tracking. Use anytime — especially right after `:merge` advances the ticket to an intermediate state like "In Review", so reviewers have the full task plan context when they open the ticket.

<a id="slopstopupdate-ticket"></a>
## `/slopstop:update-ticket` — checkpoint locally, then push upstream

```
/slopstop:update-ticket
```

Runs [`:update`](#slopstopupdate) to checkpoint `progress.md`, then delegates to
[`:document`](#slopstopdocument) to push the current `task_plan.md` and `findings.md` to the
ticket — without archiving anything locally. Auto-detects the ticket system. Idempotent: running
it twice with no intervening changes is a no-op.

Use it mid-flight when a reviewer or a teammate needs the current plan visible on the ticket
before the work is finished.

<a id="slopstopdoc-sync"></a>
## `/slopstop:doc-sync` — mirror design/ to the project's doc store


```
/slopstop:doc-sync
```

One-way push of all `design/*.md` files to the project's documentation store — GitHub wiki (for `system = "github"`) or Linear Docs (for `system = "linear"`). `design/` is the source of truth; the doc-store copy is overwritten on each sync. Orphan pages (previously synced, now deleted from `design/`) are pruned.

- Warns if `design/` has uncommitted changes (pushes working-tree state, not the committed version).
- For GitHub: requires the wiki to be initialized via the web UI before the first sync (`git push` to an uninitialized wiki fails).
- **Do not run in the same turn as edits to `design/`** — the sync reads source files while concurrent writes modify them, producing mid-edit snapshots. Finish all edits first, then sync.

<a id="slopstopfocus-ticket"></a>
## `/slopstop:focus <TICKET>` — re-point attribution mid-session

```
/slopstop:focus BILL-201
/slopstop:focus --clear
```

Re-tags the current session's router attribution to a different ticket **without** creating a
branch or transitioning anything on the ticket system. For when one session's work legitimately
spans tickets and you want the spend recorded against the right one. `--clear` resets.

Requires `[fleet.router] enabled = true` in `.project-conf.toml`; without the router there is no
attribution to re-point.

---

## See also

- **[WORKFLOW.md](WORKFLOW.md)** — the single-ticket loop as one diagram, start to finish.
- **[walkthrough/](walkthrough/)** — a real fleet run, annotated minute by minute.
- **[CONFIG.md](CONFIG.md)** — every `.project-conf.toml` setting these commands read.
- **[SETUP-GUIDE.md](SETUP-GUIDE.md)** — installation, MCP servers, and project initialization.
