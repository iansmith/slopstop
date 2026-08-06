[← 3. The handoff](03-handoff-and-gates.md) · **4. Fleet execution** · [5. The report adversary →](05-report-adversary.md) · [Index](README.md)

---

# 4. Fleet execution — nine tickets driven concurrently

**11:08:32 – 12:52:44 · `claude-sonnet-5` orchestrator, `claude-haiku-4-5` implementers · tier gate PASS**
Source: Transcript B, turns cited as `[n]`. Notation key: [index §3](README.md#3-notation).

Nine tickets, seven merged branches. Along the way: a launch bug that costs nothing, a failed
attempt, a no-op, a model escalation, and two investigations into edited test files.

> Reminder from [§3](03-handoff-and-gates.md): the implementing agents ran on the **small tier by
> deliberate choice**, so that the checking machinery had something real to catch. The failures
> below are the instrument working.

---

## Read this first: the mechanism changed in v4.0.0

**This section is a record of a real run, and it is quoted verbatim.** The catches below are what
the walkthrough is for and they still stand. But the *machinery* that produced them was replaced
in the v4.0.0 reorganization, and reading the quotations as current documentation will mislead
you. The differences, up front:

| In the transcript (v3) | Today (v4) |
|---|---|
| A "fleet": one headless `claude -p` background session per ticket, each in its own git worktree | **`:run` launches worker agents** from a single orchestrator session. No headless CLI, no `--allowedTools` grant to compose, no worktrees to prepare |
| Four different agent-launch dialects across `:run`, `:plan`, `:design`, `:single-ticket` | **One launch form** for all eleven workers and all three orchestrators |
| A metering router agents were tagged against | Deleted. Timing is recorded directly in `run.jsonl` |
| The orchestrator polls agents on a monitoring cadence and holds **kill authority** — it terminates a silent or misbehaving agent | No poll and no kill. A worker returns a result or returns `BLOCKED`; the orchestrator branches on the verdict line |
| An **attempt budget** per ticket (3), a diagnosis fork after 2 failures, and an escalation ladder | Gone as machinery. Two failed implementations is read as a likely **ticket** defect, and the recommendation is `/slopstop:tickets --rewrite`, whose mandatory scope-subtraction check stops the ticket being quietly made easier |
| Waves: a hand-planned wave 1 / wave 2 / wave 3 | **Conflict scheduling**, described below |
| `G-failure` — a distinct gate for a run that could not finish | Gone. A failing gate stops **that ticket**, not the run |

**What survives is the capability, not the implementation.** `:run` still drives N tickets
concurrently, still freezes tests before implementation, still has a fresh reader check every
result, and still refuses to let the session that wrote the code review it.

### How `:run` schedules N tickets now

There is no wave plan to author. The schedule falls out of the first stage:

1. **Fan out `investigate` for every ticket before anything else.** It is read-only, so it is
   always safe in parallel, and each run returns a **predicted file map**.
2. **Schedule by overlap.** Tickets with disjoint predicted file maps run their lifecycles
   concurrently; overlapping ones run serially, later ones starting from the updated tip.
   Prediction is never perfect, so this is an efficiency measure and is not relied on for
   correctness.
3. **Merge serially, always** — regardless of what step 2 concluded. One PR at a time. On
   conflict: `git merge master` into the losing branch, resolve, re-run that ticket's tests, push,
   merge. **Never rebase** — rebasing a pushed branch requires a force push.

Compare that with `[76]` below, which is the same idea arrived at by hand.

### And when something fails

A failing gate closes that ticket's span `failed`, preserves its branch and tracking directory,
and **every other ticket keeps running**. The stopped set is reported together at the end with
what each needs. Mechanical gates — red-test tamper, vacuity, slop findings — stop a ticket in
either mode and at any change size; there is no permissive setting to reach for.

With that established, the record.

---

### 11:11:09 `[76]` — The wave plan, and a consent gate before anything becomes public

> **SLOPSTOP SAYS:**
> **Wave 1** (solo): #2 Foundation — blocks everything.
> **Wave 2** (parallel once #2 lands): #4 set, #5 get, #6 delete, #7 list, #8 export — disjoint file maps.
> **Wave 3** (solo fan-in): #9 Integration — after all of #4–#8 land.

**Caused by:** Q2 at **10:09:48** in [§1](01-design-and-grill.md). This *is* that answer, executed.

*Then:* each agent launched as a headless `claude -p` background session with an explicit
`--allowedTools` grant, created a worktree and branch, and posted progress comments on its own
GitHub issue. *Now:* the same shape is computed rather than authored — "disjoint file maps" is
literally the scheduling rule, taken from what `investigate` predicts rather than from what the
ticket tree asserted.

And it stopped before acting on the outside world:

> **GATE:** "Before I fire Step 4 and start pushing real branches/comments to that **public** repo: confirm I should launch the fleet now, starting with #2?"

---

### 11:2x – 11:40:30 `[225]` — Three nested blockers, and a zero-cost accounting decision

1. First launch fails. Diagnosis: `--permission-mode auto` does not auto-approve the agent's **own `Write` tool**; `acceptEdits` does.
2. Second blocker: the orchestrator's *own* classifier will not let it launch a subprocess with `acceptEdits`.
3. At **11:36:21** `[186]` Ian asks for the permission rule; it adds `Bash(claude -p *)` to `~/.claude/settings.json` — **global scope, Ian's choice, after confirming**.
4. Relaunch — and the accounting call:

> **SLOPSTOP SAYS:** "**no attempt consumed** for the first failed launch since it was an **orchestrator bug, not a ticket/agent defect**."

**Why interesting:** the attempt budget was what eventually escalated a model tier and eventually
gave up. Charging a ticket for the orchestrator's own bug would corrupt every downstream decision.
This exact distinction gets re-litigated by the adversary at 13:03 in
[§5](05-report-adversary.md) — and the ledger turns out to have been right while the prose was wrong.

**All three blockers are now structurally impossible**, and that is the single clearest argument
for the v4 launch change: there is no subprocess, so there is no permission mode to get wrong, no
classifier to refuse it, and no global settings file to edit. The judgment that survives is the
one about accounting — don't charge the work for the tool's own defect.

---

### 11:52:34 `[252]` — The tamper check passes, and the verification still runs

> **SLOPSTOP SAYS:** "Gate 0 (red-test tamper check) passes mechanically — the frozen test files (`store_test.go`, `resolve_test.go`) show **zero diff** between the Phase 0 commit and the branch tip. Now spawning the two fresh handoff-verification subagents (requirements adversary + code reviewer) **in parallel**."

**Why interesting:** a clean tamper check is not a pass. Two fresh readers with no conversation
history are spawned anyway, and they are what find the next thing.

That structure is intact — the two verifiers are now the `slop-check`, `vacuity-check` and
`review` workers, launched at defined stages with the frozen commit passed to them explicitly.
The frozen sha is captured at the moment the Phase 0 commit is made and threaded onward, never
recovered afterwards by grepping the log for "Phase 0" — that derivation is wrong on any branch
carrying a second such commit, and the gap-test commit is exactly that.

---

<a id="writable-dir"></a>
### 11:55:55 – 11:56:43 `[255]`,`[258]`,`[260]` — **Attempt 1 FAILS. Two independent subagents converge on the same defect.**

> **ADVERSARY** *(both verifiers, independently)*: "`View()` never acquires the sidecar lock, so it never touches the `<store>.lock` sidecar and thus never requires a writable directory. On a read-only directory with no store file, it returns `(map[string]string{}, nil)` instead of erroring — **a silent empty read**."

Both verified it **live**, not by reading: created a `0500` directory containing no store file,
called `View(cfg)`, got `map[] err=<nil>`. Both quoted the ticket's Observable behavior 4 verbatim
back at the code:

> **TICKET #2, Observable behavior 4** *(written by the adversary at 10:46:55)*: "Because locking creates a sidecar (behavior 5), both `View` and `Update` require a **writable directory** — a read-only directory yields a clear error, never a silent empty read."

Second finding: `golangci-lint run` is not clean — 18 errcheck findings across `store.go`,
`lock_unix.go`, `main.go`.

**Trace it all the way back — this is the payoff of the entire grill:**

| Time | Event |
|---|---|
| 10:18:41 | Ian overrides "defer" → locking exists at all |
| 10:19:44 | flock chosen, on the store file |
| 10:39:12 | adversary: flock + rename = orphaned lock → move it to a sidecar |
| 10:46:55 | adversary round 2, finding **N4**: *"sidecar locking makes every read require a writable directory; stated nowhere"* → becomes Observable behavior 4 |
| **11:55:55** | **the implementing agent violates behavior 4 — the exact failure class the ticket was amended to forbid, 69 minutes later** |

A requirement written by an adversary at 10:46 catches an implementation bug at 11:55 that no test
in the tree covered.

Note also the fix instruction sent to the agent at `[266]` — it does not merely name the bug, it
hands over the reproduction and demands the agent run it:

> **SLOPSTOP SAYS** *(to the fleet agent)*: "Verified live by the adversary: `View` on a missing store path inside a `0500` directory returned `map[] err=<nil>` — **reproduce this yourself before and after your fix.**"

---

<a id="no-op"></a>
### 11:58:31 `[290]` — **The no-op. A capability failure, not a code failure.**

> **SLOPSTOP SAYS:** "Attempt 2 produced nothing — the agent printed *'Waiting for slopstop-start to complete...'* instead of actually invoking the `Skill` tool, exited clean, no commits, no ticket comment. This is the exact **'slash text is inert'** failure mode already documented as a known Haiku-tier scar in `run-agent-brief.md`. No new work to verify."

**Why interesting:** the weak model did not write bad code. It *narrated* doing the work and exited
0. A CI-shaped check sees a clean exit and a green tree. Only "did the tip move / did a comment
appear" catches this.

This particular mode is a headless-CLI artifact — an agent that printed a slash command as text
instead of invoking a tool. Worker agents return a report or return `BLOCKED`, so there is no
exit code to misread. But the lesson generalizes past its mechanism and is worth carrying: **a
clean exit is not evidence of work.** Look at whether the artifact moved.

---

### 11:59:40 `[320]` — The escalation ladder, stated plainly

> **SLOPSTOP SAYS:** "attempt 1 failed handoff verification on two real findings, attempt 2 was a no-op from the weak model, and **attempt 3 is now running on sonnet-5 with both sets of findings**."

Diagnosis recorded as `capability-gap`; the escalation and its trigger are posted to the issue.

Note the discipline at **12:15:49** `[521]` when KV-4 hits the identical no-op:

> **SLOPSTOP SAYS:** "Relaunching attempt 2 — **still on haiku per the budget rules — escalation only kicks in after 2 failed attempts**."

One failure is not evidence. The rule is not bent for a hunch, even when the orchestrator has just
seen this precise failure mode an hour earlier.

**The ladder is gone; the diagnosis it encoded is not.** v4 has no attempt counter and no
automatic escalation. What it keeps is the question the ladder was asking — *is this a code
problem or a ticket problem?* — and it answers it in one place: a ticket that fails
implementation twice is stopped with a recommendation to run `/slopstop:tickets --rewrite`, which
re-authors the ticket against the specific failure and will not let the rewrite subtract scope.

---

### 12:05:46 `[349]` — **Frozen tests changed. What happens next is the interesting part.**

The attempt-3 fix commit touched both frozen files. Classification:

> **SLOPSTOP SAYS:** "every change to the two frozen files is a mechanical `X` → `_ = X` errcheck discard (both `os.Setenv`/`os.Unsetenv` in `resolve_test.go` and `f.Close()` in `store_test.go`) plus one wholly-new test appended to `store_test.go`. No assertion values changed, nothing skipped or removed. **This is defensible — the agent disclosed it proactively rather than hiding it — but I want the fresh subagents to independently confirm that read before I trust it.**"

**Why this is the best-formed judgment in the run:** a defensible edit plus proactive disclosure
still does not buy trust. It buys a second opinion. The instruction to the verifiers at `[350]` is
explicit — *"IMPORTANT — the fix commit touched the two FROZEN Phase-0 test files, which is exactly
the kind of thing Gate 0 exists to catch. Do NOT skip this."*

**12:10:22** `[358]`: both fresh subagents **PASS** on attempt 3. KV-2 blessed at `e6533a5`.

---

<a id="tamper-check"></a>
### 12:18:44 – 12:23:16 `[570]`,`[592]`,`[609]`,`[613]` — **The tamper investigation that ends in an acquittal**

KV-6 rewrote `isErrUsage`, a helper used by frozen test assertions, from:

```go
// Check if it's store.ErrUsage or wrapped in it
var m map[string]interface{}
if json.Unmarshal([]byte{}, &m) == store.ErrUsage {
    // This is just a way to check - we use the sentinel
}
// Actually, we need to check the error directly
return err == store.ErrUsage || (err != nil && err.Error() == store.ErrUsage.Error())
```

to:

```go
return errors.Is(err, store.ErrUsage)
```

At `[573]`:

> **SLOPSTOP SAYS:** "This one needs scrutiny before I trust it: `isErrUsage`, a helper used by frozen test assertions, was rewritten between the Phase-0 commit and tip — not a test assertion itself, but **exactly the kind of 'expected value lives in an edited helper' evasion Gate 0's adversary checklist calls out.**"

The instruction to the verifiers at `[592]` is the exemplary bit: it hands over the raw diff and
the command to reproduce it, and demands they re-derive the conclusion rather than accept the
framing. Both did — independently rebuilding the Phase-0 stub and tracing that `delete.go` returns
`store.ErrUsage` **bare, unwrapped**, so the old helper's surviving branch was already equivalent
`[609]`:

> **ADVERSARY:** "No expected value, assertion target, or test name changed… This does not constitute tampering under the ticket's 'changed expected value' bar."

Verdict posted publicly on the issue at `[613]`, with the reasoning, not just the outcome.

**Why interesting:** the tamper gate's value is not that it convicts. It is that a
suspicious-looking edit gets adjudicated on evidence, in public, and the acquittal is recorded.

This is the gate that has *least* changed, and deliberately so. Red-test tamper is mechanical: it
stops a ticket in either mode, at any change size, with no permissive setting anywhere in the
config. The reasoning is the same one that killed the old `[autonomous]` knobs — a gate whose
permissive value is the only one an unattended run can use has disabled itself for exactly the
agents it exists to police, and then reports clean.

---

### 12:42:40 `[830]` / 12:52:44 `[900]` — Bugs the test suite structurally could not find

- **12:42:40** — KV-9 attempt 1 FAIL: *"README overclaims that exit code 1 is exclusively for `get`'s key-not-found, when the code actually maps *any* non-`ErrUsage` error to exit 1."*
- **12:52:44** — three more, and the reason they survived:

> **SLOPSTOP SAYS:** "three README accuracy bugs the e2e test **structurally couldn't catch** (it happened to use alphabetically-ordered test keys)"

**Why interesting:** the suite is green and stays green through all of it. A test that accidentally
chose sorted keys can never distinguish "sorted output" from "insertion order" — and recall that
ordering was decided at **10:13:16**, Q6, in [§1](01-design-and-grill.md). Green ≠ correct,
demonstrated rather than asserted.

This is the class `vacuity-check` was later added to attack head-on: it re-runs each new test
against the code that predates the branch, and a test that was already green is reported
`vacuous` — a mechanical result, not a judgment anyone can argue with.

---

### 12:43:23 `[843]` — Fix-forward instead of blocking

The umbrella drift-check on #3 finds **vacuous test assertions in `set`** — filed as
[#17](https://github.com/iansmith/slopstop-multiagent-example/issues/17), *"rather than blocking
the run."*

**Why interesting:** a real defect found late, and the process neither hides it nor holds the run
hostage to it. Note what it is: a test that passes without asserting anything — precisely the slop
the whole apparatus exists to stop, caught by the *last* check rather than the first.

Two things moved since. The check now runs earlier and mechanically, per ticket, at stage 9 —
`vacuity-check` proving vacuity by execution and `slop-check` catching by reading the tests it
cannot even collect. And the escape valve is narrower: a vacuity verdict stops that ticket
outright rather than being filed onward, while everything not depending on it keeps running.
Filing forward remains the right answer for a defect found *outside* a gate; it is not a way past
one.

---

## Section summary — the ledger

| Ticket | Attempts | What happened | Verdict |
|---|---|---|---|
| #2 Foundation | 3/3 + 1 zero-cost | orchestrator config bug (uncharged) → real work, FAIL on 2 findings → no-op → **escalated to sonnet-5**, PASS | merged |
| #4 set | 2/3 | no-op → PASS | merged |
| #5 get | 1/3 | PASS | merged |
| #6 delete | 1/3 | PASS, `isErrUsage` scrutinized, benign | merged |
| #7 list | 1/3 | PASS | merged |
| #8 export | 1/3 | PASS | merged |
| #9 Integration | 2/3 | README accuracy FAIL → PASS | merged |

Two distinct failure classes, and they want different responses:

- **Real defects** (#2's `View` bug, #9's README) — feed the findings back and retry.
- **Capability failures** (the no-ops) — the agent could not do the work at all; more of the same
  is wasted effort.

That distinction is the durable finding of this section, and it is what v4 kept when it dropped
the attempt counter that measured it: repeated failure on the same ticket is a signal about the
*ticket or the tier*, not a budget to spend down.

Deviations logged for the upstream report, and where they landed:

- Partial/missing tracking-dir writes on KV-5/6/7/8 — **fixed by construction.** The orchestrator
  is now the sole writer of the tracking dir and of `run.jsonl`; no worker resolves a path or
  writes a file, so there is no second writer to be partial.
- Inconsistent PR-decline behavior — folded into `:run`'s single inline PR stage.
- Inconsistent GitHub auto-closing (three PR bodies happened to contain `Closes #N`, two did not)
  — now an explicit rule: closure happens through the API at stage 14, and a closing keyword in a
  PR body is forbidden because it races that step and skips the label half of it.

---

[← 3. The handoff](03-handoff-and-gates.md) · **4. Fleet execution** · [5. The report adversary →](05-report-adversary.md) · [Index](README.md)
