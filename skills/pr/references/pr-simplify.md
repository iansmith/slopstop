# PR Simplify Pass — Full Implementation (Step 1)

## Guard: sibling convention check

Before flagging an error-wrap, docstring, or boilerplate construct as redundant,
grep 2–3 sibling functions in the same file. If the pattern is the established
local convention, do NOT flag it — consistency with neighbors outranks local
terseness.

This guard is restated in each agent's invocation below — an instruction that does
not reach the agent does not bind it.

## Scope — the whole branch change, committed or not

```bash
SIMPLIFY_BASE="$(git merge-base "$ORIGIN_REMOTE/$BASE" HEAD)"
```

Every diff below is `git diff "$SIMPLIFY_BASE"` — **one ref, no range.** `git diff A`
compares A to the *working tree*, so it covers committed work, uncommitted work, and
any mixture in a single command. `git diff A..B` compares two commits and silently
drops uncommitted work; using it here reintroduces the defect this scope exists to
remove. `$ORIGIN_REMOTE` and `$BASE` are already resolved in `:pr` Pre-flight — do not
re-derive them.

This is why Step 1 no longer skips on a clean working tree. Work committed as it was
written — which is what `:plan` Step 3a does on every autonomous and fleet run — is
still work that has never been simplified.

### Frozen Phase 0 tests are excluded

**Never modify a frozen Phase 0 test file.** Derive the frozen set exactly as
`pr-slop-detection.md` § Step 2d derives it — the test files present in the Phase 0
red-test commit — and exclude those paths from simplification. Simplify's remit is
structure and redundancy; a frozen test's shape *is* its contract. Touching one turns
a quality pass into a Step 2d tamper hard-stop two steps later.

## No inline path — Step 1 always spawns

There is no `--inline` variant of this step, deliberately. The agents exist to supply a
context that has not spent the session rationalising the code; running the review in the
caller's session returns exactly the reviewer the isolation is meant to exclude, and
`--inline` would be a flag that silently reinstates it. `--inline` still governs
`:plan`'s fanout; it does not reach here.

If the `Agent` tool is unavailable, **stop and say so**. Do not fall back to reviewing
inline. A skipped simplify pass is visible; a self-reviewed one is not.

## Snapshot commands

```bash
git diff "$SIMPLIFY_BASE" > /tmp/pr-before-simplify.diff
```

## Agent invocation — four briefs, one at a time

Spawn **four `general-purpose` agents, serially** — each with one dimension brief, each
applying its own fixes to the shared working tree. Wait for each to finish before
starting the next.

**Serial is load-bearing, not stylistic.** The four agents write to the same tree. Run
concurrently, the reuse agent extracts a helper out of a function while the
simplification agent rewrites that function inline, and the edits race. Worktree
isolation would fix the race and reintroduce the contamination — merging four divergent
trees happens in *this* session, which is the context being excluded. Serial on a shared
tree is the only arrangement that is both safe and clean: each agent sees its
predecessor's work.

**The agents apply their own fixes.** Do not ask an agent to return findings for this
session to apply. That path ends with the session that wrote the code deciding which
criticisms of it are valid.

Spawn in this order — reuse first, because extracting a shared helper changes what the
later dimensions are looking at:

```
Agent(
  subagent_type: "general-purpose",
  description: "Simplify: reuse",
  prompt: "<contents of skills/pr/references/pr-simplify-brief-reuse.md>\n\nReview this branch's changes. Get them with `git diff \"$(git merge-base origin/HEAD HEAD)\"` — resolve the base yourself; one ref, not a range, so the diff covers committed and uncommitted work together. Do not modify any test file that was present in the Phase 0 red-test commit; those are frozen. Before flagging an error-wrap, docstring, or boilerplate construct as redundant, grep 2–3 sibling functions in the same file — if the pattern is the established local convention, do NOT flag it."
)

Agent(
  subagent_type: "general-purpose",
  description: "Simplify: simplification",
  prompt: "<contents of skills/pr/references/pr-simplify-brief-simplification.md>\n\n<same diff, frozen-test, and sibling-convention instructions as above>"
)

Agent(
  subagent_type: "general-purpose",
  description: "Simplify: efficiency",
  prompt: "<contents of skills/pr/references/pr-simplify-brief-efficiency.md>\n\n<same diff, frozen-test, and sibling-convention instructions as above>"
)

Agent(
  subagent_type: "general-purpose",
  description: "Simplify: altitude",
  prompt: "<contents of skills/pr/references/pr-simplify-brief-altitude.md>\n\n<same diff, frozen-test, and sibling-convention instructions as above>"
)
```

Each brief is a file in this directory; read it and pass its contents as the prompt
prefix. The briefs defer to the repository's own `CLAUDE.md` for conventions and name no
language's rules, because one brief set serves every repository slopstop is installed in.

**No agent may be given a generated, vendored, or test-corpus path.** Each brief says so;
do not undercut it by naming such a path in the diff instructions.

## After simplify — capture and compare

```bash
git diff "$SIMPLIFY_BASE" > /tmp/pr-after-simplify.diff
```

Compare the two diffs:
- **Identical** — simplify found nothing to fix. Continue silently to Step 2.
- **Different** — simplify modified the working tree. Show the user the delta (`diff /tmp/pr-before-simplify.diff /tmp/pr-after-simplify.diff`, or just `git diff` against the snapshot reference) and ask:
  > simplify made the changes above. Continue with these incorporated, or abort to review/revert manually? (continue / abort)
  - On `continue`: proceed to Step 2.
  - On `abort`: stop. Remote state unchanged. The simplify changes remain in the working tree for the user to inspect/revert manually with `git checkout -p` or `git stash`.

## Write the `step_1` gate entry

Step 1 wrote no `gates.json` entry before BILL-429, so the simplify pass was the one gate
whose cost and outcome left no record — which is why the serial redesign's cost could not
be assessed from the tracking dir at all.

Record **one `agents[]` entry per spawn**, with the wall clock either side of it:

```json
"step_1": {
  "sha": "<head sha>", "result": "pass", "at": "<ISO-8601 Z>",
  "agents": [
    {"role": "reuse",          "started": "...", "ended": "...", "elapsed_s": 168},
    {"role": "simplification", "started": "...", "ended": "...", "elapsed_s": 117},
    {"role": "efficiency",     "started": "...", "ended": "...", "elapsed_s": 110},
    {"role": "altitude",       "started": "...", "ended": "...", "elapsed_s": 186}
  ]
}
```

`result` is `"pass"` when all four agents completed, `"fail"` if any errored — not a
judgment about whether they found anything. An `--inline` run records `result` normally
and sets `advisory.step_1.inline = true`; it has no `agents[]`.

Timestamps are facts, so they live in the gate entry rather than `advisory`. Do **not**
add a `"serial": true` field: whether the spawns overlapped is derivable from the
`started`/`ended` pairs, and a derived fact beats a self-assessment. See
`gates-json.md` § Timing fields.
