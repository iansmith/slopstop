# slopstop

**slopstop v4.0.0 is slopstop for autonomous agents: it drives coding work end to end, with no
human in the loop, without letting slop in on the way.**

The idea has not changed — stop slop before it goes in, instead of reviewing it out afterwards.
What changed is who is driving. `/slopstop:run` takes one or more tickets and carries each one
from "open" to "merged and archived" by itself: investigate, write failing tests for what the
*ticket* requires, prove each one fails for the right reason, run an adversary over them,
implement, run the mechanical gates, review in a clean context, open the PR, merge, close the
ticket, archive the notes. It interleaves the tickets you give it, and it is **autonomous by
default** — an unattended run that stalls waiting for someone is the failure mode the default
exists to avoid.

**Six user-facing commands.** The whole flow is `:design` → `:tickets` → `:run`, or just `:run`
on tickets you already have. Everything else — eleven single-purpose workers — is an internal
agent the orchestrators launch; you never invoke one.

A real run of the previous generation, annotated end to end: **[walkthrough/](walkthrough/)**.

The argument for why any of this is worth the ceremony, written as prose rather than reference:
**[Prevention, Not Recovery](https://iansmith.github.io/slopstop/what_is_slopstop.html)**, on the
project site at [iansmith.github.io/slopstop](https://iansmith.github.io/slopstop/).

---

## Stop the slop before it goes in

The core idea is **prevention, not recovery.** Most "AI code review" tooling is recovery — it hunts for slop after it's already in the diff. slopstop puts the weight earlier: the work is scoped and test-anchored *before* the implementation is written, so there's less slop to catch in the first place. That does not change because nobody is watching — if anything it matters more.

The pipeline, front to back — step 1 is `:tickets`, and steps 2–5 all happen inside one `/slopstop:run`:

1. **A ticket that says what "done" means.** `:tickets` cuts every leaf ticket to a five-section standard with an explicit Definition of Done and scope boundary, and an adversary has to approve the tree before a single ticket is created. That contract is what everything downstream is measured against — the DoD is scored before the ticket can be closed, and `unverifiable` is not a polite `met`.
2. **TDD that tests the right thing.** The `red-tests` worker writes failing tests first — for the operations and behavior the *ticket* requires, not for whatever the current implementation happens to do. That distinction is the whole game: tests reverse-engineered from existing code are the common, sad failure mode of AI-generated tests — they pin the current behavior (bugs and all) and pass vacuously. Then `mutation-check` proves each red test fails for the *right reason*, and an `adversary` pass hunts for the cases the tests missed. The result is committed frozen; the implementing worker may not touch it.
3. **Three mechanical gates on the finished diff.** `slop-check` (judgment: what would have to break for this to go red?), `vacuity-check` (proof: run the test against the branch point and watch it fail), and `complexity-check` (a cyclomatic-complexity bound). They run *after* implementation, deliberately — the adversary at step 2 cannot see tests written later.
4. **Clean-context review.** The `review` worker reads the branch diff in its own context, with no access to the session that wrote the code, looping until it applies nothing or hits five rounds. It catches over-engineering, dead code, and needless abstraction while it's still cheap to remove.
5. **Bot review, read once.** After the PR is open, existing review-bot comments are read once, verified against the actual code, and sorted into what survives and what was refuted. There is no poll — a review that lands after the merge is not a gate.

Steps 3–5 are the slop-hunts. But it's the prep in steps 1–2 that does the real work: scope and tests pinned down before the implementation exists is what *prevents* the slop, rather than catching it after the fact.

### Mechanical gates never soften

A **judgment** gate can be waved past by a human who has read it. A **mechanical** gate — the red-test tamper check, vacuity, slop findings — cannot, and has no permissive setting in either mode and at any change size. It stops that ticket, always.

This is not strictness for its own sake. Any knob whose permissive value is the only one a fleet can live with silently disables its gate for exactly the agents it exists to police. **A gate that waves through the cases it was built to catch is worse than no gate, because it reports clean.**

### Every step is recorded

Each orchestrator appends every stage transition to an append-only `run.jsonl` — one file that is simultaneously the state machine, the resume point, and the timing record. Human waits are bracketed as spans of their own, so machine-active time is separable from someone who went to bed. It is validated on resume and again at the end; if a span was never closed, the run reports the unclosed spans and **no timing numbers at all**, because a broken record must not be able to produce a plausible-looking summary.

Nothing reads that data to make decisions yet. It is the substrate for adaptive behavior — knowing what is actually expensive before deciding what a small change is allowed to skip.

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

Three commands, in order, when you're starting from an idea:

1. **`/slopstop:design <topic>`** — grills you to shared understanding, one question at a time,
   then writes a PRD and a feature charter into a run dir. It classifies every decision against
   your spec (`SPEC` / `DERIVED` / `UNDERDETERMINED`) and names what it could not settle instead
   of pretending it did. Stops at a gate; it never cuts tickets.
2. **`/slopstop:tickets <run-id>`** — reads only those artifacts (not the design transcript) and
   cuts an umbrella/leaf ticket tree, each leaf to the five-section standard. An adversary reviews
   the draft — up to three rounds — and nothing reaches your ticket system until it passes.
3. **`/slopstop:run <TICKET> [TICKET...]`** — drives each ticket through the full lifecycle,
   interleaved. One ticket ⇄ one branch ⇄ one PR, merged serially.

Already have tickets? Skip to step 3. `:run` is the only lifecycle command there is.

**A failing gate stops that ticket, not the run.** Its branch and tracking directory are left
exactly as they are, every other ticket keeps going, and all the stopped tickets are reported
together at the end with what each one needs from a human.

**A ticket that fails implementation twice may be a ticket defect rather than a code defect.**
`:run` says so instead of grinding, and points at `/slopstop:tickets --rewrite <TICKET>` — which
captures the outgoing body verbatim and runs a mandatory scope-subtraction check, so the ticket
cannot be quietly shrunk until the existing code satisfies it.

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

> **Plan this before you start a project.** After a merge, `:run` takes the ticket to its terminal state (or advances exactly one state, if you set `[workflow] post_merge_done = false`). It is designed around two supported workflow shapes:

| Shape | States | When to use |
|---|---|---|
| **3-state** | `Todo → In Progress → Done` | Most GitHub Issues projects; simple JIRA/Linear boards |
| **4-state** | `Todo → In Progress → In Review → Done` | When you have a separate review or QA gate before closing |

**GitHub Issues:** the workflow shape is declared in `[status_labels]` in `.project-conf.toml` (see Setup). No ticket-system configuration needed beyond the labels.

**Linear / JIRA:** slopstop uses the board's existing states and advances by one step using a preference algorithm (same-bucket first, then forward-progress). This works cleanly when the board has 3 or 4 states. If your board has more states — e.g. `Backlog → Todo → In Dev → Dev Review → QA → Staging → Done` — you have three options:

1. **Simplify the board** for this project: configure 3 or 4 workflow states in JIRA/Linear (recommended). Other projects on the same board are unaffected.
2. **Park the ticket deliberately:** set `[workflow] post_merge_done = false` so `:run` advances exactly one state after the merge and stops. It reports parked tickets under their own heading, so a parked ticket never looks like a forgotten one. Someone moves it the rest of the way.
3. **Extend the skill:** the transition logic lives in `skills/run/SKILL.md` (stages 13–15); fork or modify it to encode a custom state map.

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

### Required for the PR and merge stages of `/slopstop:run`

- **A GitHub backend** — one of (both can coexist; MCP is preferred):
  - **Anthropic's GitHub plugin** (recommended — preferred path for PR and issue operations):
    ```
    /plugin install github@claude-plugins-official
    ```
    Exposes `mcp__plugin_github_github__*` tools. The skills use this for issue read/write, PR list/view/merge.
  - **The `gh` CLI** ([github.com/cli/cli](https://github.com/cli/cli)). `gh auth status` must succeed. **`gh` is required only when the GitHub MCP is absent** — except for reading a review bot's comments, where `gh api` is the more precise path even when the MCP is installed.

> **`gh` CLI is now optional for most operations.** The GitHub MCP handles issue transitions and PR list/view. Two things still prefer `gh`: reading bot comments (`gh api repos/.../pulls/.../comments`, since the MCP exposes no raw API proxy), and the merge itself — `:run` merges with `gh pr merge --merge --delete-branch`, and the MCP's merge tool does not delete the remote branch.
>
> **Known limitation:** `mcp__plugin_github_github__create_pull_request` returns 403 on some repos due to the plugin's PAT scope. `:run` falls back to `gh pr create` on a 403. If you don't have `gh` installed, PR creation will fail — install it or open the PR manually.

### Optional but recommended

- **A PR review bot on the repo**, if you want a second opinion on top of the `review` worker. `[pr_review] backend` in `.project-conf.toml` (`coderabbit` | `claude` | `greptile`) only selects *whose* comments `:run` looks for. It reads them **once**, after the PR is open, and never waits: a review that arrives after the merge was never a gate, and a run that blocks for twenty minutes hoping for one is a run that stalled. If there is nothing there, the `review` worker's verdict is what the merge rests on.
- **A test command** the workers can invoke. `red-tests`, `mutation-check` and `vacuity-check` all need one. It is auto-detected from common project files (`Taskfile.yml`, `package.json`, `Makefile`, `Cargo.toml`, `go.mod`, `pyproject.toml`); the resolved command is threaded to every worker that needs it, so it is established once per ticket.

---

## Install

Two install paths depending on which Anthropic app you use.

### Claude Code (CLI) — recommended

```
/plugin marketplace add iansmith/slopstop
/plugin install slopstop@slopstop
```

After install, commands are namespaced: `/slopstop:run`, `/slopstop:design`, etc.

(The repo, the marketplace it hosts, and the plugin inside it all share the name `slopstop` — hence the doubled-up install command.)

### Claude Desktop — manual install (band-aid until Claude Desktop supports plugins)

> Claude Desktop currently has no `/plugin` manager and no built-in mechanism for installing third-party plugins from a marketplace — only Claude Code (CLI) does. Claude Desktop *does* load standalone slash commands from `~/.claude/commands/`, so this installer is a stopgap that drops the commands there directly, bypassing the marketplace entirely. This is a band-aid, not a long-term solution — when Claude Desktop ships plugin install support, this section becomes obsolete and Claude Desktop users will use the marketplace install above.

```bash
curl -fsSL https://raw.githubusercontent.com/iansmith/slopstop/master/install-for-claude-desktop.sh | bash
```

After install, the commands appear as `/slopstop-run`, `/slopstop-design`, etc. (un-namespaced). The installer drops every skill, workers included, since an orchestrator has to be able to invoke them.

To pin to a specific tagged version: `SLOPSTOP_REF=v4.0.0 bash <(curl -fsSL https://raw.githubusercontent.com/iansmith/slopstop/v4.0.0/install-for-claude-desktop.sh)`.

To uninstall: `rm ~/.claude/commands/slopstop-*.md && rm -rf ~/.claude/commands/slopstop-*-refs/`.

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

# Whose bot comments to read once before merging (optional)
# [pr_review]
# backend = "claude"   # "coderabbit" (default) | "claude" | "greptile"

# After a merge, take the ticket to its terminal state (optional; default true)
# [workflow]
# post_merge_done = true
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

### Autonomy: one flag, no config

`/slopstop:run` is **autonomous by default**, because driving tickets unattended is what it exists for. There is exactly one switch and it lives on the command, not in config: `--interactive` stops at every judgment gate and asks instead.

> **`--interactive` is declared but not yet implemented.** The flag is part of `:run`'s contract; the interactive paths are not built. Today, `:run` runs autonomously.

There is no `[autonomous]` table. It held a master switch and seven per-gate `on_*` knobs, and it was deleted in the reorg: seven separate commands each needed a policy at their own gate, whereas one orchestrator has one decision point. The mechanical gates never had a permissive setting and still don't.

What remains is the complexity gate's bounds, in a table named for what it actually holds:

```toml
[complexity]
cc_warn_threshold        = 5      # 🟡 elevated
cc_reject_threshold      = 10     # 🔴 blocks the ticket
cc_exempt_pre_existing   = true   # exempt what the branch did not make worse
file_nloc_warn_threshold = 400    # 0 disables
```

`:run` is the sole reader of `.project-conf.toml` — it resolves these and passes them to `complexity-check` explicitly, and that worker blocks rather than falling back to a threshold of its own. Two readers of one config is two answers to one question. See [CONFIG.md](CONFIG.md) for the full key reference.

---

## The commands

Six, and that is the whole list:

| Command | What it does |
|---|---|
| `/slopstop:run <TICKET> [TICKET...]` | **The single lifecycle entry point.** Drives one or more tickets through the whole lifecycle, interleaved. Autonomous by default. `--constraint "<phrase>"` applies a hard scope to every ticket. |
| `/slopstop:design <topic>` | Stage 1 — grill to shared understanding, then write the PRD and feature charter into a run dir. Cuts no tickets. |
| `/slopstop:tickets <run-id>` | Stage 2 — cut an adversary-approved ticket tree from the PRD. `--retrofit <TICKET>` brings one existing ticket up to the five-section standard; `--rewrite <TICKET>` re-drafts one that failed implementation twice; `--refactor <fn>…` cuts a *nothing broke* ticket from `complexity-check`'s exempt list. |
| `/slopstop:grill [topic]` | The interview on its own — one question at a time until no branch of the decision tree is unresolved. `:design` vendors it; run it standalone to stress-test any plan. |
| `/slopstop:gh-init` | Bootstrap a GitHub repo: status labels, `.project-conf.toml`, gitignore entries. Idempotent. |
| `/slopstop:doc-sync` | Mirror `design/` to the project's doc store (GitHub wiki / Linear docs). |

**Eleven workers** — `investigate`, `red-tests`, `mutation-check`, `adversary`, `implement`, `review`, `slop-check`, `vacuity-check`, `complexity-check`, `create-ticket`, `archive` — are internals. The orchestrators launch them as agents, each on the model its stage resolves to, with checking work running one tier above the work it checks. You never invoke one directly, and a worker never launches another worker.

There is no `:start`, `:plan`, `:pr`, `:merge`, `:archive`, `:document`, `:update`, `:focus`, `:create-gh` or `:single-ticket`. Their work lives inside `:run` (or, for ticket creation and retrofit, inside `:tickets`); the hand-off machinery that existed only because each stage was a separate interactive session is gone.

---

## Worked examples

- **[QUICKSTART.md](QUICKSTART.md) — one ticket, one command, about 15 minutes.** Copy a small
  example repo and watch `:run` take a real bug from ticket to merged PR while you read the
  transcript.
- **[walkthrough/](walkthrough/) — one feature, nine tickets, a fleet of parallel agents.** The
  annotated run described [above](#see-it-actually-happen--the-annotated-walkthrough). It records
  a run of the previous generation, so the command names in it predate v4.0.0 — the adversarial
  machinery it shows is the machinery the workers now carry. Nothing to install.

---

## Tracking files — what's in them

Each ticket directory (`.slopstop/ticket-active/<TICKET>/`) contains three files:

- **`task_plan.md`** — the durable plan. Seeded from the ticket's own description and filled in as the run proceeds; the DoD confirmation (per-item verdict plus its evidence) is written here before the ticket is closed.
- **`findings.md`** — investigation results: root causes, codebase facts, constraints, dead-ends ruled out.
- **`run.jsonl`** — the append-only record described [above](#every-step-is-recorded): every stage transition, every human wait, the change-size note. The orchestrator is its sole writer; no worker touches it, and no worker even resolves the tracking directory.

At the end, the `archive` worker posts one comment per file to the ticket, so the local record survives where the ticket lives, and the directory moves to `.slopstop/ticket-archive/<TICKET>/` with its `run.jsonl` — an archived ticket carries its own timing.

There is no `progress.md` and no `gates.json`. The first was a checkpoint that existed because stages were separate sessions that could lose context, which `run.jsonl` now does mechanically. The second was gate-pass evidence written by the session under test, which was never evidence.

---

## Key Design Choices

- **The DoD is scored before a ticket can close, and `unverifiable` is not a polite `met`.** Any item that comes back `not-met` or `unverifiable` blocks and goes to a human. Closure happens through the ticket-system API, in `:run` — never by writing `Closes #N` in a PR body, which would let GitHub auto-close and silently skip the label half of the transition.
- **slopstop still enforces TDD in the projects it runs on.** `red-tests` and `mutation-check` are workers in every run: tests first, red for the right reason, committed frozen, and the implementing worker may not touch them. A stopped ticket is never resolved by weakening what stopped it — no deleted test, no narrowed assertion, no `Skip()`.
- **The plugin never touches git destructively.** No `--force`, no `--reset --hard`, no `--no-verify`, no `--admin`. Merges are real merge commits — never squash, never rebase — so a conflict is resolved by merging the base branch *into* the losing branch and re-running its tests, not by rebasing a pushed one.
- **Linear, JIRA, and GitHub Issues are all first-class.** Detection is automatic via `.project-conf.toml`. The GitHub MCP is preferred; `gh` CLI is the fallback.
- **Backend differences live in one worker.** `create-ticket` is the only thing that knows how each ticket system creates issues, which is what lets a new backend be added in one file instead of in every orchestrator.
- **Tracking files live project-local but gitignored** (`.slopstop/ticket-active/<TICKET>/`). They sit next to the code and travel with the clone, but stay out of every diff and aren't tied to any branch — and, unlike the legacy `~/.claude` location, they are writable by the agents `:run` launches. No config needed: a project-local `.slopstop/` directory (which `:gh-init` and `:design` create) is what puts them there. `tracking_dir`/`archive_dir` in `.project-conf.toml` are *overrides*; with no `.slopstop/` and no keys, tracking falls back to the legacy `~/.claude` default. See [CONFIG.md](CONFIG.md) for the full ladder.
- **Workflow shape is declared, not inferred.** For GitHub Issues, the 3-state vs 4-state workflow is explicit in `[status_labels]`. For Linear/JIRA, the advance-one-state algorithm works best with 3 or 4 states; see [Workflow shape](#workflow-shape--jira--linear) for the options if your board is larger.

---

## Storage layout

```
<repo root>/
  .project-conf.toml      ← system, key, prefix, [status_labels], [pr_review],
                            [workflow], [complexity], [tiers], [stage_tiers]
  .mcp.json               ← MCP server declarations (if any)
  design/                 ← durable, committed design docs
  .slopstop/              ← gitignored — slopstop's working state
    ticket-active/
      MAZ-26/
        task_plan.md
        findings.md
        run.jsonl         ← append-only state + timing record for this ticket
      PLTF-2180/
        ...
    ticket-archive/
      MAZ-23/
        ...
  scratch/                ← gitignored — transient :design/:tickets artifacts
    runs/
      twilio-20260709-1802/
        run.jsonl         ← the same schema, one per design/tickets run
        prd.md
        charter.md
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
- **GitHub (CLI fallback):** `gh` CLI — used when no GitHub MCP is found, and as the preferred path for `gh api` bot-comment reads, `gh pr merge --merge --delete-branch`, and `gh pr create` (due to MCP PAT scope limitations on PR creation).

---

## License

MIT — see [LICENSE](LICENSE).

## Privacy

This plugin collects nothing about you or your usage — no telemetry, no analytics, no remote endpoints owned by the author. See [PRIVACY.md](PRIVACY.md) for the full statement, including a transparency note about what other tools (the Claude API, the Linear / Atlassian MCPs, GitHub, CodeRabbit) your slash-command invocations naturally hit.

## Author

Ian Smith ([@iansmith](https://github.com/iansmith))
