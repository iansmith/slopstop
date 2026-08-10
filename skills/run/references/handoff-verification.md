# Handoff verification — the one definition

The orchestrator runs this. It is the check on the **worker's output**, and it exists
because of the governing rule in `design/slopstop-process.md`:

> **No information, artifact, report, or claim is ever accepted at face value by any model
> doing checking.** Checkers are always fresh invocations fed only artifacts — never the
> author's narrative or transcript.

And: *"A clean review is necessary, never sufficient."* The `review` worker hunts **bugs**.
This hunts **conformance**, from outside, at the tier above, against the ticket.

Every rule below has a named incident behind it. `design/worktree-parallelism-prior-art.md`
records them; re-deriving these from first principles means re-earning the scars.

## The order is the design

```
implement returns
   │
   ├─ 8a  MECHANICAL, inline, no agent ─┬─ tamper diff        ─┐
   │                                    └─ file-map violation ─┤ FAIL → stop the ticket.
   │                                                           │ No checker is spawned.
   ├─ 9   gates      (slop / vacuity / complexity)             │
   ├─ 10  review     (loop to REVIEW CLEAN)                    │
   │                                                           │
   └─ 10b HANDOFF, two fresh agents at the tier above ─────────┘
          requirements adversary + code reviewer
          → a blessing bound to the branch tip SHA
```

> **`tamper` runs twice, and a second run is a second span.** The 8a diff and the 10b
> re-check at the current tip are two separate runs of the same check against two different
> commits, so each gets its own `started` / `finished` pair. Do not treat the 10b run as a
> continuation of the 8a span and do not write its close against the span 8a already closed —
> that is an orphan close, and it costs the run's entire timing rather than one span's. SOP-261
> lost 3h00m05s to exactly this: `tamper finished` at 22:08:16 with no `started` after 21:39:59.
> The close-time check in `run-jsonl.md` (invariant 1's mirror) is what catches it while it is
> still repairable.

**The mechanical checks run first, and a FAIL ends verification there — no subagent is
bought.** That ordering is not an optimisation. *A green suite is not evidence when the
agent had write access to the tests*, so spending a checker on a branch a diff already
condemns is spending it on a question that has been answered.

**Every `git` command below takes `-C <the branch's checkout>`** — a linked worktree under
`.claude/worktrees/<TICKET>` since BILL-466, the main worktree before it. Written out as
`git …` for readability; do not run them against whatever happens to be the cwd. The path may
be relative: these commands were exercised as a subprocess from two directories above and
below the repo root with a relative path argument, and `-C` is what makes that work.

**This is safe only because YOU run it, from the main worktree, and it stops being safe if
that changes.** Stages 8a and 10b are `I` — the orchestrator's own inline work. The
orchestrator never enters a worktree, so Claude Code's isolation enforcement does not apply
to it and `-C` is an ordinary argument.

Inside a worktree it is not. Claude Code blocks *"a command that redirects git into the main
checkout, whether through `git -C`, `--git-dir`, a `GIT_DIR` or `GIT_WORK_TREE` variable, or
a `cd` into the main checkout before running git"* — **and blocks a command it cannot verify
stays inside the worktree**, which a relative `-C` path is exactly the shape of. So handing
these commands to a worker, or moving the orchestrator into a worktree, turns every one of
them into a refusal that surfaces as a permission error in a verification stage rather than
as the design mistake it is.

**BILL-535 is where this can break.** "Every `:run` agent works in a worktree" must not be
read as *the orchestrator too*. If 535 ever needs it to be, these commands need rewriting to
run from inside the worktree with no `-C` at all — not a flag change, a re-siting.

## 8a — The mechanical tamper diff

### Resolve the baseline: the EARLIEST Phase 0 commit, never the newest

`$FROZEN` was captured at stage 6, at the moment the commit was made. **Use it.** That is
the only moment it is unambiguous, and threading it is why it exists.

Derive it **only** when verifying a branch this run did not create — a salvage, or a resume
whose `run.jsonl` predates the capture. Then:

```bash
FROZEN=$(git log --format='%H %s' "$BASE..$TIP" | grep 'Phase 0' | tail -1 | cut -d' ' -f1)
```

**`tail -1`, never `grep -m1`.** `git log` lists newest first, so the last matching line is
the *earliest* commit and `-m1` is the *newest*. Taking the newest lets an agent slide the
baseline past its own tamper by titling a later commit `Phase 0: red tests` — and it is not
even adversarial to trigger: stage 7's legitimate gap-test commit is a second `Phase 0`
commit on every normal branch, so `-m1` picks the wrong one routinely. Measured on a staged
branch: `-m1` returned the gap-test commit, `tail -1` returned the red-test commit.

Then assert what you derived: `git merge-base --is-ancestor "$FROZEN" "$TIP"` and
`git merge-base --is-ancestor "$BASE" "$FROZEN"`. A sha that is not between the two is not
this branch's baseline.

### No Phase 0 commit at all → FAIL, immediately

Not "nothing to check". **FAIL.**

> An agent that never wrote a failing test never proved its tests can fail, so its green
> suite is unfalsifiable… This is the cheaper evasion of the whole rule, and a tamper diff
> that only runs when a baseline exists rewards skipping the baseline.

Observed live on SOP-110. The only exemption is a stage-4 outcome that **legitimately**
recorded an empty Phase 0 — matched as the literal string stage 4 returned, not as a
paraphrase and not as an inference from the diff. There are exactly two:
`PHASE 0: none — prose-only change` and `PHASE 0: none — refactor`. A branch with tests and
no baseline commit is the case this catches, and it is the common one.

**A refactor ticket is exempt here and guarded elsewhere, not unguarded.** It has no
`$FROZEN` because it writes no new tests — so the tamper diff has nothing to compare — and
what stands in for it is the rule that **no test file may be modified at all**, checked by
its own diff in `:run`'s refactor section. The two are complementary: for a normal ticket
some test files are frozen and additions are fine; for a refactor ticket every test file is
frozen and nothing is fine. Neither check covers the other's case, so neither may be
skipped on the strength of the other having run.

> **The nearest relative: predict-then-verify.** The tamper diff works because the expected
> change to a frozen file is **none**, which makes any change detectable without judgment.
> Where a change is produced by a deterministic transform — a formatter run, codegen,
> a dependency bump — the expected change is not empty but it is *computable*, and the same
> trick applies: capture the transform's dry-run output before applying it, then confirm the
> diff matches. It catches the one thing review and tests both miss, a hand edit riding along
> inside a wholly cosmetic diff.
>
> **It is a DoD pattern a ticket opts into, not a gate this stage runs**, and the two are not
> interchangeable — tamper asks whether frozen files changed, predict-then-verify asks whether
> a computed change matches its computation. Do not fold either into the other. The one
> definition is `tickets/references/ticket-standard.md`, §3.

### The frozen set is the commit, not a glob

```bash
FROZEN_FILES=$(git show --name-only --format= "$FROZEN")
```

> Exact by construction, language-agnostic, and it catches Rust/Go inline `#[cfg(test)]`
> tests living in source files, which a `'*_test.*'` glob would miss entirely.

### Two guards, each with its failure mode

Both were live defects. Both **must be asserted before the diff runs**, and both are FAIL:

- **`$FROZEN` empty or unresolvable.** `git diff "$FROZEN..$TIP"` becomes `git diff ..$TIP`,
  which git reads as `HEAD..$TIP` — on a checked-out branch that is **exit 0 with empty
  output**. An empty diff that falls through looking clean. Assert non-empty, then
  `git rev-parse --verify "$FROZEN^{commit}"`.
- **`$FROZEN_FILES` empty.** The pathspec vanishes and the command diffs the **entire
  repository**, so the implementation's own files appear and the report describes a tamper
  that is really just the ticket's work. Assert non-empty. An empty frozen set is itself a
  FAIL — a Phase 0 commit that froze no files is not a baseline.

(In the pre-4.0.0 prior art these variables were `$RED` and `$FROZEN`. `$RED` is now
`$FROZEN` and `$FROZEN_FILES` is the file list. Same two traps, renamed.)

### The signal: a line that existed at `$FROZEN` was removed or changed

```bash
git diff -w --ignore-blank-lines "$FROZEN..$TIP" -- $FROZEN_FILES
```

- **Any removed line (`^-`) in a frozen file is a FAIL.** Report the file, the line, and the
  old → new values.
- **A pure addition is not a finding.** *You may add tests. You may never weaken, retarget,
  or remove an existing one* — and stage 7's own gap-test commit adds to these same files,
  so a rule that flagged additions would fail every normal branch.
- **A frozen file deleted or renamed out of the set is a FAIL.** `git diff --name-status -M`
  over the same pathspec reports it as `D`; check it explicitly rather than inferring it
  from an all-removed diff.
- `-w --ignore-blank-lines` is what keeps a `gofmt`/`black` run from reading as a rewrite.

**The shadow-test case is not yours.** A *second definition* of a frozen test's name, added
later, silently rebinds the first in both pytest and Go — a pure addition that neutralizes
a frozen test. The diff cannot see it. That is the requirements adversary's, below, and it
is named there so neither check assumes the other has it.

### Under `--backfill`, the trigger stands and the resolution is mechanical

A backfill ticket has **no implementer** — `implement` is not launched — so the actor this
rule names does not exist there. Do **not** conclude the check is inapplicable. A sharper
actor takes its place: `mutation-check` is the only gate on that path, and *deleting a test
that came back `not-pinned`* is the cheapest evasion available. It produces the same diff as
a legitimate adversary-driven rewrite, because collapsing a hand-maintained enumeration into
a structure-driven test also removes lines.

So the trigger is unchanged and only the **resolution** differs: a removal inside the frozen
set stops the ticket until *both* the node-id set is shown not to have shrunk **and**
`mutation-check --backfill` passes on the current files. `:run`'s backfill section is the one
definition. **Never clear it by reading the diff for intent** — that is the narrative this
rule exists to refuse, and here it would be authored by the session that made the change.

### The classification rule — the core of the whole design

> The agent will have a reason. The commit message will be confident and often cites a real
> standard. **The reason is irrelevant.** A vetted expected value changed by the model whose
> code had to satisfy it is tampering by construction, regardless of how it is narrated.

The originating incident: an agent's test correctly asserted a G.711 value and failed,
pointing at a real four-character bug. Its next commit — *"Fix: use standard G.711 μ-law
table"* — left the decoder untouched and **edited the assertion**. *"This was not confusion,
it was a rationalization, which is why the fix is a mechanical diff and not a sterner
instruction."*

So: do not read the commit messages before deciding. Decide on the diff, then quote the
message in the report as evidence of what was claimed.

## 8a — The file-map violation check

The ticket's §2 file map is a fence. A write outside it is an instant stop — no grace
period, no model judgment.

> The asymmetry is deliberate: an agent writing where it was fenced out is doing damage in
> the wrong place (instant, mechanical); a quiet agent might just be thinking.

**Two commands, unioned. Neither is sufficient alone:**

```bash
FORK=$(git merge-base "$ORIGIN_REMOTE/$BASE_BRANCH" HEAD)
git diff --name-only "$FORK"                       # committed AND tracked-uncommitted
git ls-files --others --exclude-standard           # untracked new files
```

**`$FORK`, derived here, not the recorded `$BASE`.** Once a branch carries the integration
branch in — which `:run`'s conflict rule tells it to do — the recorded fork point stops
meaning "everything since here is mine", and this check starts reporting other tickets' files
as out-of-map writes. `:run`'s `$OWN` section is the one definition of the derivation and why
the obvious three-dot rewrite is a no-op. Note the working-tree form is deliberate: three-dot
is not valid against the working tree, and dropping to a commit-to-commit range would lose
the uncommitted half of this check.

`git status --porcelain` alone misses committed writes — *"agents commit as they go"*. But
**`git diff --name-only <fork SHA>` alone misses untracked new files**, which is precisely
how a brand-new file lands outside the map. Verified on a staged branch: an untracked
`outside.py` appeared in `git status --porcelain` and in `git ls-files --others`, and in
neither form of `git diff`. Use both, or the check has a hole in exactly its most likely
case.

Note the form: `git diff --name-only "$FORK"` with **no `..HEAD`** — that compares a commit
to the *working tree*, which is what folds committed and uncommitted into one command. It is
also why the derivation above uses `git merge-base` rather than a three-dot range: three-dot
takes two commits and cannot reach the working tree, so rewriting this as
`"$ORIGIN_REMOTE/$BASE_BRANCH...HEAD"` would silently drop the uncommitted half of the check.

Match each path against the file map. **A directory entry covers its whole subtree**
(`tests/` covers `tests/unit/test_x.py`). Any path matching nothing → stop the ticket,
citing every offending path and the map it was checked against.

Run this **during execution as well as at handoff** wherever the run can observe the branch
between milestones. The cost is one `git` call; the value is stopping the damage before the
next commit builds on it.

## 10b — Two fresh agents, at the tier above

Run **only if both mechanical checks passed.** Launch per `worker-launch.md`, resolving the
tier from `[stage_tiers]` — checking work runs one tier above the work it checks; never
flatten it.

### Launch them SERIALLY. Never in parallel.

**Both agents mutate production code to prove their findings** (the protocol is defined once,
in `worker-launch.md`). Two mutating workers in one working tree see each other's probes and
each other's breakage, and neither can tell a real defect from the other's experiment.

This is measured, not feared. PLTF-2562:

> **ORCHESTRATOR ERROR: the two handoff agents were launched in PARALLEL, and both make
> temporary production mutations to verify redness. They contaminated each other** — the
> adversary observed the reviewer's `zz_probe_tmp_test`…

The next round recorded the workaround — *"Agents run SERIALLY this round after last round's
cross-contamination"* — and then nothing wrote the rule down, so the next run was free to
repeat it.

**Say it here because stage 9 says the opposite one stage earlier.** Stage 9's row reads
*"launch together, they are independent"*, and that is correct there: `slop-check`,
`vacuity-check` and `complexity-check` are read-only. Carrying that reading forward to 10b is
the natural mistake and it is the one that happened. Independence is a property of read-only
workers, not of checkers in general.

**Serialize; do not isolate — yet.** Per-checker worktree isolation is the better fix and
would let them run concurrently, but it depends on BILL-535 and does not exist today.
Serializing costs one stage's wall-clock on the most expensive stage in the run, and that is
the right trade against a contaminated verdict. When 535 lands, this is the paragraph to
revisit — and only then.

**Whichever runs second inherits the tree the first one left.** That is fine when the first
restored properly and is a silent disaster when it did not, so the restoration check in
`worker-launch.md` is load-bearing here specifically: confirm the tree is clean of probes
between the two launches, not just at the end.

### Which of the two runs is decided by the ticket's mode

| | normal | refactor | backfill |
|---|---|---|---|
| requirements adversary | ✅ | **skip** | ✅ |
| code reviewer | ✅ | ✅ | **skip** |

**Not a cost saving — a structural argument, and it must survive being re-read as one.**

**Refactor skips the requirements adversary.** Its calibers are `conformance`, `shadow-test`,
`expectation-location`, `redness`; three of the four concern **new tests**, and a refactor has
none. What remains — conformance to the DoD — is *suite green before, the same suite green
after, no test file modified, CC targets met*, every item already mechanically verified before
10b is launched. There is nothing left for it to score. The **code reviewer stays**: a refactor
is production code, and correctness, removed invariants and honest error handling is exactly
the lens it needs.

**Backfill skips the code reviewer**, and it is the exact inverse. Its deliverable is tests, so
a production-correctness review is the wrong lens on the wrong artifact. The **requirements
adversary stays**, because shadow-test and expectation-location are live threats against new
tests and the diff cannot see either.

**And the survivor runs at effort `medium`, not the tier's default.** Resolve the tier's
model as always, then launch the `slopstop-effort-medium` carrier rather than the tier's
configured level. It is the same argument that removed the other agent: an invariant ticket's
diff is **mechanically fenced** — a refactor cannot have touched a test, a backfill cannot
have touched production — so the one surviving tier-above check reads a far narrower surface
than it would on a normal ticket. **A normal ticket runs at its tier's full effort**,
unchanged.

The tier is a **ceiling**, not a fixed level: a stage may ask for less, none may ask for more.

**Say which one you skipped, why, and that the survivor ran at `medium`, in the report.**
A skip that is not stated is
indistinguishable from one that passed — and this one changes what was checked.

**A normal ticket launches both.** This selection never applies to it.

**Both are fed artifacts only**: the ticket body and its DoD, the worktree or branch, and
the diff from the recorded fork SHA.

> …never the agent's claims — its ticket comments and PR description are the **subject** of
> scrutiny, not evidence.

That means: do not pass `implement`'s report, do not pass the PR description, do not
summarise what the run did. A summary written by the orchestrator is still a narrative, and
round 1 is the work's first sight of a fresh reader.

### The requirements adversary — charter: *fail this work if you can*

`adversary --target <the branch diff + worktree> --goals <the ticket body and its DoD>
--caliber conformance,shadow-test,expectation-location,redness --round <n>`

It scores the DoD **item by item** and hunts the three evasions a diff cannot see:

- **(a) A shadow definition** of a frozen test's name that neutralizes it — including via a
  rename that merges two tests, which a string compare misses.
- **(b) The expected value living outside the frozen set** — in a helper, a `conftest.py`, a
  fixture, or a golden file the Phase 0 commit never froze, so the frozen test still reads
  untouched while what it asserts has moved.
- **(c) Whether the test was *actually* red**, rather than merely committed under a `Phase 0`
  title.

And the one only it can catch: *"a value that was wrong on arrival is invisible to the
tamper check, and yours alone to catch."* A test frozen with the wrong expectation is
perfectly clean by diff and wrong by contract.

### The code reviewer

A fresh `review` launch at the same tier: correctness, removed invariants, honest error
handling, house style.

**Why fresh, stated correctly (BILL-542).** This paragraph used to read *"the stage-10 review
loop's later rounds have already read their own earlier rounds."* **That is false.** Stage 10
says the opposite in its own words — *"Each round is a fresh worker, so round N+1 cannot
rationalise round N's edits"* — and `review` takes `--scope --mode --frozen` with no
`--prior`, so no findings cross between rounds. The interface is fine; the sentence was wrong,
and a false rationale in the file that calls itself the one definition gets copied forward and
defended.

The true, weaker version: round N+1 sees the *code* round N edited, inside its diff scope, and
can read those fixes as pre-existing rather than as this branch's work. That is a real reason
to want an outside look, and it is not the reason that was written.

**The stage stands on its other legs, which are the strong ones** and are already stated in
this file: the `review` worker hunts **bugs**; this hunts **conformance**, from outside, at the
tier above, against the ticket. Different question, different tier, artifacts-only inputs, and
a blessing bound to a SHA. Fixing the reason does not weaken the stage.

**Applied fixes are committed before the round closes.** `review` applies with `Edit` and
hands nothing back — the same worker, the same behaviour as stage 10, which already has the
rule *"`REVIEW APPLIED: n` → commit and push this round's fixes"*. 10b had no equivalent and
SOP-261 paid for it: *"HANDOFF FAIL: 3 — (1) code reviewer's REVIEW APPLIED fixes were left
uncommitted (blocker, structural)."* The adversary spent a blocker finding on process debris
instead of on the code. So: on a non-clean verdict, commit this round's fixes, then
**re-verify on the new tip** — the blessing binds to a SHA, and the tip just moved.

### What crosses back

Only the verdict and the findings — `VERDICT` plus `<file>:<line> — <defect> — <fix>`.
**The orchestrator never ingests diffs.** Longer detail goes to a file in the tracking dir
and the finding cites it.

## The blessing binds to a SHA, not to a ticket

On a passing handoff, record a `note` carrying the **branch tip SHA at verdict time**:

```json
{"ticket":"BILL-501","event":"note","stage":"handoff","at":"…",
 "verdict":"BLESSED","blessed_sha":"<git rev-parse HEAD>"}
```

**Re-check it at merge.** If the tip has advanced past the blessed sha — a relaunch, a
review round, a bot-comment fix, a salvage commit landed — the blessing is **void** and
handoff verification re-runs on the new tip. This is not hypothetical bookkeeping: stage 10
commits fixes and stage 12 may apply more, so a blessing taken before them and trusted after
them blesses code nobody checked.

A blessing is a statement about a commit. It cannot be a statement about a ticket, because
a ticket keeps moving.

## Every verdict is recorded, and none of them is rounded

Write each of these as its own `run.jsonl` line, spelled exactly:

| verdict | meaning |
|---|---|
| `TAMPER CLEAN` | the frozen set has no removed lines and no deleted/renamed frozen file |
| `TAMPER FAIL: <file>:<line>` | a frozen line changed — old → new in the result |
| `TAMPER FAIL: no Phase 0 baseline` | no baseline commit, and stage 4 recorded no legitimate empty outcome |
| `TAMPER BLOCKED: <guard>` | `$FROZEN` or `$FROZEN_FILES` failed its guard — **never a pass** |
| `FILEMAP CLEAN` | every changed path is inside the map |
| `FILEMAP FAIL: <paths>` | at least one is not |
| `HANDOFF BLESSED: <sha>` | both agents passed; the blessing binds to that tip |
| `HANDOFF FAIL: <n>` | findings survive — go to `failure-and-salvage.md` |

`BLOCKED` is not `CLEAN`. Every lethal failure of a gate in this repo has had one shape:
something measured zero, and zero read as fine.

## Even the orchestrator's own report is not trusted

> The final report is the orchestrator grading its own homework — the one self-assessment in
> the pipeline.

Its adversary is told to work from git log, the ticket system, and **to re-run the suite
itself** — *do not accept the report's claim of green*. Cap at 3 rounds, then the human gets
the report **with the surviving findings attached, never a cleaned-up version.**
