[← 2. Tickets and the adversary](02-tickets-and-adversary.md) · **3. The handoff** · [4. Fleet execution →](04-fleet-execution.md) · [Index](README.md)

---

# 3. The handoff — where the session forks

**10:59:48 – 11:06:25 · still `claude-opus-5`**
Source: Transcript A, turns cited as `[n]`. Notation key: [index §3](README.md#3-notation).

Seven minutes, no code, and the most instructive refusal in the run: Stage 3 declines to launch
on a model that is *better* than the one it requires.

---

### 10:59:48 `[301]` — Ian asks for the impossible without knowing it

> **IAN SAYS:** "go ahead and commit. then
> `/slopstop-run kvstore-20260725-1001`."

**Why it matters:** this instruction cannot be carried out in this session, and it takes 3 minutes
for that to surface. Everything below is the process discovering that.

---

### 11:01:18 `[327]` — An unrelated real-world failure, handled without touching the config

Push fails. The global `~/.gitconfig` points its github.com credential helper at
`/Users/iansmith/parigot/tools/bin/gh`, which no longer exists (`gh` is at `/opt/homebrew/bin/gh`).

> **SLOPSTOP SAYS:** "I pushed over SSH instead and **changed no config**. When you want it fixed: …"

— followed by the exact one-liner, at `[335]`.

**Why include it:** a 30-second aside that shows the boundary being respected. A broken
machine-global setting is reported, not silently repaired. Contrast it with 11:36 in
[§4](04-fleet-execution.md), where the orchestrator *does* edit a global settings file — but only
after asking and being told to.

Also at `[335]`, the review pass earns its keep: it found the config comment was
about twice as long as needed (trimmed to 6 lines) and caught that `.gitignore` was still
untracked. That second one matters — worktrees are created from HEAD, so an untracked `.gitignore`
would have meant every fleet worktree missing the `scratch/` and `.slopstop/` rules.

---

<a id="tier-gate"></a>
### 11:02:30 `[350]` — **Stage 3 refuses to launch. Two hard stops.**

> **GATE (hard stop):** "**Stage 3 did not launch.** Nothing was created — no worktrees, no briefing comments, no agents. Two hard stops, both real:"

**Stop 1 — tier gate.** `[stage_tiers]` absent → `:run` resolves to the **medium** tier →
`[tiers.medium] = sonnet 5`. This session is `claude-opus-5`. The family does not match.

And the refusal is *justified*, not merely enforced:

> **SLOPSTOP SAYS:** "This one is not softenable, and the reason is specific to Stage 3: the orchestrator holds **autonomous kill authority** over fleet agents — it terminates them without asking you. The gate is what makes that authority safe to hold, so I won't wave it through."

> **Since v4.0.0:** the tier gate is still a hard stop, but the *justification* quoted here has
> been overtaken. There is no kill authority any more — `:run` launches worker agents that return
> a result or return `BLOCKED`; nothing is terminated. The tier gate now earns its keep on
> different grounds: the orchestrator resolves every threshold and every model from config and
> passes them to workers explicitly, so a wrong-tier orchestrator misconfigures the entire run
> silently.

**Stop 2 — fleet precondition.** `[autonomous]` is absent from `.project-conf.toml` entirely, with
the consequence spelled out:

> **SLOPSTOP SAYS:** "Fleet agents run headless. Without this, each one hits `:start`'s interactive branch-type prompt, blocks forever, and gets killed for silence — **five agents burning attempts on a config gap.**"

> **Since v4.0.0:** this stop no longer exists. The entire `[autonomous]` block was deleted —
> `:run` is **autonomous by default**, with one `--interactive` flag as the only switch, so there
> is nothing to declare in config and nothing to be absent. There is also no `:start` to reach an
> interactive prompt in, and no headless agent to block forever.

**Caused by:** the gate that *passed* at **10:01:49** at the top of the grill — same mechanism,
opposite outcome. Show them as a pair.

**Why this is the strongest gate moment in the run:** the failure is on an over-powered model.
Opus is *better* than the required Sonnet, and it still refuses — because the gate is not about
capability. It is about which tier the config authorized to hold kill authority over other agents.

---

### 11:03:39 `[370]` — The one thing it cannot fix

> **SLOPSTOP SAYS:** "Blocker 2 cleared and pushed. Blocker 1 stands, and I can't clear it from here — **a session can't change its own model.**"

It stages everything for the successor session — G2 passed, `.gitignore` now tracked,
`[autonomous]` satisfied — and states the fleet-tier choice explicitly:

> **SLOPSTOP SAYS:** "`[fleet.*]` is absent, so CONFIG.md defaults apply — agents resolve from `[tiers].small` = `haiku 4-5`. That's the tutorial's deliberate choice: **a weak model so `:run`'s file-map-violation kill, handoff adversary, and rewrite loop have something real to catch. Expect failed attempts; they're the demonstration, not a malfunction.**"

Then, unprompted, it predicts a specific silent failure mode in the *next* session:

> **SLOPSTOP SAYS:** "`:run` appends each ticket's test command to `--allowedTools`, read from a `Test command:` line in the ticket's Test expectations. My tickets state the command inline as `go test ./...` rather than on a labelled `Test command:` line, so Stage 3 may not derive the `Bash(go:*)` grant automatically — **and a missing grant shows up only as an agent going quiet.** If the first agent stalls without visible errors, that's the first place to look."

**Why interesting:** a handoff note that anticipates how the successor will fail, in a way that
would otherwise be indistinguishable from a hung process. This is also where the transcript splits
into two files.

---

### 11:04:12 `[374]` → 11:06:25 `[400]` — A correction becomes a bug report against the tool

> **IAN SAYS:** "Please do not change the 'default branch type prefix' in the `.project-conf.toml` because NOT setting it reverts to a fallback that computes the prefix automatically."

It reverts and pushes, leaving a comment recording *why* the field is unset "so nobody re-adds
it." Then it files two findings **against slopstop, not against this run**:

1. **`:run`'s docs contradict `:start`'s.** `:run`'s Fleet precondition demands `[autonomous] enabled = true` *with `branch_type` set* and hard-stops otherwise; `start-autonomous.md` calls unset "the common case — no reason to require it just to avoid a prompt."
   > **SLOPSTOP SAYS:** "Since this repo is the tool those rules run on, flagging rather than picking one: `:run`'s precondition text looks like the stale side."

2. **A concrete gap that follows from it.** `:run` Step 4.2 creates each worktree with
   `git worktree add -b <TYPE>/<TICKET>` *before* the agent starts. With `branch_type` unset,
   `:run` must compute the same label/title heuristic itself — otherwise the branch `:run` creates
   and the branch the agent's `:start` resolves diverge, breaking the skill's own promise that the
   agent "finds the branch already checked out." `:run`'s text does not mention this.

> **Both findings are closed, and the way they were closed is the point.** Neither side of the
> contradiction won. `[autonomous].branch_type` was **deleted** — it was a knob for a decision
> that should simply be made, and its failure mode was a hard stop when the heuristic found
> nothing. Branch type now resolves from one definition, used by the one thing that cuts branches:
> labels first, then the title, then the ticket body, and finally the literal `unk`. `unk` is a
> real answer, not a failure — renaming a branch costs one command, while stalling a run costs a
> run, and confabulating `feat/` for something you could not classify is worse than `unk` because
> it looks decided. Ian's correction at 11:04:12 — *not setting it reverts to a fallback that
> computes the prefix automatically* — is now the whole design.
>
> Finding 2 dissolved with the mechanism: there are no worktrees to pre-create and no second
> session to resolve a branch name independently. One orchestrator cuts the branch, once.

It also discloses a judgment call and how to reverse it: #2 had no label and a title matching no
pattern, so it would have been the one leaf to hard-stop — and being the blocking foundation
ticket, it would have stopped first. Added `enhancement` → `feat/2`. *"If you'd rather it read
`chore/2` or `build/2`, swap the label."*

**Why interesting:** a one-line human correction at 11:04:12 gets converted into a documented
contradiction in the tool's own specification. This is the clearest instance of the run being used
as a test of slopstop rather than of the KV store.

---

## Section summary

Three minutes of work, four minutes of refusal, and the run splits in two.

| | |
|---|---|
| **What blocked** | tier gate (opus ≠ sonnet), fleet precondition (`[autonomous]` absent) |
| **What was fixed here** | `[autonomous] enabled = true`, `.gitignore` tracked, `#2` labelled |
| **What could not be** | the model of the running session |
| **What was flagged upstream** | `:run` vs `:start` doc contradiction; branch-name divergence gap |
| **How that was settled** | both closed in v4.0.0 — `[autonomous]` deleted entirely, branch type resolved from labels → title → body → `unk` |
| **Result** | a fresh session on `claude-sonnet-5` — Transcript B, where [§4](04-fleet-execution.md) picks up |

---

[← 2. Tickets and the adversary](02-tickets-and-adversary.md) · **3. The handoff** · [4. Fleet execution →](04-fleet-execution.md) · [Index](README.md)
