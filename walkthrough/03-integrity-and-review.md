# Integrity and review

[Index](README.md) · prev: [The mechanical gates](02-the-mechanical-gates.md)

The last two checks answer the two questions that remain once a branch is green and the gates
have passed: **were the tests gamed?** and **is the code actually right?**

---

## 5. Removed lines in a frozen test file — and the commit-by-commit proof of who removed them

**The check:** the tamper gate, run at stage 8a and again at 10b. Stage 6 records `$FROZEN`, the
commit holding the phase-0 tests. The gate diffs the frozen test files from `$FROZEN` to the
branch tip. The rule it enforces is narrow and specific: **the agent whose code has to satisfy
the tests may not weaken them.**

The naive version of this rule is "frozen tests never change", and it is wrong — it would forbid
the adversary loop from adding gap tests, and forbid the pinning pass from strengthening a test
that mutation-check found unpinned. Both of those are the process working. So the gate does not
enforce immutability. It enforces **attribution**.

**The ticket:** AATK-82. The gate found removed lines in a frozen file:

```
TAMPER CLEAN (re-checked at current tip aeaf17d4211f6b61e5cae0f4223abbeacab57237); FILEMAP
CLEAN. Two comparisons, both reported for transparency: (1) literal $FROZEN=afe6d4f..TIP
over the frozen set shows removed lines in
telephony/twilio/realtime_clientevents_test.go -- every one traces to the three
adversary-round commits (6dfc2db, 31c0e47, 670abc6), zero to implement (2e2a4c1) or the
CC-reduction commit (aeaf17d), confirmed via `git log afe6d4f..aeaf17d -- <file>` naming
exactly those three and no others. (2) The implement-scoped comparison (670abc6..aeaf17d,
i.e. from the LAST Phase-0 authoring commit to the current tip) is unambiguously clean:
zero removed lines in either frozen test file. The classification rule's actor is 'the
model whose code had to satisfy the tests' (implement) -- that model touched no test file
at all, at either the original implement commit or the CC-fix.
```

**Why this matters.** "Tests were modified" is not by itself a finding. The question that
matters is *by whom, and when relative to the implementation*. The gate answered it by naming the
three commits responsible, naming the two commits that were not, and running a second scoped
comparison that isolates exactly the window in which tampering would be meaningful.

This is the difference between a check that produces an alarm and a check that produces an
answer. An alarm on every modified test file gets muted within a week. An attribution that says
*"all removals predate implementation, implement touched no test file at all, here are the shas"*
is something a reviewer can actually act on — and it stays useful precisely because it does not
fire on the legitimate cases.

The same gate on a sibling ticket recorded `$FROZEN` moving seven separate times across a run,
each move logged with the reason and the authorizing decision. The record is not "the tests were
frozen." The record is every change to them, with a cause attached to each.

---

## 6. A bug, then the same bug beneath its own fix, then no coverage for either

**The check:** the stage-10 `review` loop. A worker reviews the diff in a context that never saw
the conversation that wrote the code, applies what survives its own verification, and returns a
verdict. The caller re-launches a *fresh* reviewer until one reports clean, up to five rounds —
then stage 10b does it again with independent checkers at the tier above, bound to the branch tip
sha.

**The ticket:** AATK-82. The reviewer took eight rounds. Rounds 2, 3 and 4 are one continuous
story and are the best argument in this document for not stopping at the first clean-looking pass.

**Round 2** found a real bug:

```
Applied: major/behavioural -- handleClientEvent passed the call-wide context to
client.Send, so a blocking websocket write (backend stops reading, buffers fill) parked the
whole select loop, silencing backendDone/carrierDone/idle-timeout simultaneously -- the
exact condition WithIdleTimeout exists to guard against, defeated by it. Mutation-proven
live: probe with a deliberately-blocking transport hung indefinitely before the fix (still
hung at 12s), ended in 5.0s with a deadline-exceeded error after […] Fix: bounded the write
with a new realtimeClientEventSendTimeout (5s) constant
```

**Round 3** — a different agent, reviewing the fixed code — found the same bug one layer down:

```
A deeper layer of round 2's own bug: writeMu was a plain sync.Mutex, so round 2's
context-bounded Send call still parked UNCANCELLABLY waiting to ACQUIRE the lock if
AppendAudio already held it against a stalled backend -- the exact select-loop wedge round
2 believed it had fixed, one level down. Mutation-proven end-to-end: before, loop still
parked at 20s with a 2s idle timeout configured, never logged the failure; after, unparks
at 5.05s with an attributable error. Mechanism cross-checked against coder/websocket's OWN
internal lock (conn.go:286, write.go:289) which IS already context-aware -- this Client's
home-grown mutex sat in front of it and voided that property.
```

**Round 4** then asked whether the two fixes were themselves protected:

```
Found rounds 2 and 3's fixes (the send timeout, the ctx-aware write-slot semaphore) had
ZERO regression coverage -- reverting either to its pre-fix form left the entire suite green
under -race, a silent-regression risk on the exact bugs review itself just found and fixed.
Added two new white-box tests […] both mutation-proven red against the reverted code and
green against the fix; a control mutation (marshal-path revert) killed 7 tests,
establishing the suite genuinely watches this code.
```

And **round 6**, still in the same area, found an unrelated ordering bug with a measured failure
rate:

```
newIdleGuard was armed BEFORE cfg.clientEventChan(start) was resolved, so a slow consumer
resolver ate the guard's first window; a call whose backend was actively streaming the whole
time could still end with a bogus 'idle timeout' […] Mutation-proven with actual failure
rate: 6/10 calls died spuriously with the bug (500ms timeout, 1.2s resolver sleep, active
backend), 0/10 after moving resolution above arming.
```

**Why this matters.** Round 2's fix was correct, and insufficient, and looked complete. A process
that stops at the first plausible fix ships it. What caught the deeper layer was not a smarter
reviewer — it was a *fresh* one, with no investment in round 2's reasoning, looking at round 2's
output as just more code to attack.

Round 4 is the subtler point. The pipeline turned its own findings into permanent test coverage.
Two real concurrency bugs had been found and fixed, and reverting either fix left the suite fully
green — so the next refactor could have silently reintroduced both. The reviewer treated its own
prior fixes as unproven until pinned, and proved the pins by mutation.

Every one of these was verified before it was believed. Round 3 checked its mechanism claim
against the upstream library's source rather than asserting it. Round 6 reported `6/10` and
`0/10`, not "this seems racy." Across the eight rounds the reviewer also refuted roughly 40
candidate findings with stated reasoning — including a specific deadlock hypothesis it traced and
found no cycle for. The discipline is symmetric: nothing is applied on suspicion, and nothing is
dismissed on convenience.

The convergence signal is visible in the severities: blocker and major in rounds 2–4, minor by
rounds 5–7, then:

```
REVIEW CLEAN | reported 0 (blocker 0, major 0, minor 0). Full, serious pass, not a rubber
stamp -- re-verified every dependency claim in every new comment against the actual
coder/websocket source, confirmed writeFramePayload does not mutate the caller's slice,
traced the full lock order (writeSem -> msgWriter.mu -> writeFrameMu) with no inversions
found anywhere […] Stressed the new tests at -count=5/-count=10, no flakes. CONVERGED.
```

---

[Index](README.md)
