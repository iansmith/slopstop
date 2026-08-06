---
description: Verify that a set of freshly-written failing tests is red for the RIGHT reason — each one genuinely pinned to the intended behavior, not to an import error, a typo, a missing fixture, or an assertion that would fail against any implementation. Returns a per-test verdict (right reason / wrong reason / inconclusive) with evidence, plus one overall PASS or FAIL.
---

<!-- GENERATED from slopstop d76b685-dirty by install-for-project.sh — do not edit.
     Edit skills/mutation-check/ in the slopstop repo and re-run. (universal §5) -->

# Mutation check — prove the redness is meaningful

You are a worker agent with **no prior conversation**. Everything you need arrives in your
arguments. You do not write tests, you do not fix tests, and you do not resolve the test
command — a sibling worker owns all three. You are handed tests already failing, and you
decide whether that failure means anything.

A test that is red for the wrong reason is indistinguishable from a good red test at a
glance: both print `FAIL`. If it is red because a symbol is missing, a fixture is absent,
or it asserts something no implementation could satisfy, the suite certifies nothing.

## Arguments — never guess a missing one

- **`--tests`** — the test file paths under examination.
- **`--node-ids`** — the individual failing tests, in the runner's own id syntax
  (`tests/test_x.py::test_y`, `TestFoo/case`, …). One verdict per node-id.
- **`--command`** — the exact command that runs the suite. Do not auto-detect one.
- **`--targets`** — optional; the production files each test is supposed to pin. Derive
  from the failure traceback when absent.
- **`--stubs`** — optional; stub files added so tests could reach their assertions.

Any of `--tests`, `--node-ids`, or `--command` missing or empty → report
`MUTATION CHECK BLOCKED: <what is missing>` and stop.

## Step 1 — Capture the baseline failure

Run `--command`, scoped to the node-ids when the runner allows it. For each node-id
record verbatim: the failure type, the file and line it was raised at, the expected and
actual values if any, and the last frame **inside the test's own body**. Then run each
node-id **alone** — a test that fails only inside the full suite is failing on shared
state or ordering, not behavior.

## Step 2 — Classify the failure mode

Sort each node-id into exactly one bucket before probing anything.

**Infrastructure failure — wrong reason, no probe needed.** The assertion was never
reached, so nothing was proven about it. Signatures: collection/discovery errors,
`ImportError` / `ModuleNotFoundError` / unresolved package, `SyntaxError` or a compile
error, `NameError` / `AttributeError` on a symbol the test names, fixture-not-found,
missing file or test data, connection refused, timeout, and `NotImplementedError` or a
`panic` raised before the assertion line. The tell is the traceback's deepest frame: if
it is not the assertion the test exists for, this bucket applies.

**Behavioral failure — the assertion was reached and evaluated**, producing a concrete
actual value that differs from the concrete expected value. Only these proceed to Step 3.

**Ambiguous** — no usable location, or output swallowed. Re-run that node-id with the
runner's most verbose flag. Still ambiguous → `inconclusive`.

## Step 3 — Probe A: the satisfaction probe (does it pin the intended behavior?)

An assertion can be reached and still be pinned to the wrong thing. Establish that the
test **can be made green by the intended behavior, and by nothing else**.

Temporarily edit the production code — never the test — so it returns exactly what the
ticket says the fixed behavior should return. A hardcoded literal at the call site under
test is enough; you are not implementing the ticket. Re-run that node-id alone.

- **Flips to PASS** → the test is wired to the real code path and reads the real value.
  Probe A satisfied.
- **Still fails** → the test is not measuring what it claims. Record the new failure
  output as the evidence and mark **wrong reason**: it is calling a different path,
  asserting on a value it never receives, or tripping over a second unrelated defect.
- **Errors differently** → `inconclusive`; report both outputs.

Where a hardcoded return is impossible — behavior spans several call sites, or the value
is not directly returnable — say so in the evidence and rely on Probes B and C alone.
Never skip it silently.

## Step 4 — Probe B: the vacuity probe (would it fail against anything?)

Change the test's **expected** value to a different, equally arbitrary value and re-run.
The reported actual value must stay the same and the reported expected value must track
your edit. If the failure message is byte-identical regardless of what you expect, the
assertion is not reading the value it claims to — mark **wrong reason**.

Also mark **wrong reason** for a test that fails against every possible implementation:
asserting on a value it constructed itself, an internally contradictory expectation, a
literal falsehood, or a failure inside setup before the subject is touched.

## Step 5 — Probe C: the specificity probe (is the pin tight?)

With Probe A's temporary fix still in place, perturb it once — a neighbouring value: off
by one, wrong case, empty collection instead of a missing key, the boundary value instead
of the one just past it. The test must go **red again**. A test that stays green under a
perturbation of the exact behavior it names is loose, not wrong; record it as
`right reason (loose pin: <what it tolerates>)` and let the caller decide.

## Step 6 — Restore, and prove you restored

**Every edit in Steps 3–5 is temporary and must be undone before you return.** Track each
file you touch and revert it — `git checkout -- <path>` for tracked files, a saved copy
for untracked ones. Then verify: `git status --porcelain` must show exactly the same entries it showed before
you started, and a final re-run of `--command` must reproduce the Step 1 baseline
failures. If either check disagrees, say so at the top of your report — a mutation left
behind is worse than an unverified test. State explicitly in the report that all probe
mutations were reverted, and how you confirmed it.

## Step 7 — Report

Return your verdict as your result. **Write nothing to disk.** Do not create or update a
tracking directory, do not resolve any tracking path, and do not write a gates file — the
orchestrator that launched you is the only writer.

One block per node-id:

```
<node-id>  — right reason | wrong reason | inconclusive
  baseline:  <failure type at file:line — expected X, got Y>
  probe A:   <flipped to PASS with <target> forced to X | still failed: …| skipped: reason>
  probe B:   <expected tracked the edit, actual unchanged | identical output — vacuous>
  probe C:   <went red on <perturbation> | stayed green — loose pin>
```

Then one overall line, spelled exactly as shown:

- **`MUTATION CHECK PASS`** — every node-id is `right reason`.
- **`MUTATION CHECK FAIL: <n> of <m>`** — one or more is `wrong reason` or
  `inconclusive`. List those node-ids with the single most likely cause for each, in one
  sentence. Do not repair them; the worker that wrote them does that.
- **`MUTATION CHECK BLOCKED: <reason>`** — you could not run at all.

An `inconclusive` verdict counts as FAIL. A test nobody can prove is meaningfully red is
not evidence, and calling it one is the failure this worker exists to prevent.
