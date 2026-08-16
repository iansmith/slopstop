# The mechanical gates

[Index](README.md) · prev: [Before any code exists](01-before-the-code.md) · next: [Integrity and review](03-integrity-and-review.md)

Stage 9 runs three gates against the finished branch. They share one property that separates them
from every other check in the pipeline: **they execute something and report a number.** They form
no opinion, they fix nothing, and they have no permissive setting — there is no flag that makes a
gate softer because the change looked small or because nobody is watching.

That last part is a design commitment rather than a nice-to-have. A gate that softens for the
cases it exists to police is worse than having no gate, because it reports clean.

---

## 3. The gate that refused to report a pass — on a measurement it couldn't complete

**The check:** `vacuity-check`. It takes each test by node-id, checks out the commit the branch
was cut from into a throwaway worktree, and *runs the test there*. A test that already passed
against the pre-branch code pins nothing — it is the most dangerous kind of green, because it
looks like coverage. This is not a judgment call: the test either failed at base or it didn't.

**The ticket:** AATK-87, a root-process error contract. The gate's first attempt:

```
GATE 2 of 3, ATTEMPT 1 — NOT A PASS. vacuity-check returned `VACUITY VACUOUS: 0` but with
5 of 7 node-ids `could-not-determine`, which stage 9 says is reported as itself and never
rounded to a pass. Only the 2 internal/observe node-ids ran; both are `meaningful` (each
failed AT ITS ASSERTION against base, with the assertion text quoted as evidence, not
merely exiting non-zero). The other 5 all live in package cmd/aa-server-status and died
identically on a package-wide BUILD failure, so none reached its assertion and none can be
read either way. Cause is TWO BAD ARGUMENTS FROM THE ORCHESTRATOR, both verified
independently against git rather than taken from the worker's word: (1) --frozen 4ba3ece
does not carry `observe.NewProcessHook` […] so the seam the cmd/aa-server-status gap tests
need appears TWO Phase-0 commits after the declared $FROZEN; (2)
`cmd/aa-server-status/engine_helper_test.go` is a CHANGED test file on this branch […]
```

`VACUITY VACUOUS: 0` reads like a pass. Zero vacuous tests. It is not a pass, and the gate said
so: five of seven tests never reached an assertion, so five of seven results mean nothing. Rerun
with corrected arguments:

```
GATE 2 of 3, ATTEMPT 2 (corrected inputs) — VACUITY VACUOUS: 2. STOPS THE TICKET. […] All 5
previously could-not-determine node-ids built and ran. ZERO could-not-determine this run —
the incomplete-baseline problem is fully resolved, so this verdict is a real measurement
rather than an artifact. RESULT: 5 of 7 meaningful, each with its actual assertion text
quoted as evidence (not merely a non-zero exit) […] 2 VACUOUS, both tagged
`non-interference`
```

**Why this matters.** Three separate things went right here, and only one of them is about the
tests.

The gate distinguished *"I measured, and found nothing"* from *"I could not measure."* Collapsing
those two into one green result is the single most common way an automated check becomes
decorative. `could-not-determine` is a first-class verdict precisely so it cannot be rounded off.

The gate caught the **orchestrator's** error, not the implementer's. The bad `--frozen` sha and
the missing test file were the orchestrator's arguments. A worker that had trusted its inputs
would have reported a clean pass on a broken measurement, and the run would have proceeded on it.

And the corrected run then found two genuinely vacuous tests — which is what would have shipped
unnoticed had attempt 1 been accepted.

---

## 4. One function got worse. The other 170 violations were not this ticket's problem

**The check:** `complexity-check`. It runs `lizard` over the branch diff, compares each function's
cyclomatic complexity against its complexity at the base commit, and classifies against configured
warn/reject thresholds. The critical rule is the **did-not-get-worse exemption**: a function that
already breached the threshold and did not get worse is exempt. A gate that fails every branch
touching a legacy file trains people to ignore it.

**The ticket:** AATK-82, adding a client-event send path. The gate's verdict:

```
complexity-check returned: CC VIOLATIONS: 1 (reject) + 2 (warn). REJECT:
telephony/twilio/realtime.go:324 HandleStreamRealtime CC=10 (base=7, worsened -- not
exempt, cc_exempt_pre_existing only covers did-not-get-worse). WARN:
telephony/realtime/client.go:36 Dial CC=8 (base=7, worsened);
telephony/twilio/realtime.go:527 pumpCarrierToBridge CC=7 (base=7, pre-existing,
exempt-eligible if it stayed flat -- unchanged, not a new breach). No file NLOC violations.
This is a reject-threshold stop per process, but the CC-reduction protocol says attempt a
real one-pass refactor around existing seams first, re-measure once, and only escalate
after genuine effort.
```

Note the arithmetic being done per function: `CC=10 (base=7, worsened)` blocks; `CC=7 (base=7,
pre-existing)` does not. The gate is measuring the *delta this ticket caused*, not the absolute
state of the codebase.

Then the protocol ran, and the gate re-measured rather than being talked past:

```
CC re-run at aeaf17d: 0 reject-level violations (was 1). HandleStreamRealtime CC=9 (below
reject=10), handleClientEvent CC=3. Two pre-existing warn-level elevations remain […] both
under threshold, not blocking […] All three stage-9 gates now clean: SLOP CLEAN, VACUITY
CLEAN, CC CLEAN (0 reject).
```

**Why this matters.** The alternative designs both fail. A gate on absolute complexity fires on
every branch that touches an old file, and gets waived until nobody reads it. A gate with a
"skip complexity" flag gets set once during a deadline and never unset.

Measuring the delta means the gate is silent about inherited debt and loud about *new* debt —
which is the only version of the rule a team will still be honouring in six months. On a sibling
ticket in a different repo the same gate reported 171 red functions, correctly identified that
170 were in generated code that is forbidden to hand-edit, and blocked on the one that was
genuinely new. Signal and noise, separated mechanically.

The other half of this is that the gate blocked and the run did the work, rather than escalating
immediately. `HandleStreamRealtime` went from 10 to 9 by extracting `handleClientEvent` — a real
decomposition, re-measured once, not a threshold edit.

---

Next: **[Integrity and review](03-integrity-and-review.md)** — proving the tests weren't gamed,
and what happens when a reviewer is allowed to keep going.
