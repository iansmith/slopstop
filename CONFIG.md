# CONFIG.md — slopstop configuration reference

This file documents every configuration option across all slopstop config files. For installation walkthroughs, see `README.md`. For first-time setup, see `SETUP-GUIDE.md`.

---

## Configuration files at a glance

| File | Scope | Committed? | Purpose |
|---|---|---|---|
| `.project-conf.toml` | Per project | ✅ Yes | Ticket system, workflow shape, PR review, model tiers + fleet orchestration, autonomous mode |
| `~/.slopstop/github_token` | Per machine | ❌ No | GitHub personal access token (harvesters, cron) |
| `~/.slopstop/linear_token` | Per machine | ❌ No | Linear API key (harvesters, cron) |
| `~/.slopstop/jira_api_token` | Per machine | ❌ No | JIRA API token |
| `~/.slopstop/jira_email` | Per machine | ❌ No | JIRA account email |
| `~/.slopstop/jira_base_url` | Per machine | ❌ No | JIRA instance URL |
| `.harvester.toml` | Per project | ❌ No | Harvester credentials (gitignored) |
| `.mcp.json` | Per project | ✅ Yes | MCP server declarations |

---

## `.project-conf.toml` — per-project settings

One file at the repo root. Committed to git — shared with anyone cloning the project.

### Top-level required keys

```toml
system = "github"          # "github" | "linear" | "jira"
key    = "owner/repo"      # GitHub: "owner/repo" slug
                           # Linear: team key (e.g. "MAZ")
                           # JIRA: project key (e.g. "PLTF")
prefix = "BILL"            # Ticket prefix — BILL-NN; usually same as key for Linear/JIRA
```

All three are required. Every slopstop skill reads these first and refuses with a clear error if any is missing.

**`system`** determines which ticket backend is used (GitHub Issues label-based workflow, Linear native state machine, or JIRA transitions). Authoritative for all skills — never inferred from MCP availability.

**`key`** is how each skill constructs API calls. For GitHub, the `owner/repo` form is split on `/` to get `$OWNER` and `$REPO`. For Linear/JIRA, it is the team/project key used directly in API calls.

## Three sets — where a value actually comes from

Configuration resolves in three layers, each overriding the last:

| set | source | tracked? | role |
|---|---|---|---|
| 1 | the defaults documented in this file | — | the floor |
| 2 | `.project-conf.toml` | **yes** | the project's settings, shared by everyone |
| 3 | `.project-conf-local.toml` | **no — gitignored** | one developer's overrides |

**Overrides apply per leaf key, not per table.** A local file containing only

```toml
[tiers.small]
model = "qwen"
```

changes `tiers.small.model` and leaves `provider` and `version` in place, and does not
touch `[tiers.huge]`. It does **not** replace the table.

The point is that `.project-conf.toml` can be committed and reviewed while the few values
that are genuinely per-developer are not. The motivating case is working from a fork —
a local file holding one line, `key = "joe_blow/my-fork-of-repo"`, changes the repo and
nothing else.

A local file **overrides; it does not extend.** A key that is not in the documented schema
is an error, not a new setting — otherwise a typo becomes a value nobody reads and nobody
complains about.

`.project-conf-local.toml` must sit **beside** the tracked file, in the same directory.
`tools/fleet-sync/` reads set 2 only: auditing a local file would report a personal choice
as fleet drift, and syncing it would push one developer's fork URL to everyone.

---

**`prefix`** is the ticket-number prefix (e.g. `BILL` → tickets `BILL-1`, `BILL-2`, …). Skills only operate on tickets matching `^prefix-\d+$` — a session in a `BILL` project will never accidentally touch a `MAZ-*` ticket. For GitHub Issues, `prefix` and the GitHub issue number must agree: `BILL-65` always means GitHub issue `#65`. The `create-ticket` worker preserves this alignment whenever `:tickets` publishes a tree.

---

### Top-level optional keys — remotes

```toml
pr-remote     = "origin"   # remote to push feature branches to when opening a PR
origin-remote = "origin"   # canonical remote: PR target + :merge source of truth
```

Both keys are optional and default to `"origin"` when absent, so existing configs work unchanged.

| Key | Default | Description |
|---|---|---|
| `pr-remote` | `"origin"` | Remote that `:pr` and `:start` push feature branches to. Set to your personal fork name (e.g. `"mine"`) when working on a project where you push to a fork and open PRs against the upstream. |
| `origin-remote` | `"origin"` | The canonical/blessed remote. `:start` uses it as the base for new branches (`$ORIGIN_REMOTE/$DEFAULT_BRANCH`). `:merge` fetches and pulls from it, and the multi-remote propagation loop skips it (it already has the merge). `:pr` derives the PR target repo from it. |

**Typical fork workflow:**

```toml
pr-remote     = "mine"      # git remote pointing at your personal fork
origin-remote = "upstream"  # git remote pointing at the canonical upstream
```

With this config, `:pr` pushes to `mine` before opening the PR, and the PR is opened against the canonical repo. `:merge` cleans up by fetching from the configured `origin-remote` (`upstream` here) and propagating the merged base branch to any other remotes — including `mine`, keeping the fork in sync.

---

### Top-level optional keys — `pr-repo`, `base-branch`

```toml
pr-repo     = "owner/repo"   # GitHub owner/repo for API calls, if different from `key`
base-branch = "develop"      # PR target branch, if not the repo's default branch
```

| Key | Default | Description |
|---|---|---|
| `pr-repo` | `key` | `owner/repo` used for GitHub API calls (PR create/list, issue comment/label/close) when it differs from `key` — e.g. `key` names a personal fork you push to, but issues/PRs live in the upstream repo. Read by `:pr`, `:merge`, `:start`, `:document`. |
| `base-branch` | the repo's default branch | Overrides the PR target branch `:pr` opens against. Same effect as passing `--base` on every invocation. |

---

### Top-level optional keys — `tracking_dir`, `archive_dir`, and the `scratch/` layout

**Both keys are overrides, not settings you need.** Create a `.slopstop/` directory at the
main worktree root and both paths resolve to it — no config at all:

```toml
# Nothing needed. With .slopstop/ present:
#   tracking_dir -> .slopstop/ticket-active
#   archive_dir  -> .slopstop/ticket-archive
```

| Key | Default | Description |
|---|---|---|
| `tracking_dir` | resolved (see ladder) | **Override.** Where per-ticket tracking dirs (`task_plan.md`, `findings.md`, `progress.md`) live while a ticket is active. Read by `:start`, `:plan`, `:update`, `:pr`, `:merge`, `:archive`. |
| `archive_dir` | resolved (see ladder) | **Override.** Where `:archive` moves a ticket's tracking dir at end of life. |

**Resolution ladder — first match wins, and both paths resolve together.**

| | Condition | `tracking_dir` | `archive_dir` |
|---|---|---|---|
| **Tier 1** | the key is set | that value, **verbatim** | that value, **verbatim** |
| **Tier 2** | key unset, `.slopstop/` exists | `.slopstop/ticket-active` | `.slopstop/ticket-archive` |
| **Tier 3** | key unset, no `.slopstop/` | `~/.claude/ticket-active` | `~/.claude/ticket-archive` |

Tier 1 is per-key, so setting one still lets the other fall to tier 2. **Tier 2 needs only the directory** — its presence implies both subdirectories, and neither needs to exist yet. Tier 1 beats tier 2, so an explicit `tracking_dir = ".slopstop"` still means exactly `.slopstop` (tickets at `.slopstop/<TICKET>`) and existing state is never stranded.

The canonical definition — including the layout-mismatch report — is `skills/run/references/tracking-dir-resolution.md`, which every skill reads. It is one file precisely because twelve skills used to re-derive this and disagreed. (It moved from `skills/start/references/` when `:start` was deleted in `32ecb23`; the file is unchanged, only re-homed.)

**Path rules (all tiers).** Relative paths (no leading `/` or `~/`) resolve from the **main worktree root** (`dirname "$(git rev-parse --git-common-dir)"`) — *not* from the cwd. That is deliberate: every linked worktree resolves to the same directory, so worktree sessions and the main checkout share one tracking dir and no symlinking is needed. Absolute paths (leading `/` or `~/`) are used as-is.

**A layout mismatch is reported, never fixed.** If ticket dirs exist under a different tier's layout than the one resolved, the skill says so and continues — it never moves, merges, or deletes anything. Adopting stray state is your call: a wrong guess silently destroys the only record of in-flight work.

> **Do not put either directory inside `~/.claude/`.** It is a protected path: an agent's `Write` tool refuses it *even when the session was launched with a matching `--add-dir`*. Tier 3 therefore works for interactive sessions but silently fails for the headless fleet agents `/slopstop:run` launches — an agent that cannot write its tracking dir will invent a local one and carry on. The fix is to **create `.slopstop/`**, which moves you to tier 2. Note it is a *directory*, not a key: the old advice here was "set `tracking_dir` to a project-local path (e.g. `.slopstop/ticket-active`)", and a session that already had a `.slopstop` configured read that as instructions to append `ticket-active` to it — inventing a second, divergent tree. That is the bug tier 2 exists to remove.

**Consequence for `/slopstop:run`.** Because a relative path resolves against the *main* worktree root, the resolved tracking dir lies outside every agent's worktree. The orchestrator must launch each agent with `--add-dir <resolved tracking dir>`; see `skills/run/SKILL.md` Step 4.

**The `.slopstop/` layout** (v3 recommended):

- `.slopstop/ticket-active/<TICKET>/` — tracking for tickets in flight.
- `.slopstop/ticket-archive/<TICKET>/` — tracking for finished tickets.

Add `.slopstop/` to `.gitignore`. It is transient working state, not source; without the ignore, the first `:pr` stages every tracking dir into the PR.

**The `scratch/` layout** (seeded by `:gh-init`/`:design`; full spec: `design/slopstop-process.md` §4):

- `scratch/runs/<run-id>/` — per-run interchange: run state, PRD, feature charter, fleet-state file, verdicts, umbrella + final reports. Written by the stage skills; cleaned only after the human accepts at G-final.

`scratch/` is gitignored (the seeding appends the entry idempotently), so nothing in it is ever committed or shared.

---

### `[status_labels]` — GitHub Issues workflow shape

**GitHub only.** Ignored for Linear and JIRA (which use their native state machines).

```toml
[status_labels]
in_progress = "status:in-progress"   # Required — label applied when a ticket starts
# in_review  = "status:in-review"   # Optional — uncomment to enable 4-state workflow
```

| Key | Required | Default | Description |
|---|---|---|---|
| `in_progress` | ✅ Yes (GitHub only) | — | Label name applied when `:run` transitions a ticket to In Progress. Must exist on the repo. |
| `in_review` | ❌ No | absent | If set, enables 4-state workflow (`In Progress → In Review → Done`). `:run` advances the ticket after a merge — to its **terminal** state by default, or exactly one state when `[workflow] post_merge_done = false`, which is how a 4-state project parks a ticket in In Review for verification a machine cannot do. |

Create the labels before your first ticket:

```bash
gh label create "status:in-progress" --color "0075ca" --description "Actively being worked on"
gh label create "status:in-review"   --color "e4e669" --description "In review / QA"   # 4-state only
```

---

### `[pr_review]` — which bot's comments get read

**This block does not select a reviewer.** The review that gates a merge is `:run` stage 10's
`review` worker, and it runs on every PR whatever is configured here — including when the
block is absent entirely. `backend` names only *whose bot comments* stage 12 goes looking for.

```toml
[pr_review]
backend         = "claude"    # "coderabbit" (default) | "greptile" | "claude"
```

| Key | Type | Default | Description |
|---|---|---|---|
| `backend` | string | `"coderabbit"` | Resolves to `$PR_BACKEND`, read at exactly one place in `:run`: stage 12, where it *"selects whose comments to look for, nothing more"* (`skills/run/SKILL.md`). `"coderabbit"` / `"greptile"` — read that bot's existing PR comments once, never poll. `"claude"` — there is no bot, so stage 12 has nothing external to read and the run proceeds on the stage-10 verdict. It does **not** cause `/code-review` to be invoked; nothing can (see below). |
| `effort` | string | — | **Dead key. Read by nothing.** It was the effort passed to `/code-review`, which no skill can invoke. `:run`'s own review worker takes its effort from `[stage_tiers]`/`[tiers]` like every other stage. Harmless to leave in a config file; setting it changes nothing. |

**`/code-review` is not what any backend does, and no backend can make it happen.** The
built-in `/code-review` carries `disable-model-invocation` — only a human typing it can
launch it, so a skill, subagent, or headless run cannot, and a call site that appears to
invoke it is inert. This was verified against the harness on 2026-08-09, not carried over
from documentation. What the `claude` path has always meant is `Skill(slopstop:review)`
running under `context: fork`: a subagent with no access to the conversation that wrote the
code. That property is the point — see universal §9.

**Nothing posts a review linkback comment on the ticket.** This section previously claimed
`:pr` Step 7f did; `:pr` was deleted in `32ecb23` and `:run` has no equivalent step. The
closest surviving behaviour is different in both content and timing: stage 15's `archive`
worker posts one comment per tracking file (task plan, findings, `run.jsonl`) at run
completion. If a PR/review linkback is wanted, it does not exist today.

---

### `[design]` — the authoritative specification, and autonomous mode

**Both keys optional.** `spec` names the document(s) `/slopstop:design` treats as the source
of truth for a run. When set, every decision in the PRD is classified against it (`SPEC` /
`DERIVED` / `UNDERDETERMINED`), and the ticket-tree adversary's **check F** re-reads it to
verify each quoted excerpt still says what the decision claims. `autonomous` controls
whether the grill stage waits for a human on every question or resolves recommended answers
itself (BILL-603).

```toml
[design]
spec = "SPEC.md"                          # a single document
# spec = ["SPEC.md", "docs/api-contract.md"]   # or an array of them
autonomous = false                        # default; true skips the wait when a
                                           # recommended answer exists (see below)
```

| Key | Type | Default | Description |
|---|---|---|---|
| `spec` | string \| array of strings | _(unset)_ | Path(s), relative to the repo root, of the authoritative specification. A single path may be given as a bare string; several as an array of strings. Overridden per-run by `:design --spec <path>` (repeatable). |
| `autonomous` | boolean | `false` | When `true`, the grill resolves a question with a recommended answer immediately instead of waiting for a reply, and a conventional spec path is adopted instead of confirmed. Overridden per-run by `:design --autonomous`, which forces it on regardless of this key. Unlike `:run`, `:design` defaults to **off** — the existing fully-interactive behavior — since nothing about a design conversation implies unattended operation the way `:run` driving N already-written tickets does. |

**Resolution order** — `:design --spec` (repeatable, wins) → `[design] spec` → a conventional path (`SPEC.md`, `docs/spec*.md`). Under `autonomous = false` (the default) that conventional path is **proposed and confirmed**, never adopted silently; under `autonomous = true` or `--autonomous`, a conventional path that actually resolves is adopted the same way a recommended grill answer is — see "Autonomous mode", `:design`'s SKILL.md. If nothing resolves at all, the PRD records `SPEC: none — greenfield` and every decision defaults to `UNDERDETERMINED` unless it derives from the grill transcript, in both modes.

The PRD header records each resolved spec's path **and its `sha256`**. Check F compares that hash when it re-reads the document: a mismatch means the spec changed after the PRD was written, which silently invalidates every `SPEC`-classified decision, and is a finding in its own right.

**`autonomous` does not touch the tier gate.** Whether the running session's model matches the configured tier is a fact the session can or cannot verify about itself, not a decision with a recommendation to fall back on — the tier gate's "cannot determine" confirmation asks regardless of this key.

Same resolution rule as every other table: a missing key or missing table never errors.

---

### `[workflow]` — cross-mode behavior shortcuts

`skip_confirm` reduces friction in interactive sessions without enabling full autonomous mode. `skip_archive` is not mode-scoped at all — it applies identically in autonomous and `--interactive` runs.

```toml
[workflow]
skip_confirm = true    # true | false (default: false)
skip_archive = false   # true | false (default: false)
```

| Key | Type | Default | Description |
|---|---|---|---|
| `skip_confirm` | bool | `false` | If `true`, skips the interactive confirmation prompts in `:merge`, `:archive`, and `:start` (when a branch-type heuristic suggestion is available). Auto-proceeds as `yes` and logs the plan. Has no effect in an autonomous run, which already skips confirmations. |
| `post_merge_done` | bool | `true` | After a merge, take the ticket to its **terminal** state. `false` advances exactly **one** state and stops, parking the ticket for verification a machine cannot do — the case is on-device mobile testing, where an Expo/EAS build has to reach real hardware, possibly days later, and a human moves it to done once it passes. `:run` reports parked tickets under their own heading, never folded in with completed ones. Note a `Closes #N` in a PR body overrides this entirely by auto-closing — another reason never to write one. |
| `skip_archive` | bool | `false` | If `true`, `:merge` skips its `:document` push (description/DoD/findings) and its Step 10 archive chain (tracking-dir move) entirely — for every merge, not just terminal-state ones. Instead it posts a single comment with the merge commit id when the ticket transitions state. `$TRACKING_DIR/$TICKET/` is left in place indefinitely. Same effect in interactive and autonomous mode. |

**When to use `skip_confirm`:** personal projects where you always say yes and the confirmation adds friction without value. Not recommended for team repos where multiple people might need to review what's about to happen.

**When to use `skip_archive`:** projects that don't want the full plan/DoD/findings pushed to every ticket — e.g. tickets tracked lightly, or where the commit history itself is the record. Most projects should leave this `false`: `:archive`'s documentation push is what turns a ticket into a durable record of what was actually done, not just a title and a merged PR diff.

---

### `[tiers]` — model tiers for the four-tier process

Assigns a model to each tier of the slopstop process (see `design/slopstop-process.md`). Stage skills hard-stop when the session model doesn't match their declared tier; subagent tiers (adversaries, reviewers, fleet agents) are set explicitly from this table.

Each tier is a nested table with `provider` and `model` fields, an optional `version` field to pin a specific model version, and an optional `effort` field — the tier's *default* reasoning effort (BILL-333). `effort` is a separate dial from `model`: it says how hard the tier's model thinks, not which model it is.

**`effort` is read as of BILL-486 (2026-08-07).** It was inert for months — `worker-launch.md` claimed per-stage effort tuning was impossible, and that claim was false. `:run` now resolves `[tiers.<name>].effort` and launches a shipped `slopstop-effort-<level>` subagent carrier, which is where the harness actually takes an effort level. Fleet target: **`high` on all four tiers**, applied by `tools/fleet-sync/sync-project-conf.py` from `fleet.py`'s `TARGET_EFFORT`.

**The tier's effort is a ceiling, not a fixed level.** A stage may resolve *lower* where its risk surface is narrower — stage 10b drops to `medium` for a refactor or backfill ticket, whose diff is mechanically fenced and which already has one of the two tier-above checks skipped. No stage may resolve higher than its tier.

```toml
[tiers.huge]
provider = "anthropic"
model    = "fable"
# version  = ""      # optional: pin to a specific model version
# effort   = "high"  # low | medium | high | xhigh | max  (default: "inherit" — no effort passed)

[tiers.large]
provider = "anthropic"
model    = "opus"
# effort   = "high"

[tiers.medium]
provider = "anthropic"
model    = "sonnet"
# effort   = "medium"

[tiers.small]
provider = "anthropic"
model    = "haiku"
# effort   = "medium"
```

The four tiers descend `huge > large > medium > small`; each stage runs one tier down from the last, and the tier **above** a producer checks its work.

| Tier | Key | Type | Default | Description |
|---|---|---|---|---|
| `huge` | `provider` | string | `"anthropic"` | Provider for the huge tier (`:design`, huge-tier checks: ticket-tree adversary, rewrite delta checks, final-report adversary). |
| `huge` | `model` | string | `"fable"` | Model for the huge tier. |
| `huge` | `version` | string | _(none)_ | Optional: pin to a specific model version. |
| `huge` | `effort` | string | `"inherit"` | Optional: default reasoning effort for spawns resolved to this tier. One of `low` / `medium` / `high` / `xhigh` / `max`, or omitted for `"inherit"` (no effort passed — the spawn behaves exactly as it does without this key). |
| `large` | `provider` | string | `"anthropic"` | Provider for the large tier (`:tickets`, failure-driven rewrites, umbrella/integration drift checks). |
| `large` | `model` | string | `"opus"` | Model for the large tier. |
| `large` | `version` | string | _(none)_ | Optional: pin to a specific model version. |
| `large` | `effort` | string | `"inherit"` | Same as `huge`'s `effort` key, scoped to the large tier. |
| `medium` | `provider` | string | `"anthropic"` | Provider for the medium tier (`:run` orchestrator, per-ticket reviewer/adversary subagents). |
| `medium` | `model` | string | `"sonnet"` | Model for the medium tier. |
| `medium` | `version` | string | _(none)_ | Optional: pin to a specific model version. |
| `medium` | `effort` | string | `"inherit"` | Same as `huge`'s `effort` key, scoped to the medium tier. |
| `small` | `provider` | string | `"anthropic"` | Provider for the small tier (the `implement` worker). |
| `small` | `model` | string | `"haiku"` | Model for the small tier. |
| `small` | `version` | string | _(none)_ | Optional: pin to a specific model version. |
| `small` | `effort` | string | `"inherit"` | Same as `huge`'s `effort` key, scoped to the small tier. |

**Effort fallback chain.** A spawn's effort resolves in one order, everywhere:
its specific key → the resolved tier's effort → the key's own floor. **Worker
effort IS configurable as of BILL-486** — it resolves from `[tiers.<name>].effort`
and is carried by a shipped `slopstop-effort-<level>` subagent definition. This
sentence previously said the opposite ("the plugin cannot ship the subagent
definitions that would carry it"), which was false: `install-for-project.sh`
writes them to `.claude/agents/`, and a probe confirmed a project-scope definition
loads with its frontmatter applied.
The only "specific key" this chain ever had was `[pr_review].effort`, and that key
is dead — nothing reads it (see `[pr_review]` above). So in practice the chain has
one live input: the resolved tier's `effort`, falling back to the floor of
`"inherit"` (no effort passed). Setting `[pr_review].effort` does not override a
tier, because it is not read at all. `effort` reaches a spawn through the fleet CLI's `--effort`
flag or through a skill/subagent definition's frontmatter — not through the
`Agent(...)` call, which has no `effort` parameter. A spawn that names no
slopstop-defined subagent type inherits the invoking session's effort instead.
See `design/agent-effort-capability.md` for the per-site status.

**Resolution rule (applies to this table and every `[fleet.*]` table below):** all keys and tables are optional — a missing key within a tier resolves to its documented default, and a missing `[tiers]` table never errors. Skills read this config defensively. Every artifact a tier produces carries a provenance header naming the model that produced it, so substituting cheaper models here is visible, if inadvisable.

`version` is optional on every tier — an omitted `version` resolves to any version of the family named by `model`, rather than pinning to a specific one.

`url` is deliberately absent from this schema. Tiers name a provider and a model family for skills to route work to; gating never dials an endpoint directly, so there is no URL for a tier to carry.

The legacy flat string form under `[tiers]` (e.g., `huge = "fable"`) is rejected with a loud error — the nested table structure is required.

---

### `[stage_tiers]` — process structure (stage → tier)

> **There is deliberately no `run` key.** `:run` has no tier gate, and adding one would
> break it. The gate is an **exact family match**, not a minimum — `[stage_tiers].tickets
> = "large"` → `[tiers.large] = opus` means `:tickets` hard-stops on a sonnet session. A
> `run = "medium"` key would therefore hard-stop `:run` on *opus*, forbidding the higher
> tier rather than the lower one. Gating matters for `:design` and `:tickets` because a
> wrong-tier PRD or ticket tree poisons everything below it; `:run` coordinates, and every
> piece of judgment work it delegates resolves its own tier through this table anyway.

**Optional.** Decouples *process structure* from *model deployment*. `[tiers]` (above) maps each tier to a model; `[stage_tiers]` maps each stage and check-point to a **tier name**. Resolution is two hops — **stage → tier → model** (e.g. `stage_tiers.design = "huge"` → `tiers.huge = "fable"`). Re-tiering a stage — moving `:tickets` up a tier, bumping a checker — is a one-line edit here, with no skill rewrite.

```toml
[stage_tiers]
design              = "huge"     # :design tier gate
tickets             = "large"    # :tickets tier gate
ticket_adversary    = "huge"     # checks the large tier's ticket tree
rewrite_delta_check = "huge"     # checks a large-tier rewrite before relaunch
drift_check         = "large"    # checks the integrated code at umbrella completion
handoff_verifier    = "medium"   # checks the small tier's per-leaf implementation
report_adversary    = "huge"     # checks the final report
```

| Key | Type | Default | Runs at this tier |
|---|---|---|---|
| `design` | string | `"huge"` | `/slopstop:design` tier gate |
| `tickets` | string | `"large"` | `/slopstop:tickets` tier gate — covers all three of its modes (tree, `--retrofit`, `--rewrite`) (no dedicated key; it does the same caliber of per-leaf work, just for one existing ticket) |
| `ticket_adversary` | string | `"huge"` | the `adversary` worker, wherever `:tickets` launches it — tree, `--retrofit`, and the `--rewrite` scope-subtraction delta check |
| `rewrite_delta_check` | string | `"huge"` | the mandatory pre-relaunch delta check on a rewrite |
| `drift_check` | string | `"large"` | the umbrella-completion drift check |
| `handoff_verifier` | string | `"medium"` | the two per-leaf handoff verifiers (requirements adversary + code review) |
| `report_adversary` | string | `"huge"` | the final-report omission adversary |

Same **resolution rule** as `[tiers]`: a missing key resolves to its documented default (the values above — the "checker one tier above the doer" ladder); a missing `[stage_tiers]` table never errors. The `implement` worker resolves from `[tiers].small`, and each checking stage resolves one tier above the work it checks. There is no tier-escalation-on-retry any more: a ticket that fails implementation twice stops and is referred to `/slopstop:tickets --rewrite`, on the reasoning that a second failure is more often an underspecified ticket than an under-powered model.

---

### `[fleet.*]` — removed 2026-08-06

`[fleet.agents]`, `[fleet.monitoring]`, `[fleet.budget]` and `[fleet.router]` are gone.
They configured the fleet launcher: headless `claude -p` worker processes, a polling
monitor with kill triggers, per-ticket attempt and escalation caps, and the metering
router. All four mechanisms were deleted in the v4.0.0 reorganization.

`:run` still drives many tickets at once — that capability is not lost — but it launches
**worker agents** rather than CLI processes, so there is no launch model to configure, no
poll interval (it awaits results), no `--allowedTools` grant to assemble, and no
`ANTHROPIC_BASE_URL` to inject. Delete these tables from your `.project-conf.toml`;
nothing reads them, and `tools/fleet-sync/audit-project-conf.py` reports any that remain.

Two things they carried that are now behavioral rather than configurable: a ticket stops
after **two** failed implementation attempts (`:run` then recommends
`/slopstop:tickets --rewrite <TICKET>`), and per-stage models come from `[stage_tiers]` →
`[tiers]`, which is where they always belonged.

**BILL-467 considered reintroducing `[fleet.budget]` and did not** (2026-08-07). It restored
the failure/retry/salvage machinery those caps used to govern, so the question was live and
the ticket's file map named these files "if reintroduced". The answer is no: the cap that
matters — two failures is a diagnosis point, not a third attempt — already exists as
behaviour above, and it now covers verification failures as well as implementation ones. An
attempt is **counted by reading `run.jsonl`**, not stored, so it survives compaction and a
resume. Adding a `[fleet.*]` table back would resurrect vocabulary for a launcher that no
longer exists, and `audit-project-conf.py` would then be reporting the same table it was
written to flag. The decision is recorded here so it does not have to be re-argued from an
empty file map entry; the full disposition is in
`design/worktree-parallelism-prior-art.md`.

### `[complexity]` — cyclomatic-complexity gate thresholds

Bounds for the `complexity-check` worker. **Read by the orchestrator, never by the worker**
— `:run` resolves these and passes them as explicit arguments, and `complexity-check` blocks
rather than falling back to a default it carries. Two readers of one config is two answers
to one question.

This table was called `[autonomous]` until 2026-08-06. It held a master switch and seven
`on_*` gate knobs, all deleted when `:run` became autonomous by default with a single
`--interactive` flag; `merge_strategy`, `merge_target_state` and `archive_immediately` went
with them (see below). What remained had nothing to do with autonomy, so the table is named
for what it actually holds.

```toml
[complexity]
# Inclusive lower bounds: cc_warn_threshold <= CC < cc_reject_threshold warns;
# CC >= cc_reject_threshold rejects. A `reject = 10` that let CC 10 through
# would not mean what it says.
cc_warn_threshold      = 5      # 🟡 elevated boundary
cc_reject_threshold    = 10     # 🔴 hard-gate boundary
cc_exempt_pre_existing = true   # exempt a violation this branch did not make worse
file_nloc_warn_threshold = 400  # 🟡 file-size warning; 0 disables
```

| Key | Default | Description |
|---|---|---|
| `cc_warn_threshold` | `5` | 🟡 CC-elevated boundary for the CC gate (Step 0c). **Inclusive lower bound**: functions with `cc_warn_threshold <= CC < cc_reject_threshold` are flagged 🟡 — 5–9 at the defaults. |
| `cc_reject_threshold` | `10` | 🔴 hard-gate threshold for the CC gate. **Inclusive**: functions with `CC >= this value` are violations — 10 or above at the defaults. |
| `cc_exempt_pre_existing` | `true` | Exempts a 🔴 CC violation the branch **did not make worse** — see the semantics below. Still printed, ranked, with a total. `false`: every 🔴 blocks and no base measurement is taken. |
| `file_nloc_warn_threshold` | `400` | 🟡 file-size warning in the CC gate. Files whose lizard NLOC sum exceeds this threshold are flagged 🟡. Set `0` to disable. |

#### Ticket modes are not configuration

`:run` supports three ticket modes — normal, **refactor**, and **backfill** — and none of
them is a config key. A ticket declares its own mode with a **label**, `slopstop-refactor`
or `slopstop-backfill`, applied when the ticket is cut rather than when the code is written.
There is nothing to set here and nothing to switch on per project.

**The two label names are fixed and deliberately not configurable.** `[status_labels]` is
configurable because a project may already have its own status vocabulary; making the mode
labels configurable would turn one definition (universal §5) into a required key a project
can get wrong — and getting it wrong means mode silently fails to resolve, which runs the
ticket as normal and skips the gates the mode exists to impose.

**The one definition lives in `skills/run/SKILL.md`, "Invariant tickets — refactor and
backfill"** — including the symmetry table, the label names, and why the separator is a
hyphen rather than a colon. It is deliberately not restated here (universal §5); a second
copy of a rule this mechanical is a second copy that drifts.

The connection to this table is one-way and worth knowing: `cc_exempt_pre_existing` is what
stops a feature ticket being *forced* to carry a refactor, and the exempt list it prints is
the input to `/slopstop:tickets --refactor`.

#### `cc_exempt_pre_existing` — what "pre-existing" means, and why

**Semantics: *did not get worse*.** A 🔴 function is exempt when it existed at the base
commit with `CC_base >= CC_head`. Everything else blocks — a function the branch created,
one it worsened, and one whose base counterpart could not be identified or measured. The
rule in one sentence: **you may work inside a pre-existing giant as long as you do not make
it worse.**

Deciding it needs the base numbers, so `complexity-check` runs `lizard` a second time
against a scratch worktree at `--base` (the mechanism `vacuity-check` already uses to reach
base-era code). When that measurement cannot be taken, **nothing is exempt** and the report
says the exemption was inert.

Two other readings were on the table when this was decided (BILL-468, 2026-08-07):

| semantics | what it exempts | why not |
|---|---|---|
| **A. untouched by the diff** | a 🔴 whose line range no hunk overlaps | what shipped before this ticket. It does not solve the problem: a ticket that must *edit* a CC-139 function is still blocked by it, which is exactly the pressure that forces a refactor into a feature branch. |
| **B. already violating at base** | any 🔴 that was already 🔴 | blesses new branching added to an existing giant. A gate you can get past by working inside the worst function in the file is worse than no gate. |
| **C. did not get worse** ✅ | a 🔴 with `CC_base >= CC_head` | chosen. |

C strictly widens A rather than replacing it — an untouched function measures identically
at both commits, so it is exempt under C too. What C adds is the case the flag exists for.

**The default flipped `false` → `true` in BILL-468.** The gate was forcing refactors into
feature tickets: the implementer hit a pre-existing violation, decomposed the function to
get past it, and a behaviour-preserving refactor landed inside a feature branch with no DoD
item and no guards. GAST-8 did exactly that. The exemption removes the pressure; the ranked
exempt list turns what it skips into a work queue for
`/slopstop:tickets --refactor <fn>…`.

**This is not a way past the gate.** Complexity the branch created or worsened is judged at
the usual 5 / 10 boundaries, unchanged. Replayed against GAST-8's recorded violations —
`linkWithObjs 139` (grew), `archiveCreate 19`, `archiveRead 18`, `parseObjELF 38`
(untouched) — `linkWithObjs` still blocks under C, because it got worse.

#### Keys removed 2026-08-06

`merge_strategy` and `merge_target_state` were read only by `:merge`'s reference files,
which no longer exist. `:run` hard-codes `gh pr merge --merge --delete-branch`, and
universal §3 forbids squash and rebase merges outright — so `merge_strategy`'s other two
values were rule violations the knob invited. `archive_immediately` was read by nothing at
all and duplicated `[workflow] skip_archive`.

## `.harvester.toml` — credentials (gitignored)

Copy `.harvester.toml.example` and fill in values for your ticket system:

```toml
[linear]
api_key = "lin_api_..."

# [jira]
# email     = "you@example.com"
# api_token = "..."
# base_url  = "https://your-site.atlassian.net"
```

---

## Claude Code settings hierarchy and scope

### Settings load order

Claude Code applies settings from multiple sources in priority order (highest wins):

1. **Managed** — set by the organization/account administrator
2. **Command-line flags** — passed at startup
3. **Local** — `.claude/settings.local.json` in the project root (gitignored)
4. **Project** — `.claude/settings.json` in the project root (committed)
5. **User** — `~/.claude/settings.json` (machine-local)

This applies to all settings: permissions, tool configurations, environment variables, etc.

### Controlling which settings sources load: `--setting-sources`

Claude Code accepts a `--setting-sources` flag that takes a comma-separated list of settings scopes to load. Use this when you want to restrict or expand which layers of settings and skills are active for a session.

```bash
claude --setting-sources user                   # user settings only (~/.claude/)
claude --setting-sources project                # project settings only (.claude/ in cwd)
claude --setting-sources user,project           # both (the normal default)
claude --setting-sources project,local          # project + machine-local overrides, no user
```

Available source names mirror the settings hierarchy: `managed`, `user`, `project`, `local`. Combine as many as needed with commas; order does not change the priority (the hierarchy above still applies within the loaded set).

**Why this matters for users with extra skills:** if you have personal skills in `~/.claude/commands/` (user-level) and want to run a project session with *only* the project's plugin skills loaded — no personal extras — start Claude with:

```bash
claude --setting-sources project
```

Conversely, to use your user-level skills without any project config influencing the session:

```bash
claude --setting-sources user
```

### Skills (slash commands) scope

Skills are loaded from multiple locations:

- **User-level:** `~/.claude/commands/` — available in every project on this machine
- **Project-level:** `.claude/commands/` in the project root — available only in this project
- **Plugin-installed:** managed by `/plugin` install/uninstall; namespaced (e.g. `/slopstop:run`)

By default all sources load. `--setting-sources` controls which subset loads for a given session.

**`.claude/settings.local.json`** (per-machine project override): a gitignored file at the project root. Loaded as the `local` source — highest priority among committed/local layers. Useful for per-machine opt-outs that should not affect collaborators.

### Plugin vs Desktop install

| Install method | Command namespace | Commands file |
|---|---|---|
| `claude` CLI + `/plugin install` | `/slopstop:run`, `/slopstop:design`, … | Managed by plugin system |
| `install-for-claude-desktop.sh` | `/slopstop-run`, `/slopstop-design`, … | `~/.claude/commands/slopstop-*.md` |

The Desktop install drops files into `~/.claude/commands/` as user-level commands (un-namespaced). If you have both a plugin install and a Desktop install, you get duplicate commands — uninstall one:

```bash
# Remove Desktop install:
rm ~/.claude/commands/slopstop-{start,plan,update,document,archive,pr,merge,doc-sync,create-gh}.md
```

---

## `.mcp.json` — MCP server declarations

Committed to the project root. Claude Code picks it up at session start and launches the declared servers. For most slopstop projects, the file is empty:

```json
{
  "mcpServers": {}
}
```

MCPs required by the skills (Linear, GitHub, JIRA) are installed as plugins via `/plugin install`, not declared in `.mcp.json`. See `SETUP-GUIDE.md §3` for the install commands.

If your project needs project-specific MCP servers (e.g. a custom internal tool), declare them here as additional entries under `mcpServers`.
