[← 3. The handoff](03-handoff-and-gates.md) · **4. Fleet execution** · [5. The report adversary →](05-report-adversary.md) · [Index](README.md)

---

# 4. Fleet execution

**11:08:32 – 12:52:44 · `claude-sonnet-5` orchestrator, `claude-haiku-4-5` fleet · tier gate PASS**
Source: Transcript B, turns cited as `[n]`. Notation key: [index §3](README.md#3-notation).

Nine tickets, three waves, seven merged branches. Along the way: a launch bug that costs nothing,
a failed attempt, a no-op, a model escalation, and two investigations into edited test files.

> Reminder from [§3](03-handoff-and-gates.md): the fleet runs on the **small tier by deliberate
> choice**, so that the kill and rewrite machinery has something real to catch. The failures below
> are the instrument working.

---

### 11:11:09 `[76]` — The wave plan, and a consent gate before anything becomes public

> **SLOPSTOP SAYS:**
> **Wave 1** (solo): #2 Foundation — blocks everything.
> **Wave 2** (parallel once #2 lands): #4 set, #5 get, #6 delete, #7 list, #8 export — disjoint file maps.
> **Wave 3** (solo fan-in): #9 Integration — after all of #4–#8 land.

**Caused by:** Q2 at **10:09:48** in [§1](01-design-and-grill.md). This *is* that answer, executed.

Each agent launches as a headless `claude -p` background session with
`--allowedTools Bash(gh:*) Bash(git:*) Bash(go:*) Bash(golangci-lint:*) Bash(gofmt:*)`, creates a
worktree and branch, pushes commits, and posts progress comments on its own GitHub issue.

And it stops before acting on the outside world:

> **GATE:** "Before I fire Step 4 and start pushing real branches/comments to that **public** repo: confirm I should launch the fleet now, starting with #2?"

---

### 11:2x – 11:40:30 `[225]` — Three nested blockers, and a zero-cost accounting decision

1. First launch fails. Diagnosis: `--permission-mode auto` does not auto-approve the agent's **own `Write` tool**; `acceptEdits` does.
2. Second blocker: the orchestrator's *own* classifier will not let it launch a subprocess with `acceptEdits`.
3. At **11:36:21** `[186]` Ian asks for the permission rule; it adds `Bash(claude -p *)` to `~/.claude/settings.json` — **global scope, Ian's choice, after confirming**.
4. Relaunch — and the accounting call:

> **SLOPSTOP SAYS:** "**no attempt consumed** for the first failed launch since it was an **orchestrator bug, not a ticket/agent defect**."

**Why interesting:** the attempt budget is what eventually escalates a model tier and eventually
gives up. Charging a ticket for the orchestrator's own bug would corrupt every downstream decision.
This exact distinction gets re-litigated by the adversary at 13:03 in
[§5](05-report-adversary.md) — and the ledger turns out to have been right while the prose was wrong.

Both drift findings so far (this one and the `branch_type` doc contradiction from
[§3](03-handoff-and-gates.md)) are logged in `fleet-state.md` for the eventual upstream report.

---

### 11:52:34 `[252]` — Gate 0 passes, and the verification still runs

> **SLOPSTOP SAYS:** "Gate 0 (red-test tamper check) passes mechanically — the frozen test files (`store_test.go`, `resolve_test.go`) show **zero diff** between the Phase 0 commit and the branch tip. Now spawning the two fresh handoff-verification subagents (requirements adversary + code reviewer) **in parallel**."

**Why interesting:** a clean tamper check is not a pass. Two fresh readers with no conversation
history are spawned anyway, and they are what find the next thing.

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
appear" catches this. That is 2 failed attempts → Step 7 **diagnosis fork**.

---

### 11:59:40 `[320]` — The escalation ladder, stated plainly

> **SLOPSTOP SAYS:** "attempt 1 failed handoff verification on two real findings, attempt 2 was a no-op from the weak model, and **attempt 3 is now running on sonnet-5 with both sets of findings**."

Diagnosis recorded as `capability-gap`; the escalation and its trigger are posted to the issue.

Note the discipline at **12:15:49** `[521]` when KV-4 hits the identical no-op:

> **SLOPSTOP SAYS:** "Relaunching attempt 2 — **still on haiku per the budget rules — escalation only kicks in after 2 failed attempts**."

One failure is not evidence. The rule is not bent for a hunch, even when the orchestrator has just
seen this precise failure mode an hour earlier.

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
suspicious-looking edit gets adjudicated on evidence, in public, and the acquittal is recorded —
`PASS@ed29cf1 (isErrUsage cleanup scrutinized, benign)` carries into the ledger and every
downstream report.

---

### 12:42:40 `[830]` / 12:52:44 `[900]` — Bugs the test suite structurally could not find

- **12:42:40** — KV-9 attempt 1 FAIL: *"README overclaims that exit code 1 is exclusively for `get`'s key-not-found, when the code actually maps *any* non-`ErrUsage` error to exit 1."*
- **12:52:44** — three more, and the reason they survived:

> **SLOPSTOP SAYS:** "three README accuracy bugs the e2e test **structurally couldn't catch** (it happened to use alphabetically-ordered test keys)"

**Why interesting:** the suite is green and stays green through all of it. A test that accidentally
chose sorted keys can never distinguish "sorted output" from "insertion order" — and recall that
ordering was decided at **10:13:16**, Q6, in [§1](01-design-and-grill.md). Green ≠ correct,
demonstrated rather than asserted.

---

### 12:43:23 `[843]` — Fix-forward instead of blocking

The umbrella drift-check on #3 finds **vacuous test assertions in `set`** — filed as
[#17](https://github.com/iansmith/slopstop-multiagent-example/issues/17), *"rather than blocking
the run."*

**Why interesting:** a real defect found late, and the process neither hides it nor holds the run
hostage to it. Note what it is: a test that passes without asserting anything — precisely the slop
the whole apparatus exists to stop, caught by the *last* check rather than the first.

The same message states the gate that will close the run, 70 minutes early:

> **SLOPSTOP SAYS:** "that gate needs your explicit acceptance, so **I won't clean up the run directory without it**."

---

## Section summary — the fleet ledger

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

- **Real defects** (#2's `View` bug, #9's README) — feed the findings back, same tier, retry.
- **Capability failures** (the no-ops) — the model cannot invoke the tool at all; more attempts at that tier are wasted, so escalate after two.

Deviations logged for the upstream report: partial/missing tracking-dir writes on KV-5/6/7/8,
inconsistent PR-decline behavior, and inconsistent GitHub auto-closing (three PR bodies happened to
contain `Closes #N`, two did not).

---

[← 3. The handoff](03-handoff-and-gates.md) · **4. Fleet execution** · [5. The report adversary →](05-report-adversary.md) · [Index](README.md)
