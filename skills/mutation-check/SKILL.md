---
description: Verify that a set of freshly-written tests is pinned to the behavior it names — that a failing test is red for the RIGHT reason, or, under --backfill, that a passing test goes red when the behavior it claims to cover is broken. Returns a per-test verdict with evidence plus one overall PASS / FAIL / PINNED / NOT PINNED.
---

# Mutation check — prove the result is meaningful

You are a worker agent with **no prior conversation**. Everything you need arrives in your
arguments. You do not write tests, you do not fix tests, and you do not resolve the test
command — a sibling worker owns all three. You are handed tests already written, and you
decide whether their result means anything — a failure that is red for the right reason, or,
under `--backfill`, a pass that goes red the moment the behaviour it names is broken.

A test that is red for the wrong reason is indistinguishable from a good red test at a
glance: both print `FAIL`. If it is red because a symbol is missing, a fixture is absent,
or it asserts something no implementation could satisfy, the suite certifies nothing.

## Arguments — never guess a missing one

- **`--tests`** — the test file paths under examination.
- **`--node-ids`** — the individual failing tests, in the runner's own id syntax
  (`tests/test_x.py::test_y`, `TestFoo/case`, …). One verdict per node-id.
- **`--command`** — the exact command that runs the suite. Do not auto-detect one.
- **`--targets`** — optional; the production files each test is supposed to pin. Derive
  from the failure traceback when absent. **Required under `--backfill`**, where nothing
  failed and there is no traceback to derive from.
- **`--stubs`** — optional; stub files added so tests could reach their assertions.
- **`--backfill`** — the tests are **green** and cover behaviour that already works. The
  whole question inverts; read the `--backfill` section below instead of Steps 1–5, and
  note that in that mode you are the **only** gate on the ticket.
- **`--implemented`** — the tests are **green because the implementation made them pass**,
  and `--targets` is the branch's **own production diff**. Read the `--implemented` section
  below instead of Steps 1–5. `--targets` is **required** here for the same reason it is
  under `--backfill`: nothing failed, so there is no traceback to derive from.

**`--backfill` and `--implemented` are mutually exclusive.** Both given → `MUTATION CHECK
BLOCKED: --backfill and --implemented are exclusive`. They ask the same *question* of
different code at different moments, and a run that thought it was both would report a
verdict about a target set nobody chose.

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

**This is the general mutation protocol's restore step, done strictly.** The protocol —
perturb, observe, restore, control — is defined once in `worker-launch.md` and shared with
`adversary` and `review`; what follows is this worker's stricter instance of its step 3, and
the two are one protocol rather than two. Where they differ, the difference is only that this
one demands more: `worker-launch.md` requires the tree clean of probes, and this also requires
the **baseline to reproduce**.

**Every edit in Steps 3–5 (or B2–B3, or `--implemented`'s B1–B5) is temporary and must be
undone before you return.**
Track each file you touch and revert it — `git checkout -- <path>` for tracked files, a
saved copy for untracked ones. Then verify: `git status --porcelain` must show exactly the
same entries it showed before you started, and a final re-run of `--command` must reproduce
the baseline exactly — the Step 1 **failures**, or under `--backfill` the Step B1
**passes**. A backfill run that ends with the suite red has left a mutation behind, and that
is worse than the check never running: the next stage would read it as a regression this
ticket caused. If either check disagrees, say so at the top of your report — a mutation left
behind is worse than an unverified test. State explicitly in the report that all probe
mutations were reverted, and how you confirmed it.

## `--backfill` — the same question, asked backwards

A **backfill** ticket adds coverage over behaviour that already works, so its tests are
**green** from the moment they are written and Steps 1–5 above have nothing to bite on.
`vacuity-check` cannot help either: its question is *would this have passed at base?* and
the answer is "yes, by design".

So the question that decides a backfill test is yours, inverted: **break the behaviour the
test claims to pin, and does the test go red?** A test that survives every mutation is
worthless in exactly the way a vacuous test is worthless — green, named after the behaviour,
and still green when that behaviour is deleted tomorrow. **You are the only gate on this
path.** There is no second check behind you.

`--targets` stops being optional here. It names the production code each test is meant to
pin, and it is what you mutate. Missing → `MUTATION CHECK BLOCKED: --backfill needs
--targets`. Do not infer targets from a traceback: there is no traceback, because nothing
failed.

Replace Steps 1–5 with the following. Step 6 (restore, and prove you restored) applies
unchanged and matters more here — every probe edits **production** code.

### Step B1 — Baseline: confirm green, alone, and **report the enumerated set**

Run `--command` scoped to the node-ids, then each node-id **alone**. Every one must pass.
A node-id that fails is not a backfill test — report it as `not-pinned (red at baseline)`
and say so loudly; `red-tests --backfill` should have stopped before you were launched, and
a red test here means the ticket is a normal one in the wrong mode.

**That run enumerates the suite for free — capture it and report it.** List every runnable
node-id the runner emitted for `--tests`, not only the ones you were handed. The caller
compares that set against an earlier one to detect a deleted test, and it cannot build the
set itself without running the suite again.
→ Read `skills/run/references/node-ids.md`

Two consequences worth stating in your report: a node-id you were **given** that the runner
never emitted has been deleted or renamed, which the caller needs to know; and a node-id the
runner emitted that you were **not** given is outside your verdict — name it rather than
silently probing or ignoring it.

### Step B2 — Probe D: the subtractive mutation (does breaking it turn the test red?)

For each node-id, edit its `--targets` so the pinned behaviour is **wrong** — return a
different value, drop the branch, skip the assignment, delete the wiring line. One mutation
at a time, the smallest edit that genuinely changes behaviour. Re-run that node-id alone.

- **Goes red** → the test is reading the real code path. Probe D satisfied.
- **Stays green** → it pins nothing. `not-pinned`, with the mutation you made as evidence.
- **Errors instead of failing an assertion** → `inconclusive`: you broke compilation, not
  behaviour. Make a smaller mutation and try again before recording it.

Do at least **two** distinct subtractive mutations per node-id where the target offers
them. One mutation proves the test reads *something*; two make it much harder for a test
that happens to be coupled to an unrelated side effect to pass by luck.

### Step B3 — Probe E: the generative mutation (is it driven by structure or by a list?)

**Only when the ticket claims enumeration** — "adding a new X without wiring it fails the
test", "every setter is asserted", "all handlers are covered". That claim is the most
valuable thing a backfill test can offer and the easiest to fake, because a hand-maintained
list satisfies it today and silently rots the first time someone adds an X.

**Add** an uncovered instance of the enumerated thing to the production code — a new
unwired setter, a new unregistered handler — and re-run.

- **Goes red** → the test is driven by the structure. Probe E satisfied.
- **Stays green** → the enumeration claim is false. Record `not-pinned (enumeration claim
  unverified: added <what>, test stayed green)`. **A deletion-only check cannot see this**,
  which is exactly why this probe exists.

Where the ticket makes no enumeration claim, skip it and **say you skipped it and why**. A
silently skipped probe is indistinguishable from a passed one.

### Step B4 — Say what you measured, so a stale run is identifiable

Report the **test files and their content sha** you actually ran against, and the
`--targets` you mutated. A backfill ticket's tests can be rewritten after an earlier run of
this check — by an adversary round, by the caller's fixes — and a verdict that does not name
what it measured is indistinguishable from one that covers the shipped tests. If the caller
tells you this is a re-run, say which it is.

**You do not compare node-id sets across time** — you see one point in history and cannot
know what was there before. The caller owns that comparison, and it matters: a test that no
longer exists cannot come back `not-pinned`, so your clean verdict on a shrunk set is
accurate and misleading at once. What you owe the caller is the **set as the runner
enumerated it at this point in history** (Step B1), which is the half of the comparison only
you can produce without a second suite run.

### Step B5 — Verdicts

Per node-id: `pinned` / `not-pinned` / `inconclusive`. Overall line, spelled exactly:

- **`MUTATION CHECK PINNED: <n> of <n>`** — every node-id survived every probe that ran.
- **`MUTATION CHECK NOT PINNED: <n> of <m>`** — one or more is `not-pinned` or
  `inconclusive`. This **stops the ticket**.
- **`MUTATION CHECK BLOCKED: <reason>`** — you could not run at all.

**Name which probe shapes ran, in the report.** A run that did only subtractive mutations on
a ticket claiming enumeration is **partially verified, never `PINNED`** — say so on the
verdict line as `MUTATION CHECK NOT PINNED: enumeration unverified`. Reporting a partial
check as a pass is the one failure this mode cannot survive.

**Before returning, run the project's formatter over the files you touched.** One definition, in `worker-launch.md` — the project's own formatter, never a named one, and only the files this worker changed.

## `--implemented` — does the suite pin the code the implementer just wrote?

**Run this at stage 9, after `implement` returns.** Same question as `--backfill`, asked of
different code at a different moment: *the tests are green — would breaking the production
code turn them red?*

**Run Steps B1–B5 exactly as written**, with one substitution and one addition. Do not read
Steps 1–5: they start from a captured failure and there is no failure here.

- **`--targets` is the branch's own production diff**, not pre-existing code and not the
  stage-4 stubs. The caller derives it and passes it; never widen it yourself. A symbol the
  branch did not touch is somebody else's debt and reporting it here buries the finding that
  belongs to this ticket.
- **Probe E's precondition still holds.** Run the generative mutation only where the ticket
  claims enumeration, and say so when you skip it.

**Report every unkilled mutation by production symbol and by the mutation that survived**,
not by node-id alone. The caller's next move is to write a test that pins that symbol, and
`not-pinned` without the symbol name makes it guess:

```
not-pinned  internal/config.readRealtimeVoiceURL
            mutation: `return url` -> `return ""`   suite stayed GREEN
```

That example is real. It is a blocker SOP-262's handoff adversary found at stage 10b, at the
tier above, after the PR was already open — the class of defect this mode exists to catch one
stage earlier and one tier cheaper.

### Why this is not stage 5 run twice

Stage 5 mutates the **stubs**, before `implement` exists, and asks *"is this test red for the
right reason?"* This mutates the **real implementation** and asks *"does anything pin it?"*
The stage-5 invocation is unchanged and still runs; both spans appear in one run with
different targets. **Two mutation passes with one meaning would be a second definition of the
same check** — these are two questions and the difference is the target.

### Verdict vocabulary is `--backfill`'s, deliberately

`MUTATION CHECK PINNED: <n> of <n>` / `NOT PINNED: <n> of <m>` / `BLOCKED`, exactly as
Step B5 defines them. Same question, same words — inventing a third set would be a parallel
vocabulary for one concept. The two passes are told apart in the record by their **stage**
(`mutation-check` at 5, `gates` at 9), which is where that distinction belongs.

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
