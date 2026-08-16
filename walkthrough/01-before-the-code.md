# Before any code exists

[Index](README.md) · next: [The mechanical gates](02-the-mechanical-gates.md)

Two checks run while the implementation is still a stub. Both are cheap, both happen before a
line of production code is written, and both catch things that are enormously expensive to catch
later — because later means after someone has built the wrong thing and made it green.

---

## 1. The test suite proved the obvious implementation was wrong — before anyone wrote it

**The check:** `mutation-check` at stage 5. Stage 4 has just written tests that fail. This worker
asks a different question: do they fail *for the reason they claim*? An import error, a typo, or a
missing fixture also produces a red test, and a red test that is red for the wrong reason pins
nothing. So the worker mutates things — applies a probe that should make a test pass, applies
another that should push it back to red — and reports whether each test actually tracks the
behaviour it names.

**The ticket:** AATK-85, adding declared tools and a function-call round trip to a realtime
session handshake. The frozen tests required the tool declaration to reach the wire *unmodified*.

```
FINDING THAT MUST REACH THE IMPLEMENTER, and it is the most valuable thing this round
produced. The obvious implementation FAILS. Adding Tools json.RawMessage to sessionSpec
with a json:'tools,omitempty' tag and letting the existing c.send() marshal it does NOT
satisfy the declaration tests, because encoding/json HTML-ESCAPES < > & to < >
& and COMPACTS insignificant whitespace even inside a json.RawMessage field embedded
in a larger struct. Verified directly by the worker, not reasoned: that implementation
produced '"description":"<desc>&more"' and collapsed '"type":  "function"'
to '"type":"function"', and both declaration tests correctly failed against it. Only
splicing the raw tool bytes into the marshalled output AFTER json.Marshal satisfies them.
```

**Why this matters.** The idiomatic Go implementation — a struct field with a JSON tag — is what
a competent engineer writes, and it is wrong here in a way that is nearly invisible: the payload
looks correct in a log, parses correctly as JSON, and differs from the required bytes only in
escaping and whitespace. It would have been shipped believing it correct.

Two things made this catchable. First, the contract was written down as an executable test
*before* the implementation existed, so there was something to test the obvious approach against.
Second, the check didn't reason about the test — it built the near-miss implementation and ran it.
The worker's own note is careful about this distinction: *"Verified directly by the worker, not
reasoned."*

The orchestrator recorded the second-order consequence too, which is the part most processes drop:

```
TWO CONSEQUENCES. First, this is strong evidence FOR these tests: they catch a very
plausible near-miss that a reasonable implementer would ship believing it correct […]
Second, it makes the CONTRACT unusually demanding -- byte-for-byte whitespace preservation
inside the handshake -- and forces a splice-based implementation rather than an idiomatic
struct field. That is a design consequence the frozen tests have now fixed, and whether it
is the RIGHT contract is a question for stage 7's adversary […]
```

A test-first process constrains the design, and that is a cost as well as a benefit. This run
noticed it was paying the cost, said so, and routed the question to the stage that is chartered to
rule on it.

---

## 2. Two bugs that only the adversary's tests could see — and the proof is a number

**The check:** the stage-7 `adversary` loop. A fresh agent attacks the frozen test set against
the ticket's stated goals, with no access to the conversation that wrote them, looking for
behaviours the ticket requires that no test covers. Findings become new gap tests, which are
themselves proven red before being committed. It runs up to three rounds.

The obvious objection to this stage is that it is expensive theatre — more agents finding more
things to add, with no evidence any of it matters. AATK-93 produced the measurement that answers
it.

**The ticket:** AATK-93, refusing `session.update` messages on a client-event channel. Adversary
round 2 demanded a test that the refusal must not reset the idle timer. Round 3 demanded a test
that the refusal must happen on the *resolver* path specifically, not merely somewhere.

Later, at stage 9, the pinning pass mutated the branch's own production code eleven different
ways to see which mutations the suite would catch:

```
MUTATION CHECK PINNED: 11 of 11. Converged in one round, no fix round needed. Eleven
distinct subtractive mutations of the branch's own production decisions, every one killed:
equality operator across three variants (HasPrefix, Contains, inverted !=), the compared
constant, the refusal's PLACEMENT, the return (ch,nil) path, the log call removed, log
cardinality via sync.Once, the parse-failure fall-through across two variants […] No
mutation survived. TWO RESULTS VINDICATE THE ADVERSARY ROUNDS EXACTLY: the wrong-placement
mutation - refusal moved into the WithClientEventChan constructor, bypassing the resolver -
was killed by TestClientEventChanFor_SessionUpdateRefusedOnResolverPath and NOTHING ELSE;
and the idle.reset mutation was killed by
TestClientEventChan_SessionUpdateRefusalDoesNotResetIdleTimer and NOTHING ELSE. Both tests
exist only because adversary rounds 3 and 2 respectively demanded them; without those
rounds both mutations would have survived a fully green suite.
```

**Why this matters.** Two of eleven realistic bugs — a refusal wired at the wrong layer, and a
refusal that silently kept a connection alive — were invisible to every test that would have
existed without the adversary. Not "might have been"; the mutation ran, the suite stayed green
everywhere else, and exactly one test went red in each case.

This is also the shape of evidence worth demanding from any process that claims to improve
quality. The claim "the adversary found gaps" is unfalsifiable. The claim "these two specific
mutations were killed by these two specific tests and by nothing else in the suite" is a
measurement, produced by a later stage that had no stake in defending the earlier one.

Worth noting what the same worker *declined* to do:

```
Probe E (generative) explicitly SKIPPED with a stated reason rather than silently omitted:
this ticket makes no enumeration claim - it refuses one named type by exact equality, so
there is no enumerated set for a generative mutation to add an uncovered instance of.
```

A skipped check that says it was skipped and why is a check you can audit. A skipped check that
quietly reports clean is the failure mode the whole design exists to prevent.

---

Next: **[The mechanical gates](02-the-mechanical-gates.md)** — two checks that execute something
and report a number, including one that caught the orchestrator itself.
