# slopstop

A Claude Code plugin for shipping AI-written code against Linear / JIRA / GitHub Issues tickets *without the slop*. The name is the thesis: **stop slop from going in, instead of cleaning it up after.** It wraps the full ticket lifecycle — investigate, plan, work, PR, review, merge — around a pipeline that keeps AI-generated code scoped and test-anchored from the first commit. Optional parallel-agent fanout in git worktrees when the work decomposes.

---

## Stop the slop before it goes in

The core idea is **prevention, not recovery.** Most "AI code review" tooling is recovery — it hunts for slop after it's already in the diff. slopstop puts the weight earlier: the work is scoped and test-anchored *before* Claude writes the implementation, so there's less slop to catch in the first place.

The pipeline, front to back:

1. **TDD that tests the right thing.** `/slopstop:plan` writes failing tests first — for the operations and behavior the *ticket* requires, not for whatever the current implementation happens to do. That distinction is the whole game: tests reverse-engineered from existing code are the common, sad failure mode of AI-generated tests — they pin down the current behavior (bugs and all) and pass vacuously. Red tests for the *intended* behavior give the implementation a real target, and every work item in the plan is anchored to "this named test turns green."
2. **Definition of Done + Scope on the ticket.** `/slopstop:plan` drafts a plain-language Definition of Done and an explicit scope boundary up front. These keep Claude on *this* problem and out of adjacent areas. The tell that it's working: Claude stops and asks *"would you like me to spin out a new ticket for this out-of-scope task?"* — instead of quietly sprawling into a diff that touches six files it was never asked to. (It happens a lot.)
3. **Pre-commit simplify.** `/slopstop:pr` runs Claude Code's built-in `simplify` pass over the uncommitted changes *before* anything is committed — a first slop-hunt that catches over-engineering, dead code, and needless abstraction while it's still cheap to remove.
4. **PR review pass.** `/slopstop:pr` opens the PR and runs a code review — either polling CodeRabbit (the default) or invoking Claude's `/code-review` skill at a configured effort level. Either way it verifies each comment against the actual code and sorts it into 🔴 should-fix / 🟡 could-fix / ⚪ skip — a second, independent slop-hunt before merge. The Claude backend can also post findings as inline PR comments and optionally apply fixes automatically (`fix = true` in `[pr_review]`).

Steps 3 and 4 are two serious slop-hunts. But it's the prep in steps 1–2 that does the real work: scope and tests pinned down before the implementation exists is what *prevents* the slop, rather than catching it after the fact.

---

## The workflow

The slash commands are the loop, from picking up a ticket to shipping it — with the prevention steps above wired into `:plan` and `:pr`. Each ticket also gets its own plan, investigation notes, and session log on disk, so a fresh Claude Code session can resume exactly where you left off, and that record can sync back to the ticket on close.

The loop:

```
   /slopstop:start <KEY>
            │
            ▼
   /slopstop:plan [constraint]      ←─── optional but recommended
            │  ┌──────────────────────────────────────────┐
            │  │  Phase 0: red tests for desired behavior │
            │  │  Phase A: investigate                    │
            │  │  Phase B: write detailed plan            │
            │  │  Phase C-G: optional agent fanout in     │
            │  │             worktrees + auto-merge       │
            │  └──────────────────────────────────────────┘
            ▼
        ┌── (work happens) ──┐
        │                    │
   /slopstop:update     /slopstop:pause       (interrupted)
        │                                  │
        │                                  │      /slopstop:start <KEY>
        │                                  └────┬────────────────────────────┘
        ▼                                       ▼
   /slopstop:pr
            │  ┌─────────────────────────────────────────┐
            │  │  simplify → tests → commit → push → PR  │
            │  │  → review (CodeRabbit or Claude)        │
            │  └─────────────────────────────────────────┘
            ▼
        (review iteration)
            │
            ▼
   /slopstop:merge
            │  ┌──────────────────────────────────────────────┐
            │  │  merge PR (MCP preferred, gh fallback) →     │
            │  │  advance ticket one state (e.g. In Progress  │
            │  │  → In Review, not Done) → push baseRef to    │
            │  │  all remotes → delete branch → recommend     │
            │  │  whether to run :archive now                 │
            │  └──────────────────────────────────────────────┘
            ▼
        (code shipped — wait here if ticket landed in
         an intermediate state like "In Review")
            │
            ▼
   /slopstop:archive    ←─── once ticket is in a terminal Done-type state
            │  ┌──────────────────────────────────────────────┐
            │  │  push task_plan as ticket description + DoD  │
            │  │  comment + findings comment → mv tracking    │
            │  │  to ticket-archive/                          │
            │  └──────────────────────────────────────────────┘
            ▼
          done
```

A few properties of the workflow that matter:

- **Per-ticket context isolation.** Each ticket gets its own `task_plan.md`, `findings.md`, `progress.md` at `~/.claude/ticket-active/<TICKET>/`. When you're on `MAZ-26`, only `MAZ-26`'s notes load — not the dozen others you've touched recently.
- **Parallel project work.** Multiple active tickets across different projects are each isolated in their own `~/.claude/ticket-active/<TICKET>/` directory. Different Claude sessions in different repos never conflict.
- **Durable record back to the ticket.** When you run `/slopstop:archive` (after the ticket has reached a terminal state on the ticket system), the final task plan becomes the ticket's description, a timestamped DoD-confirmation comment walks each Definition-of-Done item with evidence, and the findings become a separate comment. The ticket itself becomes a record of what was actually done, not just a title and a merged PR diff. `/slopstop:merge` does NOT do this — it ships the code and tells you whether to run `:archive` now or wait for QA.

---

## Ticket systems

slopstop supports three ticket backends. Set `system` in `.project-conf.toml` (see Setup):

| System | `system =` | Required MCP |
|---|---|---|
| **Linear** | `"linear"` | `mcp__linear-server__*` (Anthropic marketplace: `linear@claude-plugins-official`) |
| **JIRA** | `"jira"` | `mcp__atlassian__*` (Anthropic marketplace: `atlassian@claude-plugins-official`) |
| **GitHub Issues** | `"github"` | `mcp__plugin_github_github__*` (preferred) or `gh` CLI |

For GitHub Issues, slopstop uses label-based workflow state (see [Workflow shape](#workflow-shape--jira--linear)). For Linear and JIRA, it uses the ticket system's native state machine.

---

## Workflow shape — JIRA / Linear

> **Plan this before you start a project.** slopstop's `:merge` skill advances tickets by exactly one state and is designed around two supported workflow shapes:

| Shape | States | When to use |
|---|---|---|
| **3-state** | `Todo → In Progress → Done` | Most GitHub Issues projects; simple JIRA/Linear boards |
| **4-state** | `Todo → In Progress → In Review → Done` | When you have a separate review or QA gate before closing |

**GitHub Issues:** the workflow shape is declared in `[status_labels]` in `.project-conf.toml` (see Setup). No ticket-system configuration needed beyond the labels.

**Linear / JIRA:** slopstop uses the board's existing states and advances by one step using a preference algorithm (same-bucket first, then forward-progress). This works cleanly when the board has 3 or 4 states. If your board has more states — e.g. `Backlog → Todo → In Dev → Dev Review → QA → Staging → Done` — you have three options:

1. **Simplify the board** for this project: configure 3 or 4 workflow states in JIRA/Linear (recommended). Other projects on the same board are unaffected.
2. **Accept multi-step merges:** run `/slopstop:merge` once per state advance and handle intervening work between invocations. Tickets still move correctly — just not in a single command.
3. **Extend the skill:** the advance-one logic lives in `skills/merge/SKILL.md`; fork or modify it to encode a custom state map.

---

## Tools you'll need

This plugin is a **wrapper around a ticket-system MCP and a GitHub backend** — it has no built-in API client of its own. Before installing, check what you have.

### Required

- **Claude Code** with the plugin manager available (`/plugin` command). On Claude Desktop, see the "manual install" path below.
- **A ticket-system MCP** — one of:
  - **Linear plugin** from Anthropic's marketplace:
    ```
    /plugin marketplace add claude-plugins-official
    /plugin install linear@claude-plugins-official
    ```
    The skills expect tools under `mcp__linear-server__*`.
  - **Atlassian (JIRA + Confluence) plugin** from the same marketplace:
    ```
    /plugin install atlassian@claude-plugins-official
    ```
    The skills expect tools under `mcp__atlassian__*`.
  - **GitHub Issues** — uses the GitHub MCP (see below). No separate ticket-system MCP needed.
- **A `.project-conf.toml` file in each project's working directory.** See [Setup](#setup--project-conftoml) below.

### Required for `/slopstop:pr` and `/slopstop:merge`

- **A GitHub backend** — one of (both can coexist; MCP is preferred):
  - **Anthropic's GitHub plugin** (recommended — preferred path for PR and issue operations):
    ```
    /plugin install github@claude-plugins-official
    ```
    Exposes `mcp__plugin_github_github__*` tools. The skills use this for issue read/write, PR list/view/merge.
  - **The `gh` CLI** ([github.com/cli/cli](https://github.com/cli/cli)). The skills look in `/usr/local/bin/gh`, `~/.local/bin/gh`, `/opt/homebrew/bin/gh`, then `$PATH`. `gh auth status` must succeed. **`gh` is required only when the GitHub MCP is absent** — except for CodeRabbit polling (Step 6 of `:pr`), where `gh api` is the preferred polling path even when the MCP is installed. See below.

> **`gh` CLI is now optional for most operations.** The GitHub MCP handles issue transitions, PR list/view/merge. The one remaining `gh`-preferred use is CodeRabbit feedback polling (`gh api repos/.../pulls/.../comments`) — the MCP doesn't expose a raw API proxy, so `:pr` Step 6 uses `gh api` when available and falls back to MCP comment reads when `gh` is absent (slightly less precise, still functional). Install `gh` if you want the full CodeRabbit experience.
>
> **Known limitation:** `mcp__plugin_github_github__create_pull_request` returns 403 on some repos due to the plugin's PAT scope. `:pr` falls back to `gh pr create` automatically on a 403. If you don't have `gh` installed, PR creation will fail — install it or handle the PR creation manually.

### Optional but recommended

- **Claude Code's bundled `simplify` skill.** `/slopstop:pr` invokes it on uncommitted changes before committing — runs a reuse/quality/efficiency pass. If you don't have it, `:pr` warns and asks before continuing.
- **A PR review backend** — one of two options, configured via `[pr_review]` in `.project-conf.toml` (see Setup):
  - **[CodeRabbit](https://www.coderabbit.ai/)** (default — no config needed). Free for open source. `/slopstop:pr` polls for CodeRabbit's review comments after opening the PR. CodeRabbit does not review `.md`-only diffs; pass `--no-poll` for documentation-only PRs.
  - **Claude `/code-review`** (`backend = "claude"`). Uses your own Claude account — no CodeRabbit subscription required. Runs at a configured effort level (`low` / `medium` / `high` / `max` / `ultra`), posts findings as inline PR comments (`--comment`), and optionally applies fixable findings automatically (`fix = true`). Good fallback when CodeRabbit credits are exhausted.
  - **Neither configured**: if `[pr_review]` is absent and CodeRabbit is not installed on the repo, the review step produces nothing. Pass `--no-poll` to skip waiting.
- **A test command** the skills can invoke automatically. `/slopstop:plan` Phase 0 and `/slopstop:pr`'s pre-commit gate both want one. They auto-detect from common project files (`Taskfile.yml`, `package.json`, `Makefile`, `Cargo.toml`, `go.mod`, `pyproject.toml`) and ask the user once if detection fails — the answer is cached in `task_plan.md`.

---

## Install

Two install paths depending on which Anthropic app you use.

### Claude Code (CLI) — recommended

```
/plugin marketplace add iansmith/slopstop
/plugin install slopstop@slopstop
```

After install, commands are namespaced: `/slopstop:start`, `/slopstop:plan`, etc.

(The repo, the marketplace it hosts, and the plugin inside it all share the name `slopstop` — hence the doubled-up install command.)

### Claude Desktop — manual install (band-aid until Claude Desktop supports plugins)

> Claude Desktop currently has no `/plugin` manager and no built-in mechanism for installing third-party plugins from a marketplace — only Claude Code (CLI) does. Claude Desktop *does* load standalone slash commands from `~/.claude/commands/`, so this installer is a stopgap that drops the eight commands there directly, bypassing the marketplace entirely. This is a band-aid, not a long-term solution — when Claude Desktop ships plugin install support, this section becomes obsolete and Claude Desktop users will use the marketplace install above.

```bash
curl -fsSL https://raw.githubusercontent.com/iansmith/slopstop/master/install-for-claude-desktop.sh | bash
```

After install, the commands appear as `/slopstop-start`, `/slopstop-plan`, etc. (un-namespaced).

To pin to a specific tagged version: `SLOPSTOP_REF=v2.0.0 bash <(curl -fsSL https://raw.githubusercontent.com/iansmith/slopstop/v2.0.0/install-for-claude-desktop.sh)`.

To uninstall: `rm ~/.claude/commands/slopstop-{start,plan,update,document,archive,pr,merge,doc-sync,create-gh}.md`.

---

## Setup — `.project-conf.toml`

Every project where you'll run these commands needs a `.project-conf.toml` file at the repo root. This single file replaces the old `.project-prefix` approach and covers all three ticket backends.

### Minimal — GitHub Issues (3-state workflow)

```toml
system = "github"
key    = "owner/repo"       # GitHub: owner/repo slug
prefix = "MYPREFIX"         # ticket prefix — MYPREFIX-NN

[status_labels]
in_progress = "status:in-progress"   # label applied when ticket starts
# in_review = "status:in-review"    # uncomment to enable 4-state workflow

# PR review backend (optional — omit to use CodeRabbit if installed, nothing otherwise)
# [pr_review]
# backend = "claude"   # "coderabbit" (default) | "claude"
# effort  = "high"     # low | medium | high | max | ultra  (claude only)
# fix     = false      # true: commit fixable findings after code-review completes  (claude only)
```

Create the required labels before your first ticket:

```bash
gh label create "status:in-progress" --color "0075ca" --description "Actively being worked on"
# Optional 4-state:
gh label create "status:in-review" --color "e4e669" --description "In review / QA"
```

### Linear

```toml
system = "linear"
key    = "MAZ"         # Linear team key
prefix = "MAZ"         # ticket prefix (usually same as key)
```

Linear's native workflow states are used. See [Workflow shape](#workflow-shape--jira--linear) if your board has more than 4 states.

### JIRA

```toml
system = "jira"
key    = "PLTF"        # JIRA project key
prefix = "PLTF"        # ticket prefix
```

### Optional: code-graph indexing

```toml
[code-graph]
languages   = ["go"]          # which SCIP indexers to run
module_root = "."
skip        = ["vendor/", "*.pb.go"]

[code-graph.tools]
# scip_go = "/home/you/go/bin/scip-go"   # per-project override
```

The plugin reads `.project-conf.toml` on every invocation. **It only operates on tickets whose key matches the cwd's `prefix`** — so a session in `~/mazzy/` (prefix `MAZ`) can never accidentally touch a `PLTF-*` ticket, even if another project has one active.

---

## The commands

### `/slopstop:create-gh` — create a GitHub issue and assign a matching ticket key *(GitHub only)*

```text
/slopstop:create-gh Add AGE graph schema endpoint
/slopstop:create-gh --title "Fix NPE on empty corpus" --labels "bug"
```

Creates a GitHub issue and assigns it the `$PREFIX-N` ticket key that equals the GitHub issue number — so `BILL-65` always means GitHub issue `#65`. This keeps the digit-stripping logic in all other skills working correctly without a mapping file.

**Why this exists:** GitHub assigns issue numbers sequentially. If you create issues outside the slopstop workflow (manually, via bots, etc.), the BILL sequence and the GitHub sequence drift apart. This skill closes that gap by creating the issue first and deriving the key from the returned number.

Steps:
1. Prompts for title (or takes it from args). Body and labels are optional.
2. Creates the GitHub issue → gets `#N` back.
3. Assigns `$PREFIX-N` as the key. Checks `~/.claude/ticket-active/`, `~/.claude/ticket-archive/`, and existing issue titles for collisions; falls back to an alphabetic suffix (`BILL-65a`, `BILL-65b`, …) in the rare case one occurs.
4. Rewrites the issue title to the canonical `"BILL-N: <title>"` form.
5. Prints the key and the `:start` invocation to use next.

**GitHub-only.** Stops immediately if `system` in `.project-conf.toml` is anything other than `"github"` — Linear and JIRA assign their own keys. Also stops if `.project-conf.toml` is absent from cwd.

Does not transition the ticket, create a branch, or touch git. Call `/slopstop:start $KEY` afterward to do that.

### `/slopstop:start <KEY>` — start or resume a ticket

```
/slopstop:start MAZ-26
```

Two modes, decided automatically:

- **Fresh-start** (no local tracking dir for this ticket): fetches the ticket from Linear/JIRA/GitHub Issues, transitions it to In Progress, **creates a feature branch named `<type>/<TICKET>`** (e.g. `fix/MAZ-26`, `feat/MAZ-26`) — `<type>` is a Conventional-Commits-style prefix chosen interactively, with a heuristic suggestion when one can be inferred from the ticket's labels or title; a `skip` option opts out of branch creation entirely. If cwd is already on a non-default branch, the skill warns and asks whether to base the new branch off the default branch (typical, clean stack off trunk) or off the current branch (stacking on a feature branch). Then seeds `task_plan.md`, `findings.md`, `progress.md` at `~/.claude/ticket-active/MAZ-26/`.
- **Resume** (tracking dir already exists): reads the tracking files, prints a summary of where you left off, appends a `## Session <ts>` header to `progress.md`. No ticket-system call, no git.

### `/slopstop:plan [constraint]` — investigate and plan

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

### `/slopstop:update` — mid-session checkpoint

```
/slopstop:update
```

Appends a `## Update <ts>` section to `progress.md` capturing: branch, HEAD, working-tree state, completed-since-last-snapshot, current state, next step. Pure local, no MCP calls. The ticket stays active.

Use this when you've made meaningful progress and want context to survive even if the Claude session unexpectedly ends.

### `/slopstop:pause` — interrupted

```
/slopstop:pause
```

Like `/slopstop:update`, but the section header is `## Pause` (richer template — captures last completed, next step, open questions, mental context). The ticket stays alive; it's just not the active one anymore. Resume by running `/slopstop:start <KEY>` again later.

### `/slopstop:pr` — open a pull request

```
/slopstop:pr
/slopstop:pr --base develop
/slopstop:pr --no-simplify --no-test
/slopstop:pr --no-poll      # skip review step (docs-only PRs, or when review isn't configured)
```

End-to-end PR creation:

1. **Simplify.** Invokes Claude Code's `simplify` skill on uncommitted changes. If simplify made changes, surfaces them for user confirmation before committing.
2. **Pre-commit tests.** Auto-detects or asks for the test command, runs it. On failure, refuses to commit by default (offers `fix` / `commit anyway` / `abort`).
3. **Commit.** Stages everything, generates a ticket-anchored commit message (`[$TICKET] <summary>` with body from `task_plan.md`'s Plan section), commits with the standard Co-Authored-By trailer. Never `--no-verify`.
4. **Find GitHub backend.** Detects GitHub MCP (`mcp__plugin_github_github__*` or `mcp__github__*`) or falls back to `gh` CLI. Also resolves `gh` for CodeRabbit polling regardless of backend.
5. **Push.** `git push -u origin $BRANCH` (or regular push if upstream exists). Never `--force`.
6. **Open PR.** Uses GitHub MCP if available, else `gh` CLI. PR creation via MCP may return 403 on some repos (PAT scope); auto-falls back to `gh pr create`. Body pulls Summary / Test plan from `task_plan.md`.
7. **Review.** Backend-dependent — reads `[pr_review]` from `.project-conf.toml`. Pass `--no-poll` to skip entirely.
   - **CodeRabbit** (default, `backend = "coderabbit"` or block absent): triggers CodeRabbit if needed, then polls every 60s for up to 20 minutes. CodeRabbit does not review `.md`-only diffs.
   - **Claude** (`backend = "claude"`): invokes `/code-review --effort <level> --comment [--fix]`. Findings posted as inline PR comments. If `fix = true`, fixable findings are also committed and pushed after code-review completes.
8. **Categorize.** (CodeRabbit path only.) Each inline comment is verified against the actual code (CodeRabbit hallucinates), then classified: 🔴 Should fix (bug/security/correctness), 🟡 Could fix (style/idiom/refactor with ROI), ⚪ Skip (premise wrong / contradicts convention / pure nit). Stops after presenting — never auto-applies. The Claude path uses code-review's own verdict structure.

### `/slopstop:document` — sync local docs to the ticket

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

### `/slopstop:doc-sync` — mirror design/ to the project's doc store

```
/slopstop:doc-sync
```

One-way push of all `design/*.md` files to the project's documentation store — GitHub wiki (for `system = "github"`) or Linear Docs (for `system = "linear"`). `design/` is the source of truth; the doc-store copy is overwritten on each sync. Orphan pages (previously synced, now deleted from `design/`) are pruned.

- Warns if `design/` has uncommitted changes (pushes working-tree state, not the committed version).
- For GitHub: requires the wiki to be initialized via the web UI before the first sync (`git push` to an uninitialized wiki fails).
- **Do not run in the same turn as edits to `design/`** — the sync reads source files while concurrent writes modify them, producing mid-edit snapshots. Finish all edits first, then sync.

### `/slopstop:merge` — ship the code

```
/slopstop:merge
/slopstop:merge --pr 123 --strategy squash
```

When the PR is review-approved and CI is green: merges the PR (GitHub MCP preferred, `gh` CLI fallback), **advances the ticket by one state in its workflow** (NOT auto-Done — same-bucket transitions like "In Progress" → "In Review" are preferred over jumping to Done so the team's review / QA gates aren't skipped), propagates the merged-onto branch to all configured remotes, and deletes the local feature branch. The proposed next state is shown in the confirmation prompt before anything irreversible happens.

**`:merge` does NOT archive.** It leaves `~/.claude/ticket-active/$TICKET/` in place. The summary at the end recommends whether to run `/slopstop:archive` now (✅ ticket landed in a terminal Done-type state) or to wait (⚠️ ticket landed in an intermediate state like "In Review" where QA still needs to verify).

> **`:merge` vs `:archive`** — properly separate steps:
> - `:merge` ships the **code**: PR merged (MCP preferred), ticket advanced one state, branch cleaned up. Local tracking left intact.
> - `:archive` ships the **record**: pushes the final plan as the ticket description, posts the DoD-confirmation + findings comments, moves the local tracking dir to `ticket-archive/`. Refuses unless the ticket is already in a terminal state.
>
> For most teams: run `:merge`, wait for QA / review / sign-off, then run `:archive`. For workflows where In Progress → Done has no intermediate state, run `:archive` immediately after `:merge`. The Step 7 recommendation tells you which case applies.

### `/slopstop:archive` — close the local lifecycle

```
/slopstop:archive
/slopstop:archive MAZ-26    # archive a paused ticket without resuming
```

After the ticket has reached a terminal state on the ticket system: delegates the documentation push to `:document` (idempotent — already-current artifacts are silently skipped), then `mv`s the local tracking dir to `~/.claude/ticket-archive/`.

Refuses to run if the ticket isn't already in a terminal state. **No `--force` in `:archive`.** If `:document`'s divergence check fires, `:archive` propagates the stop without touching local tracking. Resolve via standalone `/slopstop:document --force`, then re-run `/slopstop:archive`. The friction is intentional — archive is the irreversible end of the local lifecycle.

---

## A scenario — fixing a wrong-subscriber webhook bug

Walking through all the commands on a fictional ticket. Output is illustrative.

### The setup

You're a backend engineer on a webhooks team. A Linear ticket lands in your queue:

> **MAZ-99 — Webhooks deliver to wrong subscriber after subscription renewal**
>
> Reports from customers: when they renew a subscription, the next webhook(s) sometimes deliver to the *previous* subscriber's destination (the one whose subscription the renewal replaced). Started after the v2.4 release. Repro: create sub A pointed at endpoint E1, renew it (which canonically updates the endpoint to E2), send a webhook, observe it landing at E1 instead of E2.

Open Claude Code in `~/webhooks-service`. The repo root has:

```toml
# .project-conf.toml
system = "linear"
key    = "MAZ"
prefix = "MAZ"
```

### 1. Start the ticket

```
> /slopstop:start MAZ-99

Branch type for MAZ-99?
  Suggested: fix  (from label 'bug')
  Choices:   fix | feat | chore | docs | refactor | perf | test | ci | build | deploy | revert | <custom> | skip

> fix

Created branch 'fix/MAZ-99' off 'origin/master'.

Started MAZ-99 — tracking at ~/.claude/ticket-active/MAZ-99/. Linear → In Progress. On 'fix/MAZ-99' (created off 'origin/master').
```

`~/.claude/ticket-active/MAZ-99/task_plan.md` now exists with the ticket's original description as a snapshot.

### 2. Plan the work

```
> /slopstop:plan focus on the dispatcher + subscriber registry; tests are in tests/

Phase 0 — Red tests first (TDD)

  Test command auto-detected: `task test` (from Taskfile.yml). Cached in task_plan.md.

  Expected behaviors from MAZ-99:
    1. Webhook destination is resolved at delivery time, not queue time.
    2. After subscription renewal, queued webhooks deliver to the renewed endpoint.

  Wrote tests/webhook_renewal_test.go with two new tests:
    - test_webhook_destination_resolved_at_delivery_time
    - test_webhook_delivers_to_renewed_endpoint_after_subscription_renewal

  Running `task test`...
  RED state established. Committing.

  [a1b2c3d] Phase 0: red tests for renewed-endpoint delivery

Phase A — Investigation
  Delegating to Explore subagent (scoped to internal/webhook/* and tests/)...

  Findings in findings.md. Highlights:
    - Dispatcher caches *subscriber struct ref* at queue time (internal/webhook/dispatcher.go:142).
    - Subscriber struct is replaced (not mutated in place) on renewal (subscribers.go:88).
    - Result: queued webhooks hold a pointer to a stale struct.

Phase B — Plan drafted

  2 work items, both parallel-safe. Launching 2 agents? (yes / save-only / abort)
```

Reply `yes` → agents run in background worktrees, merge back when done.

### 3. Open the PR

```
> /slopstop:pr

Step 1 — Simplify pass
  No changes needed. Working tree unchanged.

Step 2 — Run relevant tests
  All 89 tests passed. Continuing to commit.

Step 3 — Commit
  [b9c8d7e] [MAZ-99] Resolve subscriber at delivery time + emit renewal events

Step 4 — Find GitHub backend
  Backend: MCP (mcp__plugin_github_github__)

Step 5 — Create PR
  PR created: https://github.com/example/webhooks-service/pull/247 (target: master)

Step 6 — Poll CodeRabbit
  CodeRabbit feedback received: 4 inline comments, 1 finalized review

Step 7 — Categorize

🔴 Should fix (1):

  📄 internal/webhook/dispatcher.go:158
     CodeRabbit: "resolveAtDelivery() returns nil if the subscriber was deleted between queue
                  and delivery; the caller dereferences it without a nil check..."
     Verdict:    Add nil-check; on nil, log + drop the webhook with reason "subscriber deleted".
     Why:        Verified — line 162 dereferences sub.Endpoint without a guard. Real failure mode.

🟡 Could fix (2):  [elided for space]

⚪ Skip (1):  [elided for space]

PR: https://github.com/example/webhooks-service/pull/247
```

Apply the 🔴 fix, re-run `/slopstop:pr` (skips simplify, runs tests, commits fixup, pushes, re-polls). CodeRabbit returns APPROVED.

### 4. Ship the code

```
> /slopstop:merge

About to merge MAZ-99 and ship the code:
  1. Merge PR #247 (fix/MAZ-99 → master), then delete the remote feature branch.
  2. Advance MAZ-99 on Linear: 'In Progress' → 'In Review'
     (one step forward, NOT auto-Done — your QA gate is preserved)
  3. Switch to master, pull, delete local fix/MAZ-99.

Proceed? (yes / no / merge-only)

> yes

Shipped MAZ-99.

PR:      #247 merged (merge, abc1234) into master
Ticket:  MAZ-99 advanced from 'In Progress' to 'In Review' on Linear
Branch:  local fix/MAZ-99 deleted; remote branch deleted at merge
Local:   ticket-active/MAZ-99/ untouched

Next step:
  ⚠️ Ticket is now in 'In Review' — NOT terminal. Wait until QA sign-off,
     then run /slopstop:archive.
```

QA verifies the fix and moves MAZ-99 to Done on Linear.

### 5. Archive — close the loop

```
> /slopstop:archive

About to archive MAZ-99 (currently in 'Done'):
  1. Push task plan as ticket description + DoD-confirmation comment + findings comment
  2. mv ~/.claude/ticket-active/MAZ-99/ → ~/.claude/ticket-archive/MAZ-99/

Proceed? (yes / no / skip-push)

> yes

Archived MAZ-99 (was 'Done' on Linear).

Description:   updated (new)
DoD comment:   posted (new)
Findings:      posted (new)
Local:         archived to ~/.claude/ticket-archive/MAZ-99/
```

The Linear ticket now has the completed plan as its description, a timestamped DoD-confirmation comment with evidence per item, and a Findings comment with investigation notes. Three weeks later when someone re-reads MAZ-99, they see real engineering context — not just a title and a merged PR diff.

---

## Tracking files — what's in them

Each ticket directory (`~/.claude/ticket-active/<TICKET>/`) contains three markdown files:

- **`task_plan.md`** — the durable plan. Starts seeded with the ticket's original description; `/slopstop:plan` fills in the **Plan** section. This is what gets pushed back to the ticket's description on archive.
- **`findings.md`** — investigation results: root causes, codebase facts, constraints, dead-ends ruled out. Pushed as a comment on archive (unless template-empty).
- **`progress.md`** — per-session diary with `## Session`, `## Update`, and `## Pause` entries. **Never** pushed to the ticket system — too noisy for the durable record. Lives locally; the commit history + the findings comment + the description tell the durable story.

---

## Design choices

- **`:archive` and `:merge` refuse to mark a ticket Done unless it's already terminal on the ticket system.** The user controls the transition; the command syncs. No "Claude marked my ticket Done without telling me" failure mode. (`:merge` itself advances the ticket one state as part of its flow — but only after explicit confirmation in the Step 3 prompt.)
- **The plugin never touches git destructively.** No `--force`, no `--no-verify`, no `--admin`. It commits and merges with confirmation; the user resolves anything that requires those flags manually.
- **Linear, JIRA, and GitHub Issues are all first-class.** Detection is automatic via `.project-conf.toml`. The GitHub MCP is preferred; `gh` CLI is the fallback.
- **MCP-preferred, CLI-fallback throughout.** Each GitHub operation tries the MCP first and falls back to `gh` CLI on failure or absence. Exception: `create_pull_request` may 403 on the Anthropic plugin's PAT scope — `:pr` auto-falls back to `gh pr create` on a 403 rather than stopping.
- **Tracking files live outside the repo** (`~/.claude/ticket-active/<TICKET>/`). They survive `cd` between repos and aren't tied to any branch.
- **Workflow shape is declared, not inferred.** For GitHub Issues, the 3-state vs 4-state workflow is explicit in `[status_labels]`. For Linear/JIRA, the advance-one-state algorithm works best with 3 or 4 states; see [Workflow shape](#workflow-shape--jira--linear) for the options if your board is larger.

---

## Storage layout

```
~/.claude/
  ticket-active/
    MAZ-26/
      task_plan.md
      findings.md
      progress.md
      .agents.json        ← only present during /slopstop:plan agent fanout
    PLTF-2180/
      ...
    BILL-60/
      ...
  ticket-archive/
    MAZ-23/
      ...

<repo root>/
  .project-conf.toml      ← system, key, prefix, [status_labels], [pr_review], [code-graph]
  .harvester.toml         ← API credentials (gitignored)
  .mcp.json               ← MCP server declarations (slopstop-rag + others)
```

---

## Compatibility & troubleshooting

The skills track tool names from Anthropic's marketplace MCPs as of release time. If your installed MCP is a different distribution (community fork, older version) with a different namespace, detection may report `"No ticket-system MCP found"` even though an MCP is installed. Open an issue with the actual namespace and we'll add the alias.

Currently expected tool namespaces:

- **Linear:** `mcp__linear-server__*` (specifically `get_issue`, `save_issue`, `save_comment`, `list_issue_statuses`).
- **Atlassian (JIRA):** `mcp__atlassian__*` (specifically `getJiraIssue`, `editJiraIssue`, `addCommentToJiraIssue`, `getAccessibleAtlassianResources`, `getTransitionsForJiraIssue`, `transitionJiraIssue`).
- **GitHub (primary):** `mcp__plugin_github_github__*` — the Anthropic-managed `github@claude-plugins-official` plugin. Tools used: `issue_read`, `issue_write`, `add_issue_comment`, `list_pull_requests`, `pull_request_read`, `merge_pull_request`, `create_pull_request`.
- **GitHub (canonical fallback):** `mcp__github__*` — open-source GitHub MCP server, if installed separately.
- **GitHub (CLI fallback):** `gh` CLI — used when no GitHub MCP is found, and as the preferred path for `gh api` CodeRabbit polling and `gh pr create` (due to MCP PAT scope limitations on PR creation).

---

## License

MIT — see [LICENSE](LICENSE).

## Privacy

This plugin collects nothing about you or your usage — no telemetry, no analytics, no remote endpoints owned by the author. See [PRIVACY.md](PRIVACY.md) for the full statement, including a transparency note about what other tools (the Claude API, the Linear / Atlassian MCPs, GitHub, CodeRabbit) your slash-command invocations naturally hit.

## Author

Ian Smith ([@iansmith](https://github.com/iansmith))
