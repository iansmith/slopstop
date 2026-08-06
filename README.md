# slopstop

**Ticket-anchored AI development for Linear, JIRA, and GitHub Issues, built on one idea: stop slop
before it goes in, instead of reviewing it out afterwards.**

Work starts from a ticket, not a prompt. Claude writes failing tests for what the ticket
requires — not for what the code already does — then implements against a written scope boundary
and asks before wandering outside it. Nothing merges without a clean-context review of the branch
diff and an adversarial review that checks every finding against the real code, and each ticket
keeps a durable plan, findings, and progress log outside the repo so a fresh session resumes where
the last one stopped.

**Preventing slop does not mean working alone.** The same guarantees scale to a fleet:
[`:design`](COMMANDS.md#slopstopdesign-topic) interviews you into a PRD,
[`:tickets`](COMMANDS.md#slopstoptickets-run-id) cuts an adversary-approved ticket tree from it,
and [`:run`](COMMANDS.md#slopstoprun-run-id) drives parallel headless agents — one per ticket,
each isolated in its own git worktree — toward that tree, across four model tiers where every
tier's work is checked by the tier above it, with frozen-test tamper checks, independent handoff
verification before any branch is integrated, and a human gate at each stage boundary.

Seventeen commands in all: **[COMMANDS.md](COMMANDS.md)**. The single-ticket loop end to end:
**[WORKFLOW.md](WORKFLOW.md)**. A real fleet run, annotated: **[walkthrough/](walkthrough/)**.

The argument for why any of this is worth the ceremony, written as prose rather than reference:
**[Prevention, Not Recovery](https://iansmith.github.io/slopstop/what_is_slopstop.html)**, on the
project site at [iansmith.github.io/slopstop](https://iansmith.github.io/slopstop/).

---

## Stop the slop before it goes in

The core idea is **prevention, not recovery.** Most "AI code review" tooling is recovery — it hunts for slop after it's already in the diff. slopstop puts the weight earlier: the work is scoped and test-anchored *before* Claude writes the implementation, so there's less slop to catch in the first place.

The pipeline, front to back:

1. **TDD that tests the right thing.** `/slopstop:plan` writes failing tests first — for the operations and behavior the *ticket* requires, not for whatever the current implementation happens to do. That distinction is the whole game: tests reverse-engineered from existing code are the common, sad failure mode of AI-generated tests — they pin down the current behavior (bugs and all) and pass vacuously. Red tests for the *intended* behavior give the implementation a real target, and every work item in the plan is anchored to "this named test turns green."
2. **Definition of Done + Scope on the ticket.** `/slopstop:plan` drafts a plain-language Definition of Done and an explicit scope boundary up front. These keep Claude on *this* problem and out of adjacent areas. The tell that it's working: Claude stops and asks *"would you like me to spin out a new ticket for this out-of-scope task?"* — instead of quietly sprawling into a diff that touches six files it was never asked to. (It happens a lot.)
3. **Clean-context review.** `/slopstop:pr` runs a forked review of the branch — its own context, no access to the session that wrote the code — looping until it applies nothing or five rounds. It catches over-engineering, dead code, and needless abstraction while it's still cheap to remove.
4. **PR review pass.** `/slopstop:pr` opens the PR and runs a code review — either polling CodeRabbit (the default) or invoking Claude's `/code-review` skill at a configured effort level. Either way it verifies each comment against the actual code and sorts it into 🔴 should-fix / 🟡 could-fix / ⚪ skip — a second, independent slop-hunt before merge. The Claude backend can also post findings as inline PR comments and optionally apply fixes automatically (`fix = true` in `[pr_review]`).

Steps 3 and 4 are two serious slop-hunts. But it's the prep in steps 1–2 that does the real work: scope and tests pinned down before the implementation exists is what *prevents* the slop, rather than catching it after the fact.

---

## See it actually happen — [the annotated walkthrough](walkthrough/)

Claims about "adversarial verification" are cheap. **[`walkthrough/`](walkthrough/)** is a time-ordered reading of one real run — a five-sentence feature description turned into seven merged PRs by a fleet of deliberately underpowered agents — quoting the transcript at every point where the process caught something, and tracing each catch back to the decision that caused it.

What it shows, with timestamps and links to the actual public tickets:

- A design interview that catches a contradiction between [**two of its own answers, 70 seconds apart**](walkthrough/01-design-and-grill.md#grill-contradiction) — then an adversary that [rejects the resulting ticket tree because the lock it specified *would not have locked*](walkthrough/02-tickets-and-adversary.md#flock), and [proves it with a 40-trial experiment](walkthrough/02-tickets-and-adversary.md#experiment).
- An implementing agent that [**reported success and did nothing at all**](walkthrough/04-fleet-execution.md#no-op), exiting cleanly with a green tree — and what caught it.
- [A tamper investigation into an edited test helper](walkthrough/04-fleet-execution.md#tamper-check) that ends in an acquittal, adjudicated on evidence and in public.
- A final adversary that re-ran the whole suite, confirmed the code was correct, and then found that the orchestrator's own report [**had fabricated a violation against one of its own agents**](walkthrough/05-report-adversary.md#retraction) — followed by a public retraction on the ticket.
- A stage that [refuses to launch on a model *more* capable than the one it requires](walkthrough/03-handoff-and-gates.md#tier-gate), and says why.

Start at [`walkthrough/`](walkthrough/). It assumes you know coding agents and have never heard of slopstop.

---

## The workflow

The slash commands are a loop: pick up a ticket, plan it, work it, PR it, ship it, archive it.
Each ticket gets its own plan, investigation notes, and session log on disk, so a fresh session
resumes exactly where you left off, and that record syncs back to the ticket on close.

**The whole loop, as one diagram, with what each command actually does at each step:
[WORKFLOW.md](WORKFLOW.md).**

That page covers a *single ticket* — one person, one branch, one PR. The fleet pipeline
(`:design` → `:tickets` → `:run`) is a different shape and is described in
[walkthrough/](walkthrough/) and [`design/slopstop-process.md`](design/slopstop-process.md).

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

- **A forked review skill.** `/slopstop:pr` invokes `/slopstop:review`, which runs in its own subagent context with no access to the calling session — correctness, reuse, simplification, efficiency and altitude in one pass, applying what it verifies.
- **A PR review backend** — one of two options, configured via `[pr_review]` in `.project-conf.toml` (see Setup):
  - **[CodeRabbit](https://www.coderabbit.ai/)** (default — no config needed). Free for open source. `/slopstop:pr` polls for CodeRabbit's review comments after opening the PR. CodeRabbit does not review `.md`-only diffs; pass `--no-poll` for documentation-only PRs.
  - **Claude `/code-review`** (`backend = "claude"`). Uses your own Claude account — no CodeRabbit subscription required. Runs at a configured effort level (`low` / `medium` / `high` / `xhigh` / `max`), posts findings as inline PR comments (`--comment`), and optionally applies fixable findings automatically (`fix = true`). Good fallback when CodeRabbit credits are exhausted.
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

> Claude Desktop currently has no `/plugin` manager and no built-in mechanism for installing third-party plugins from a marketplace — only Claude Code (CLI) does. Claude Desktop *does* load standalone slash commands from `~/.claude/commands/`, so this installer is a stopgap that drops the commands there directly, bypassing the marketplace entirely. This is a band-aid, not a long-term solution — when Claude Desktop ships plugin install support, this section becomes obsolete and Claude Desktop users will use the marketplace install above.

```bash
curl -fsSL https://raw.githubusercontent.com/iansmith/slopstop/master/install-for-claude-desktop.sh | bash
```

After install, the commands appear as `/slopstop-start`, `/slopstop-plan`, etc. (un-namespaced).

To pin to a specific tagged version: `SLOPSTOP_REF=v2.0.0 bash <(curl -fsSL https://raw.githubusercontent.com/iansmith/slopstop/v2.0.0/install-for-claude-desktop.sh)`.

To uninstall: `rm ~/.claude/commands/slopstop-{start,plan,update,document,archive,pr,merge,doc-sync,create-gh,update-ticket,grill}.md && rm -rf ~/.claude/commands/slopstop-*-refs/`.

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
# effort  = "high"     # low | medium | high | xhigh | max  (claude only)
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

The plugin reads `.project-conf.toml` on every invocation. **It only operates on tickets whose key matches the cwd's `prefix`** — so a session in `~/mazzy/` (prefix `MAZ`) can never accidentally touch a `PLTF-*` ticket, even if another project has one active.

### Optional: autonomous mode

Add `[autonomous]` to run slopstop without interactive confirmation prompts — designed for benchmark harnesses (e.g. SlopCodeBench), overnight runs, and CI pipelines where no human is present.

```toml
[autonomous]
enabled = true

# :start — optional; unset uses the label/title heuristic automatically instead

# :plan — what to do when Phase 0 tests pass on current code (ticket may be stale) (default shown)
on_phase0_tests_pass = "continue" # continue (default) | ask | abort

# :plan — what to do when the plan recommends parallel agents (default shown)
on_parallel_agents = "proceed"    # proceed (default) | ask | serial | abort

# :pr — what to do when the simplify pass modifies the working tree (default shown)

# :pr — what to do when pre-commit tests fail (default shown)
on_test_failure = "abort"         # abort (default) | ask | commit-anyway | benchmark-continue

# :pr — what to do with 🔴 and 🟡 review findings (claude backend only) (default shown)

# :merge — default strategy (overridden by --strategy flag). Keep "merge": squash
# collapses a branch into one commit and destroys `git bisect` granularity.
merge_strategy = "merge"          # merge | squash | rebase

# :merge — ticket state after merge (overrides the computed "advance one" target)
merge_target_state = "auto"       # auto | done | skip
```

With `enabled = true`, each interactive prompt is resolved by the corresponding `on_*` key instead of asking you. The skill still logs what decision was made (so runs are auditable). Every key already defaults to a non-stalling value (`enabled = true` alone is a working config) — autonomous mode runs to completion unless it hits a serious or repeated problem, never stalling silently on an "ask" default. Set a key to `"ask"` explicitly only when a human is actually monitoring the run. See CONFIG.md for the full key reference, including `[workflow] skip_archive` for controlling how much `:merge` writes back to the ticket.

---

## The commands

Seventeen commands, grouped by what they are for — the single-ticket loop, the fleet pipeline, and
a handful of utilities — each with its arguments, what it does, and what it refuses to do:

**[COMMANDS.md](COMMANDS.md)**

---

## Worked examples

- **[QUICKSTART.md](QUICKSTART.md) — one ticket, by hand, about 15 minutes.** Copy a small example
  repo and take a real bug from ticket to merged PR yourself, so you see the single-ticket loop
  once with your own hands.
- **[walkthrough/](walkthrough/) — one feature, nine tickets, a fleet of parallel agents.** The
  annotated run described [above](#see-it-actually-happen--the-annotated-walkthrough). Nothing to
  install; read it to see what the adversarial machinery actually does.

---

## Tracking files — what's in them

Each ticket directory (`.slopstop/ticket-active/<TICKET>/`) contains three markdown files:

- **`task_plan.md`** — the durable plan. Starts seeded with the ticket's original description; `/slopstop:plan` fills in the **Plan** section. This is what gets pushed back to the ticket's description on archive.
- **`findings.md`** — investigation results: root causes, codebase facts, constraints, dead-ends ruled out. Pushed as a comment on archive (unless template-empty).
- **`progress.md`** — per-session diary with `## Session`, `## Update`, and `## Pause` entries. **Never** pushed to the ticket system — too noisy for the durable record. Lives locally; the commit history + the findings comment + the description tell the durable story.

---

## Key Design Choices

- **`:archive` and `:merge` refuse to mark a ticket Done unless it's already terminal on the ticket system.** The user controls the transition; the command syncs. No "Claude marked my ticket Done without telling me" failure mode. (`:merge` itself advances the ticket one state as part of its flow — but only after explicit confirmation in the Step 3 prompt.)
- **The plugin never touches git destructively.** No `--force`, no `--no-verify`, no `--admin`. It commits and merges with confirmation; the user resolves anything that requires those flags manually.
- **Linear, JIRA, and GitHub Issues are all first-class.** Detection is automatic via `.project-conf.toml`. The GitHub MCP is preferred; `gh` CLI is the fallback.
- **MCP-preferred, CLI-fallback throughout.** Each GitHub operation tries the MCP first and falls back to `gh` CLI on failure or absence. Exception: `create_pull_request` may 403 on the Anthropic plugin's PAT scope — `:pr` auto-falls back to `gh pr create` on a 403 rather than stopping.
- **Tracking files live project-local but gitignored** (`.slopstop/ticket-active/<TICKET>/`). They sit next to the code and travel with the clone, but stay out of every diff and aren't tied to any branch — and, unlike the legacy `~/.claude` location, they work when `/slopstop:run` launches headless fleet agents (which cannot write under `~/.claude`). No config needed: a project-local `.slopstop/` directory (which `:gh-init` and `:design` create) is what puts them there. `tracking_dir`/`archive_dir` in `.project-conf.toml` are *overrides*; with no `.slopstop/` and no keys, tracking falls back to the legacy `~/.claude` default. See [CONFIG.md](CONFIG.md) for the full ladder.
- **Workflow shape is declared, not inferred.** For GitHub Issues, the 3-state vs 4-state workflow is explicit in `[status_labels]`. For Linear/JIRA, the advance-one-state algorithm works best with 3 or 4 states; see [Workflow shape](#workflow-shape--jira--linear) for the options if your board is larger.

---

## Storage layout

```
<repo root>/
  .project-conf.toml      ← system, key, prefix, [status_labels], [pr_review], [autonomous]
  .mcp.json               ← MCP server declarations (if any)
  design/                 ← durable, committed design docs
  .slopstop/              ← gitignored — slopstop's working state
    ticket-active/
      MAZ-26/
        task_plan.md
        findings.md
        progress.md
        .agents.json      ← only present during /slopstop:plan agent fanout
      PLTF-2180/
        ...
    ticket-archive/
      MAZ-23/
        ...
  scratch/                ← gitignored — transient :design/:run artifacts (PRDs, run state)
```

`.slopstop/` and `scratch/` hold machine state, not source — both gitignored, so
they never enter a diff. `design/` is the committed, durable counterpart. (The
paths above are what a project-local `.slopstop/` resolves to on its own — no
config. `tracking_dir`/`archive_dir` override it; with neither the directory nor
the keys, tracking falls back to the legacy `~/.claude/ticket-active`.)

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
