---
description: Write the phase-0 failing tests that define a ticket's contract before any implementation exists, run them, and return the test files, node-ids, test command, and the observed failure output proving they are red.
---

# Phase 0 — write the red tests

You are a worker agent with **no prior conversation**. Everything arrives in your prompt:
the repository path, the ticket key, its original description, and its Definition of Done.
If any is missing, report `RED-TESTS BLOCKED: <what is missing>` and stop — do not guess a
ticket or infer a DoD from the code.

Write tests that describe the **expected** behavior and **fail on current code**. Do not
implement the behavior, do not commit, and do not write `task_plan.md`, `findings.md`, or
anything under a tracking directory — the orchestrator owns those.


## If you were invoked without inputs, stop

You are a worker, not a command. You are launched by an orchestrator that hands you
everything below. If you find yourself running with no ticket and no plan — a stray
invocation rather than a launch — report `RED-TESTS BLOCKED: invoked with no inputs` and stop.
**Do not go looking for work to do.** Do not scan the repo for something plausible, do not
pick up the current branch, and do not infer a ticket from git state.

## Step 1 — Decide whether Phase 0 applies

**A change that alters only documentation prose gets no red tests.** A test asserting an
English sentence appears in a markdown file pins *wording*, not behavior: it cannot fail
for a reason review would miss, and every later legitimate reword turns the suite red. The
exception is narrow — **structural invariants a human cannot check by reading**: a mirrored
file matching its reference byte-for-byte, a derivation still present in the script
implementing a gate, a file existing where a manifest says it does. Test those.

If the ticket is prose-only, write no tests and return `PHASE 0: none — prose-only change`
with a one-paragraph justification. Do not manufacture tests to look productive.

**A refactor ticket gets no red tests either.** If you were launched with `--refactor`,
return `PHASE 0: none — refactor` immediately and write nothing. Judge this from the flag
alone — mode lives in the ticket's `slopstop-refactor` label, the orchestrator resolves it at
intake, and a worker re-deriving it from the body would be reading a source that no longer
carries the answer. A refactor adds no behaviour, so
there is no contract for a new test to describe; its guard is the **existing** suite, run by
`implement` before and after, and a test you invented here would be a new contract smuggled
into a ticket whose whole claim is that nothing changed. In the normal case the orchestrator
does not launch you at all for such a ticket — this rule is what makes a stray launch harmless
rather than productive-looking.

### `--backfill` — you write tests, and they must come up GREEN

A **backfill** ticket covers behaviour that already works. You are launched normally and you
write real tests — Steps 2, 4 and 7 apply unchanged — but **the expected outcome is
inverted**, and this is the one place in this skill where a passing test is the success
condition:

- **Every test you write must pass on current code.** That is not a failure to make it red;
  it is the deliverable. Do not rewrite it until it fails, and do not reach for
  `TICKET UNDERSPECIFIED` because you cannot make it red.
- **Write no stubs.** Step 5 does not apply: the surface exists, or the ticket is in the
  wrong mode.
- **A test that comes up RED is a stop.** It describes behaviour that does not yet exist,
  which means this is a normal ticket wearing backfill's marker. Report
  `PHASE 0: BLOCKED — red under --backfill: <node-ids>` and stop. **Never edit the production
  code to make it green** — that is implementing a feature inside a ticket that has no red
  test and no implementer, and it is the single worst thing you can do on this path.
- **You still do not vouch for the tests.** A test that passes proves nothing on its own —
  `assert True` passes. `mutation-check --backfill` is what establishes that yours are
  pinned to real behaviour, and it is the gate this mode turns on. Write tests that break
  when the behaviour breaks, and give it something to work with: report `--targets`, the
  production files each test is meant to pin, because that is what it mutates.

Report `PHASE 0: green — backfill` with the node-ids, the test command, and — in place of
the failure output — **one line per node-id naming the production behaviour it pins**.

## Step 2 — Resolve the test command

Use the command given in your prompt if there is one. Otherwise auto-detect from the
repository root:

| Indicator | Test command |
|---|---|
| `Taskfile.yml` with a `test:` task | `task test` |
| `Makefile` with a `test:` target | `make test` |
| `package.json` with a `"test"` script + `pnpm-lock.yaml` | `pnpm test` |
| `package.json` with a `"test"` script + `yarn.lock` | `yarn test` |
| `package.json` with a `"test"` script (else) | `npm test` |
| `Cargo.toml` | `cargo test` |
| `go.mod` | `go test ./...` |
| `pyproject.toml` with pytest config | `pytest` |

The lockfile discriminator only matters once a `package.json` already has a `"test"` script.
If nothing matches, or several plausibly do, stop with `RED-TESTS BLOCKED: cannot resolve
test command`, listing what you found.

**Never pipe a run you must classify through `tail` or `head`** — truncation can drop the
very failure you are reporting. Redirect the full output to a scratch file and read it
back — `( eval "$TEST_CMD" ) > /tmp/red-tests-<ticket>.output 2>&1` followed by `STATUS=$?`
on the very next line, since the exit code is not in the text.

## Step 3 — Record the regression baseline

Run the existing suite **before writing anything**: record `N passing, M failing, K errors`
and list pre-existing failures by node-id. Downstream commit gates compare against this, so
capture it on untouched code.

## Step 4 — Write the tests

Follow the layout, framework, and fixtures of the existing tests. Derive expected behaviors
from the ticket description and DoD, transcribing any test expectations the ticket states
explicitly. Write in this priority order — most commonly missed first:

1. **Edge / boundary** — empty input, zero, max, off-by-one, empty collections, missing
   optional fields. At least two per new behavior.
2. **Error / rejection** — invalid input, conflicting state, out-of-order operations,
   missing required values. Every error condition the ticket names gets a test asserting
   the specific error or early-exit.
3. **Cross-feature interaction** — push data that existing features already handle through
   the new code path, so the new behavior cannot shadow or break existing handling.
4. **Happy path** — one or two. Easiest to write; do not over-index on it.

Every test needs a clear name and must actually exercise the behavior. **No stub tests** —
one that asserts nothing, or only what it itself just set up. No skipped tests, no `xfail`,
no commented-out assertions. If the ticket's expected value is contradictory or unknowable,
stop with `TICKET UNDERSPECIFIED: <what cannot be pinned down>` rather than writing a test
you cannot justify.

### Your assertions will be mutation-tested

**Every assertion you write is checked by perturbing the production code and requiring your
test to fail.** That is `mutation-check` at stage 5, on the stubs you leave behind, and again
at stage 9 against the real implementation. **An assertion that survives a mutation of the
behaviour it names is not pinning that behaviour, whatever the test is called.**

So the question to ask of each assertion is not *"does this fail right now"* — it does, or
you would not be returning it — but ***"which single change to the production code would make
this pass, and is that change the behaviour the ticket asked for?"*** If more than one answer
fits, the assertion is loose.

That is not a hypothetical failure mode. A real one, caught at the tier above after the code
was written:

> `TestHandleVoiceStream_RealtimeDialFailureEndsCallWithinDialTimeout` only asserts
> `err != nil`, and **the default path ALSO returns non-nil**

The name says dial-failure-within-timeout. The assertion says *something went wrong*. It was
weak the moment it was written, and it survived stage 5 and three adversary rounds because
nothing it was checked against could tell the difference. `err != nil`, `is not None`,
`len(x) > 0`, `assertTrue(result)` — these pass against implementations that are wrong in
exactly the way the test exists to prevent.

**This is bounded by the ticket, and the bound is not a formality.** Pin the expected values
*the ticket states*, at the boundaries *the ticket names*. An assertion the ticket does not
call for is out of scope **even when it would strengthen the suite** — stage 10b hunts for
things in the worktree that are not in the ticket, so Phase 0 grown past its contract trades
one finding class for another. Tightening an assertion the ticket asked for is always in
scope; adding a behaviour it did not is never.

**Under `--backfill` this reads differently and you should know which situation you are in.**
There, your tests come up **green** and `mutation-check` is *the gate on the ticket*, not a
sanity check on redness — the whole question is whether your tests pin behaviour that already
works. A green test that no mutation can break is the entire failure mode of that mode, so
the paragraph above is not advice there; it is the thing being measured.

## Step 4a — Tag every test with its category, as you write it

**Every test you write carries a category tag in its own source**, on the line immediately
above the test:

```go
// slopstop:test contract
// slopstop:test regression — guards: "With no option supplied, behaviour is byte-identical to today."
// slopstop:test non-interference — paired: asserts the consumer received all 50 events
```

Use the host language's ordinary line-comment marker; the token `slopstop:test` and the
category word are the fixed part. One tag per test function.

### The three categories

| tag | at Phase 0 | against base | must also carry |
|---|---|---|---|
| `contract` | **red** | fails | — |
| `regression` | green | **passes, by design** | what it guards, quoted |
| `non-interference` | **red** | fails | its positive pairing, named |

- **`contract`** — pins behaviour this ticket adds. The ordinary case, and the one that must
  fail at Phase 0 for the reasons Step 6 already gives.
- **`regression`** — guards behaviour that must **not** change: *"byte-identical to today"*,
  *"existing destinations unchanged"*, *"a concurrent second `Run` still returns the refusal
  error"*. Passing against pre-branch code is what it is *for*; a regression guard that failed
  against old code would not be a guard. Quote what it guards — a `regression` tag with nothing
  quoted is not a tag, and the quotation is the whole control.
- **`non-interference`** — a **negative property of the new behaviour**: "does not stall the
  audio", "does not trip the idle timer", "no goroutine outlives the call". **A do-nothing stub
  satisfies any purely negative assertion, and no sentinel can fail one** — so Step 5's
  "non-satisfying by construction" rule cannot be met, and the test is green at Phase 0 through
  no fault of the stub. Naming this category is what forces the fix: **the test must also
  assert something positive that an empty stub fails**, in the same test function. Name that
  pairing in the tag.

### A test you cannot categorize is a test in trouble — stop here

**This is the point of the step.** If a test fits none of the three, do not force it into
`contract` and do not leave it for a gate. Stop with
`RED-TESTS BLOCKED: uncategorizable test — <name>: <why none of the three fit>`.

Being unable to say what a test is *for*, while writing it, with the ticket in front of you, is
the cheapest signal available that something is wrong with it — and it is available now, not
eleven stages later. The categories are exhaustive over legitimate intents: a test that pins
nothing new, guards nothing existing, and constrains no property of the new behaviour is not a
test this ticket needs.

**Choose the tag while writing, not after running.** A tag picked to explain a result is a
rationalisation; the tag is fixed at `$FROZEN` with everything else at Phase 0 and cannot be
changed once a downstream gate has flagged something.

**Why this is worth the ceremony.** `vacuity-check` at stage 9 re-runs tests against pre-branch
code and reports every one that passes as `vacuous`. It is right about the fact and cannot know
the intent. Without the tag, a correct regression guard reads as slop and stops the ticket —
three hours and eleven stages after the moment it could have been resolved for nothing. On
AATK-81 that cost the run: six `vacuous` verdicts, of which two were correct regression guards,
three were unpaired negative assertions, and one was a test of a test helper that no category
fits (BILL-570).

## Step 5 — Add non-satisfying stubs when the surface does not exist

A test against a symbol that does not exist yet fails at **compile/import** and never
reaches its assertion — so it could assert something already true and still "fail". Add the
minimum production surface needed for the assertion to be reached.

**A stub is non-satisfying by construction.** It returns a **sentinel that reaches and
fails the assertion** — a value that cannot equal anything asserted. A zero value, empty
collection, or plausible default that might coincidentally satisfy an assertion is
forbidden. `panic("not implemented")` and `raise NotImplementedError` are **not** permitted
stub bodies: they fail without reaching the assertion — the same defect as the compile
error, under a different name. Keep stubs minimal; they are scaffolding for the implementer
to replace. Track every stub file path — you must report them.

## Step 6 — Run and classify

Run the resolved command. Four outcomes:

- **All new tests fail at their assertions** → RED established. Go to Step 7.
- **A test fails before reaching its assertion** (missing symbol, import or compile error)
  → **not yet red.** Go back to Step 5, add the stub, re-run.
- **A `contract` or `non-interference` test passes** → **not red.** For `contract`, the
  behavior already exists or the test is not exercising what the ticket describes — rewrite it
  until it fails. For `non-interference`, its positive pairing is missing or too weak to fail
  against an empty stub — strengthen the pairing (Step 4a). A test that passed here is **not**
  red and must never appear in your report as one. If the ticket's expectation is itself the
  wrong thing, take the `TICKET UNDERSPECIFIED` stop.
- **A `regression` test passes, and is supposed to** → expected; leave it alone. "Rewrite until
  it fails" is not merely hard here, it is *wrong*: a test asserting *"behaviour is
  byte-identical to today"* cannot be made to fail against today's code without asserting
  something false. Report it under its own heading, never as a red node-id.
- **The suite does not run** → stop with the captured error output verbatim.

Re-run the Step 3 baseline before reporting: a stub is real production surface and can
break an existing test, and unreported that breakage gets blamed on the wrong work later.
Then format the test files you wrote, so the downstream tamper gate never has to tell a
reformat from a rewrite. → `worker-launch.md`, "A worker that writes code formats what it
touched" — the project's own formatter, never a named one.

## Step 7 — Report

Return exactly this, and write it nowhere else:

```
PHASE 0: RED  (or: none — prose-only change / none — refactor / green — backfill
               / BLOCKED / TICKET UNDERSPECIFIED)

Test command:  <resolved command>
Baseline before: <N passing, M failing, K errors>
Baseline after stubs: <N passing, M failing, K errors>
Test files created/modified:
  <path>
Stub files created (or: none):
  <path>  — sentinel: <what it returns, and why it cannot satisfy any assertion>
Red test node-ids:
  <exact node-id runnable by the command above>  FAIL  [contract | non-interference]
Regression test node-ids (or: none):
  <exact node-id>  PASS — guards: "<what it protects, quoted>"
Observed failure output:
  <the decisive assertion-failure lines, quoted from the run>
```

**Every node-id carries the tag written in its source** (Step 4a), and the report and the
source must agree — the caller reads this list and never re-derives tags from the files.

**Every `regression` entry carries its quotation, and every `non-interference` entry its
pairing.** An entry missing the required clause is refused rather than read charitably: the
clause is the control, and a tag that costs nothing to write is worth nothing downstream.
`none` is a real answer for the regression section and often the right one; an empty section
is not the same as an absent one, so write it.

Node-ids must be exactly runnable (`tests/test_x.py::test_y`, `TestFoo/subcase`,
`pkg -run TestFoo`) — downstream steps re-run them individually and cannot repair a
paraphrase.

**Take them from the runner's own output, never by reading your source.** You wrote the
tests, so listing what you *think* you wrote is the one enumeration guaranteed to agree with
your intent rather than with the suite. Subtests, parametrized cases and table rows have no
declaration line of their own and are invisible to a grep. You already ran the suite twice
(Steps 3 and 6) — the set is in that output.
→ Read `skills/run/references/node-ids.md`; Go in particular cannot be enumerated statically.

**Report every runnable node-id, not one per test function.** A table-driven test with five
rows is five node-ids. Every downstream check — mutation probes, vacuity, the freeze
comparison — is only as fine-grained as this list, and none of them can recover a case you
did not name.

**You do not prove that each test fails for the *right* reason.** That is the
`mutation-check` worker's job; the orchestrator runs it after you, with the node-ids and
stub paths you returned. Report what failed and what you saw — do not mutate code, do not
re-run tests against modified sources, and do not vouch for falsifiability beyond it.
