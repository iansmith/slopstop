# PR Simplify Pass — Full Implementation (Step 1)

## Guard: sibling convention check

Before flagging an error-wrap, docstring, or boilerplate construct as redundant,
grep 2–3 sibling functions in the same file. If the pattern is the established
local convention, do NOT flag it — consistency with neighbors outranks local
terseness.

This guard reaches each agent in `pr-simplify-brief-common.md`, which every invocation
below concatenates — an instruction that does not reach the agent does not bind it.

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

## `--inline` — an explicit opt-in, never a fallback

The agents exist to supply a context that has not spent the session rationalising the
code. Running Step 1 in the caller's session returns exactly the reviewer the isolation is
meant to exclude — so the mode is **chosen by the flag and never fallen into**:

- `--inline` **passed** → work the four dimensions in this session, one after another,
  applying each brief's fixes before starting the next. Required for fleet agents: `:run`
  launches them headless in a worktree, where sub-agent completion notifications route to
  the top-level loop instead of back to the spawning context (`run-agent-brief.md`,
  `design/slopstop-process.md`). Spawning there deadlocks the run, so inline is the only
  workable mode. Keep the before-diff in `$INLINE_DIFF`; Step 2e reuses it rather than
  re-deriving the base (`pr-slop-detection.md` § Inline slop detection).
- `--inline` **absent** → spawn. If the `Agent` tool is unavailable, **stop and say so.**
  Never simplify inline because spawning failed. A skipped simplify pass is visible; a
  self-reviewed one is not.

An inline run is a self-review, and its finding quality is not comparable to a spawned
one's. Record it as such: `advisory.step_1.inline = true` (see `gates-json.md`). This is
the same rule Step 6 follows, for the same reason — `pr-claude-review.md` § The rule this
step exists to enforce carries the history that produced it (PR #411), and the two must
not drift apart.

## Snapshot commands

```bash
git diff "$SIMPLIFY_BASE" > /tmp/pr-before-simplify.diff
INLINE_DIFF=/tmp/pr-before-simplify.diff
```

`$INLINE_DIFF` is set here, in both modes, because this is the only place the base is
resolved — Step 2e's inline path reads it rather than re-deriving `$SIMPLIFY_BASE` and
risking a different answer.

## Agent invocation — four briefs, one at a time (non-`--inline` only)

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
  prompt: "<contents of skills/pr/references/pr-simplify-brief-common.md>\n\n<contents of skills/pr/references/pr-simplify-brief-reuse.md>\n\nReview this branch's changes. Get them with `git diff <the resolved $SIMPLIFY_BASE sha>` — one ref, not a range, so the diff covers committed and uncommitted work together."
)

Agent(
  subagent_type: "general-purpose",
  description: "Simplify: simplification",
  prompt: "<contents of skills/pr/references/pr-simplify-brief-common.md>\n\n<contents of skills/pr/references/pr-simplify-brief-simplification.md>\n\n<same diff instructions as above>"
)

Agent(
  subagent_type: "general-purpose",
  description: "Simplify: efficiency",
  prompt: "<contents of skills/pr/references/pr-simplify-brief-common.md>\n\n<contents of skills/pr/references/pr-simplify-brief-efficiency.md>\n\n<same diff instructions as above>"
)

Agent(
  subagent_type: "general-purpose",
  description: "Simplify: altitude",
  prompt: "<contents of skills/pr/references/pr-simplify-brief-common.md>\n\n<contents of skills/pr/references/pr-simplify-brief-altitude.md>\n\n<same diff instructions as above>"
)
```

**Interpolate `$SIMPLIFY_BASE`; do not tell the agent to resolve the base itself.** You
already computed it above, so a re-deriving agent is four redundant derivations — and it
would derive a *different* base: `origin/HEAD` is the remote's default branch, which is
not `$ORIGIN_REMOTE/$BASE` on any run with a non-default base or a non-`origin` origin
remote. The agents would then simplify a diff the before/after snapshot never measured.

**Every invocation gets two briefs: the common one, then its dimension's.** Read the
common brief **once** and reuse that text across all four prompts — re-reading it per
spawn is three redundant reads of the same file. Pass the two as the prompt prefix, common
first. The common brief is where the frozen-test rule, the generated/vendored/test-corpus
prohibition, the behavior-preservation rule and the sibling-convention guard live — one
copy, so a change to a shared rule cannot land in three briefs and miss the fourth. Do not
restate them in the diff instructions, and do not undercut them by naming an off-limits
path there.

The briefs defer to the repository's own `CLAUDE.md` for conventions and name no
language's rules, because one brief set serves every repository slopstop is installed in.

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

`result` is `"pass"` when all four dimensions completed, `"fail"` if any errored — not a
judgment about whether they found anything. `agents[]` records **spawns**, so an
`--inline` run omits it entirely and carries `advisory.step_1.inline = true` instead;
a spawned run always has four entries.

Timestamps are facts, so they live in the gate entry rather than `advisory`. Do **not**
add a `"serial": true` field: whether the spawns overlapped is derivable from the
`started`/`ended` pairs, and a derived fact beats a self-assessment. See
`gates-json.md` § Timing fields.
