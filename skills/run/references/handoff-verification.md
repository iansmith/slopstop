# Handoff verification — the one definition

The orchestrator runs this. It checks the **worker's output** per the governing rule:

> **No information, artifact, report, or claim is ever accepted at face value by any model
> doing checking.** Checkers are always fresh invocations fed only artifacts — never the
> author's narrative or transcript.

And: *"A clean review is necessary, never sufficient."* `review` hunts **bugs**; this hunts **conformance**, from outside, at the tier above, against the ticket.

## The order is the design

```
implement returns
   |
   +- 8a  MECHANICAL, inline, no agent -+- tamper diff        -+
   |                                    +- file-map violation -+ FAIL -> stop the ticket.
   |                                                           | No checker is spawned.
   +- 9   gates      (slop / vacuity / complexity)             |
   +- 10  review     (loop to REVIEW CLEAN)                    |
   |                                                           |
   +- 10b HANDOFF, two fresh agents at the tier above ---------+
          requirements adversary + code reviewer
          -> a blessing bound to the branch tip SHA
```

> **`tamper` runs twice, and a second run is a second span.** The 8a diff and the 10b
> re-check at the current tip are two separate runs against two different commits, so each
> gets its own `started` / `finished` pair. Do not write the 10b close against 8a's span.
> Why: SOP-261 lost 3h00m05s to an orphan close. The close-time check in `run-jsonl.md`
> (invariant 1's mirror) catches it while repairable.

**Mechanical checks run first; a FAIL ends verification — no subagent is bought.** *A green suite is not evidence when the agent had write access to the tests.*

**Every `git` command below takes `-C <the branch's checkout>`** — a linked worktree under `.claude/worktrees/<TICKET>` since BILL-466. Written as `git ...` for readability; do not run against whatever cwd happens to be.

**Corrected 2026-08-30 by measurement.** This paragraph used to say *"Claude Code blocks
`-C` and relative paths inside a worktree"*, and concluded that stages 8a and 10a must stay
`I` (inline) because handing them to a worker *"turns them into permission errors."* That is
false, and it closed off the two largest inline mechanical stages on a constraint that does
not exist. A probe agent run under `isolation: "worktree"` established the real rule.

**`-C` is not blocked. `-C` pointing somewhere other than the agent's own worktree is.**
Claude Code applies four checks to a worktree-isolated session
(`https://code.claude.com/docs/en/worktrees`): it blocks file edits targeting the main
checkout, a command whose working directory resolves there, a command that redirects git
there (`-C`, `--git-dir`, `GIT_DIR`, `GIT_WORK_TREE`, or a `cd`), and a command whose shape
it cannot verify stays inside the worktree.

Measured, from inside a worker's own worktree:

| | verdict |
| -- | -- |
| plain `git log` / `diff --numstat` / `merge-base --is-ancestor` / `show --stat` / `status --porcelain`, no `-C` | **allowed** |
| `git -C <the agent's OWN worktree>` (including `-C .`) | **refused** — "can't be verified before it runs" |
| `git -C <the main checkout>`, `GIT_DIR=<main checkout>/.git` | refused |
| `git -C <a SIBLING worktree>` | **refused** — see below |
| unquoted heredoc (`<<EOF`), brace expansion (`{a,b,c}`) | refused, "too complex to verify" |
| quoted heredoc (`<<'EOF'`), `;` chains, `$?`, single-quoted `--format` | allowed |
| Write into the main checkout | refused at the tool level |

**The sibling-worktree refusal is the one that shapes the design, and it is not in
Anthropic's docs.** Pointing `-C` at another ticket's worktree is refused with the same
"shared checkout" wording as the main checkout. So a worker cannot inspect a checkout it
does not own, by any path. It must have the branch checked out in **its own** worktree and
compare **by ref** — `git log "$BASE..HEAD"`, not `git -C <somewhere else>`. That is already
how `worker-launch.md` arranges every worker's branch, so 8a and 10a need no new mechanism
to move; they need the `-C` dropped.

**What genuinely keeps the orchestrator in the main worktree** is the file-edit check, not
the git ones: `run.jsonl`, `task_plan.md` and `findings.md` live in the main checkout's
tracking dir, and a worktree-isolated context cannot write there. That constraint is real
and unchanged.

The durable lesson is the one universal §9 already records about `/code-review`: a
written-down claim that something is forbidden can be wrong when written, and from the
outside a false constraint is indistinguishable from a real one. This one stood because it
was specific and plausible. The test that overturned it was a single probe agent — 78K
tokens, 87 seconds.

## 8a — The mechanical tamper diff

### Resolve the baseline: the EARLIEST Phase 0 commit

`$FROZEN` was captured at stage 6. **Use it.** Derive only when verifying a branch this run did not create (salvage, or a resume whose `run.jsonl` predates the capture):

```bash
FROZEN=$(git log --format='%H %s' "$BASE..$TIP" | grep 'Phase 0' | tail -1 | cut -d' ' -f1)
```

**`tail -1`, never `grep -m1`.** `git log` lists newest first; `-m1` is the newest, `tail -1` is the earliest. Why: stage 7's gap-test commit is a second `Phase 0` on every normal branch, so `-m1` picks the wrong one routinely.

Then assert ancestry: `git merge-base --is-ancestor "$FROZEN" "$TIP"` and `git merge-base --is-ancestor "$BASE" "$FROZEN"`.

### No Phase 0 commit at all -> FAIL, immediately

Not "nothing to check". **FAIL.** Why: an agent that never wrote a failing test has an unfalsifiable green suite.

The only exemptions are the two literal stage-4 outcomes: `PHASE 0: none -- prose-only change` and `PHASE 0: none -- refactor`. Matched as the literal string, not a paraphrase.

**Refactor tickets** are exempt here and guarded elsewhere: they write no new tests, so no `$FROZEN` exists; instead, **no test file may be modified at all**, checked by `:run`'s refactor-section diff. The two checks are complementary — neither covers the other's case, neither may be skipped on the other's strength.

> **Predict-then-verify** is a related DoD pattern (capture a deterministic transform's dry-run, confirm the diff matches). It catches hand edits inside cosmetic diffs. It is a DoD pattern a ticket opts into, not a gate this stage runs — the one definition is `tickets/references/ticket-standard.md`, section 3.

### The frozen set is the commit, not a glob

```bash
FROZEN_FILES=$(git show --name-only --format= "$FROZEN")
```

Exact by construction, language-agnostic, catches inline `#[cfg(test)]` tests that a `'*_test.*'` glob would miss.

### Two guards — both FAIL, both asserted before the diff runs

- **`$FROZEN` empty or unresolvable.** `git diff "$FROZEN..$TIP"` becomes `git diff ..$TIP` which git reads as `HEAD..$TIP` — exit 0, empty output, looks clean. Assert non-empty, then `git rev-parse --verify "$FROZEN^{commit}"`.
- **`$FROZEN_FILES` empty.** The pathspec vanishes; the command diffs the entire repo, reporting the implementation's own files as tamper. Assert non-empty. An empty frozen set is itself a FAIL.

### The signal: a line that existed at `$FROZEN` was removed or changed

```bash
git diff -w --ignore-blank-lines "$FROZEN..$TIP" -- $FROZEN_FILES
```

- **Any removed line (`^-`) in a frozen file is a FAIL.** Report file, line, old -> new.
- **A pure addition is not a finding.** Stage 7's gap-test commit adds to these files; flagging additions would fail every normal branch.
- **A frozen file deleted or renamed is a FAIL.** Check explicitly via `git diff --name-status -M`.
- `-w --ignore-blank-lines` keeps formatter runs from reading as rewrites.

**Shadow-test is not yours.** A second definition of a frozen test's name neutralizes it via pure addition — the diff cannot see it. That belongs to the requirements adversary (named there explicitly).

### Under `--backfill`

The trigger is unchanged; only the **resolution** differs. `mutation-check` is the only gate, and deleting a `not-pinned` test is the cheapest evasion. A removal in the frozen set stops the ticket until both the node-id set is shown not to have shrunk **and** `mutation-check --backfill` passes. `:run`'s backfill section is the one definition. **Never clear by reading the diff for intent.**

### The classification rule — core of the whole design

> A vetted expected value changed by the model whose code had to satisfy it is tampering
> by construction, regardless of how it is narrated.

Why: an agent's test correctly asserted a G.711 value; its fix commit edited the assertion, not the decoder. Do not read commit messages before deciding. Decide on the diff, then quote the message as evidence.

## 8a — The file-map violation check

The ticket's section 2 file map is a fence. A write outside it is an instant stop.

**Two commands, unioned. Neither is sufficient alone:**

```bash
FORK=$(git merge-base "$ORIGIN_REMOTE/$BASE_BRANCH" HEAD)
git diff --name-only "$FORK"                       # committed AND tracked-uncommitted
git ls-files --others --exclude-standard           # untracked new files
```

**`$FORK`, derived here, not the recorded `$BASE`.** Once a branch carries the integration branch in, the recorded fork point stops meaning "everything since here is mine." `:run`'s `$OWN` section is the one definition of the derivation. The working-tree form (`"$FORK"` with no `..HEAD`) is deliberate: it compares commit-to-working-tree, folding committed and uncommitted into one command. Three-dot takes two commits and cannot reach the working tree, so rewriting as `"$ORIGIN_REMOTE/$BASE_BRANCH...HEAD"` silently drops the uncommitted half.

`git diff --name-only` alone **misses untracked new files**. `git status --porcelain` alone misses committed writes. Use both.

Match each path against the file map. **A directory entry covers its whole subtree.** Any path matching nothing -> stop the ticket, citing every offending path and the map.

Run this **during execution as well as at handoff** wherever the branch is observable between milestones.

## 10b — Two fresh agents, at the tier above

Run **only if both mechanical checks passed.** Launch per `worker-launch.md`, resolving the tier from `[stage_tiers]` — checking work runs one tier above.

### Launch them SERIALLY. Never in parallel.

**Both agents mutate production code to prove findings.** Two mutating workers in one working tree see each other's probes and contaminate each other's verdicts. Why: PLTF-2562 — the adversary observed the reviewer's `zz_probe_tmp_test`.

**Stage 9 looks like the opposite but is not.** Stage 9 launches three gates together on the READ-ONLY brief (`worker-launch.md`), which detaches each at the tip. Read-only workers share a *branch* safely because none holds checkout. 10b's workers must write, so they need the branch, and a branch is checked out in exactly one worktree (BILL-597). Serializing costs one stage's wall-clock; that is the right trade against a contaminated verdict.

**Whichever runs second inherits the tree the first left.** Confirm the tree is clean of probes between the two launches (the restoration check in `worker-launch.md` is load-bearing here).

### Which checker runs is decided by ticket mode

| | normal | refactor | backfill |
|---|---|---|---|
| requirements adversary | Y | **skip** | Y |
| code reviewer | Y | Y | **skip** |

**Structural argument, not a cost saving:**

- **Refactor skips adversary.** Three of four calibers concern new tests; a refactor has none. Remaining conformance items are mechanically verified before 10b. Code reviewer stays (production correctness).
- **Backfill skips reviewer.** Deliverable is tests; production-correctness review is the wrong lens. Adversary stays (shadow-test and expectation-location are live threats against new tests).
- **The survivor runs at effort `medium`**, not the tier's default. Invariant tickets are mechanically fenced, so the surviving check reads a narrower surface. **Normal tickets run at the tier's full effort**, unchanged.

The tier is a **ceiling** — a stage may ask for less, none may ask for more.

**Say which one you skipped, why, and that the survivor ran at `medium`.** A skip not stated is indistinguishable from one that passed.

**A normal ticket launches both.**

**Both are fed artifacts only**: ticket body, DoD, worktree/branch, diff from fork SHA. Do not pass `implement`'s report, the PR description, or any summary. A summary by the orchestrator is still a narrative.

### The requirements adversary

Charter: *fail this work if you can.*

`adversary --target <branch diff + worktree> --goals <ticket body + DoD> --caliber conformance,shadow-test,expectation-location,redness --round <n>`

Scores the DoD **item by item** and hunts three evasions a diff cannot see:

- **(a) Shadow definition** of a frozen test's name (including via rename/merge).
- **(b) Expected value outside the frozen set** — in a helper, `conftest.py`, fixture, or golden file the Phase 0 commit never froze.
- **(c) Whether the test was actually red**, not merely committed under a Phase 0 title.

And the one only it can catch: a value wrong on arrival is invisible to the tamper check.

### The code reviewer

A fresh `review` launch: correctness, removed invariants, honest error handling, house style.

**Why fresh:** the `review` worker hunts bugs; this hunts conformance, at the tier above, artifacts-only, blessing bound to a SHA. Different question, different tier. (Stage 10's rounds are already fresh per its own spec; the prior rationale claiming otherwise was wrong — corrected in BILL-542.)

**Applied fixes are committed before the round closes.** `review` applies with `Edit`; on a non-clean verdict, commit fixes, then **re-verify on the new tip** — the blessing binds to a SHA, and the tip just moved. Why: SOP-261 — reviewer fixes left uncommitted; the adversary spent a blocker finding on process debris.

### What crosses back

Only the verdict and findings — `VERDICT` plus `<file>:<line> -- <defect> -- <fix>`. **The orchestrator never ingests diffs.** Longer detail goes to a file in the tracking dir; the finding cites it.

## The blessing binds to a SHA, not to a ticket

On passing handoff, record:

```json
{"ticket":"BILL-501","event":"note","stage":"handoff","at":"...",
 "verdict":"BLESSED","blessed_sha":"<git rev-parse HEAD>"}
```

**Re-check at merge.** If the tip has advanced past the blessed SHA, the blessing is **void** and handoff re-runs. Stage 10 commits fixes and stage 12 may apply more — a blessing taken before them and trusted after them blesses code nobody checked.

## Every verdict is recorded, and none of them is rounded

Write each as its own `run.jsonl` line, spelled exactly:

| verdict | meaning |
|---|---|
| `TAMPER CLEAN` | frozen set has no removed lines and no deleted/renamed frozen file |
| `TAMPER FAIL: <file>:<line>` | a frozen line changed — old -> new in the result |
| `TAMPER FAIL: no Phase 0 baseline` | no baseline commit, and stage 4 recorded no legitimate empty outcome |
| `TAMPER BLOCKED: <guard>` | `$FROZEN` or `$FROZEN_FILES` failed its guard — **never a pass** |
| `FILEMAP CLEAN` | every changed path is inside the map |
| `FILEMAP FAIL: <paths>` | at least one is not |
| `HANDOFF CORRECT: <sha>` | no surviving findings; blessing binds to that tip |
| `HANDOFF SALVAGE: <n>` | findings survive; repairable in place |
| `HANDOFF DROP: <n>` | findings survive; repairing would mean redoing the work |

### The three-way verdict (BILL-535)

10b returns a **disposition**, not pass/fail. The two failure modes want opposite treatments.

**Decide with the severity vocabulary** (`adversary`'s section Severity, which `review` also carries since BILL-544):

- **`CORRECT`** — nothing survived. Same SHA binding as the old `BLESSED`.
- **`DROP`** — a surviving `blocker` repair cannot reach: a DoD item not implemented, an approach contradicting the ticket, or a change whose removal takes the rest with it. Test: *"would fixing this mean writing the attempt again?"*
- **`SALVAGE`** — findings survive but none qualifies as `DROP`. `major`, `minor`, and locally addressable blockers are repairs, not rewrites.

**When agents disagree, take the more conservative disposition** — `DROP` over `SALVAGE`, `SALVAGE` over `CORRECT`.

**Every non-`CORRECT` verdict carries numbered findings.** An empty list is a defect in the evaluator — re-run the check, never throw away a branch on it.

`BLOCKED` is not `CLEAN`. Every lethal gate failure in this repo had one shape: something measured zero, and zero read as fine.

## Even the orchestrator's own report is not trusted

Its adversary works from git log, the ticket system, and **re-runs the suite itself** — does not accept the report's claim of green. Cap at 3 rounds. The human gets the report **with surviving findings attached, never a cleaned-up version.**
