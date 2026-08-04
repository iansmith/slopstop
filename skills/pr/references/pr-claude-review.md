# PR Claude Code Review — Full Implementation (Step 6-claude)

**Tier-gated:** on the `trivial` tier, Step 6 (this backend) is **skipped
unconditionally** — the tier alone decides, and no `gates.json` `step_6` entry needs to
exist (schema: `~/.claude/commands/slopstop-pr-refs/pr-size-classifier.md`). A sha-matched
entry licenses the separate *resume* skip on a re-run at an unchanged sha; it is never a
precondition of the tier skip. On `standard` and `large`, it always runs.

Write a `step_6` entry to `$TRACKING_DIR/$TICKET/gates.json` (schema:
`~/.claude/commands/slopstop-start-refs/gates-json.md`) once the cycle below reaches its
exit condition — `"pass"` when no confirmed 🔴 finding remains, `"fail"` otherwise.

## The rule this step exists to enforce

**No agent in this step runs in the caller's session, and the caller never adjudicates a
finding.**

PR #411 recorded `step_6: pass` from a review the authoring session performed on its own
code. The trigger was a name collision; the cause was that this file gated its inline
path on `--inline` being passed, so nothing defined what to do when the backend was
simply absent — and the answer it fell into was "review yourself."

The defect was never that an inline path existed; it was the undefined case falling into
one. Defining it is the whole fix — **`--inline` is an explicit opt-in, never a fallback:**

- `--inline` **passed** → review inline. Required for fleet agents: `:run` launches them
  headless in a worktree, where sub-agent completion notifications route to the top-level
  loop instead of back to the spawning context (`run-agent-brief.md`, `design/slopstop-process.md`).
  Spawning there deadlocks the run, so inline is the only workable mode.
- `--inline` **absent** → spawn. If the `Agent` tool is unavailable, **stop and say so**.
  Never review inline because spawning failed.

An inline run is a self-review, and its finding quality is not comparable to a spawned
one. Record it as such: `advisory.step_6.inline = true` (see `gates-json.md`). A fleet
agent's review is a first pass, not the merge gate — `:run`'s own Step 6 review is the
backstop, and it spawns.

Nothing here invokes the built-in `/code-review` either. That skill is
`disable-model-invocation` — a skill cannot launch it, only a human typing it can — so
every call site that appeared to do so was inert. It is not a fallback.

## Scope

```bash
gh pr diff #$PR      # or: git diff origin/$BASE..HEAD
```

**This scope is deliberate and is not the Step 1 / Step 2e bug.** Review reads the PR —
the branch as pushed — and is independent of working-tree state, so it was unaffected
when simplify and slop detection were found to skip on a clean tree (BILL-337). A range
is correct *here* precisely because the PR is the artifact under review; Step 1 and Step
2e need the one-ref merge-base form instead, because they run before the commit and must
see uncommitted work too. Do not "fix" this into consistency with them.

## The cycle — find, score, apply

Three agent roles, all `general-purpose`, all clean-context. Each role is a **separate
spawn**: a context that found a finding is not the context that decides whether it is
real, and neither is the context that fixes it.

### 1. Find — parallel, read-only

Spawn one agent per dimension, **concurrently**:

```
Agent(subagent_type: "general-purpose", description: "Review: correctness",
      prompt: "<contents of pr-review-brief-common.md>\n\n<contents of pr-review-brief-correctness.md>\n\nReview this PR's changes. Get them with `gh pr diff <$PR, interpolated>` — the § Scope command above.")

Agent(subagent_type: "general-purpose", description: "Review: reuse",
      prompt: "<contents of pr-review-brief-common.md>\n\n<contents of pr-review-brief-reuse.md>\n\n<same diff instructions as above>")

Agent(subagent_type: "general-purpose", description: "Review: efficiency",
      prompt: "<contents of pr-review-brief-common.md>\n\n<contents of pr-review-brief-efficiency.md>\n\n<same diff instructions as above>")
```

**Pass the diff *command*, not the diff.** Each agent fetches the same bytes either way,
but embedding them means this session must first load the whole diff into its own context
and then retransmit it three times. A 1300-line diff runs ~110 KB — roughly 27k tokens of
caller context, per round, spent on bytes the caller never reads. Step 1's dispatch
already passes a command for this reason.

**Every invocation gets two briefs: the common one, then its dimension's.** Both are files
in this directory. Read the common brief **once** and reuse that text across all three
prompts; pass the two as the prompt prefix, common first.
`pr-review-brief-common.md` is where the no-write prohibition, the repository-rules
pointer, the scope, and the report format live — one copy, so a change to a shared rule
cannot land in two briefs and miss the third.

**Do not substitute Step 1's `pr-simplify-brief-*.md` files**, despite the overlapping
dimension names: those instruct the agent to *apply its own fixes to the working tree*,
which would put three concurrent writers in the one step whose safety argument is that
find agents do not write.

**Find agents must not write.** That is a requirement, not a description: parallelism is
safe here *only* because these agents do not touch the tree. An agent that "helpfully"
applies a fix breaks the argument for running them concurrently, and races the others.
The common brief opens with that prohibition, and each dimension brief stops the agent if
the common brief did not arrive; do not undercut either in the diff instructions.

**No effort level can be passed here.** The `Agent` tool schema has no `effort`
parameter (`design/agent-effort-capability.md`), so `$PR_EFFORT` has no consumer on this
path — the `/code-review` invocation that used to carry it is gone. What *is* controllable
is `model`, via `[stage_tiers].review` (#433). Do not reintroduce an `--effort` flag here
expecting it to reach an agent.

Each returns findings with file, line, a one-line summary, and the concrete failure the
finding predicts.

### 2. Score — separate agents, one per finding, parallel

For each finding, spawn a **fresh** agent to score it. It reads the actual code at the
cited line and verifies the finding's premise — the same discipline
`pr-verification-classification.md` already requires for bot comments.

**Spawn them concurrently.** Scoring is read-only and each finding is scored against the
code independently, so the find agents' safety argument applies unchanged — and it is the
same argument, so a scoring agent must not write either. Serial scoring costs the sum:
ten findings at the ~40s a scoring agent takes is ~7 min per round instead of ~40s, and
that repeats every round up to the cap. Only the **fix** agents in step 3 must be serial,
because only they write.

- **confirmed** — the agent reproduced the premise against the real code.
- **not confirmed** — it could not. This includes "plausible but unverified."

**Plausible is not confirmed.** A finding nobody could substantiate is not acted on, in
either mode. Acting on an unverified finding is the same defect as dismissing a verified
one, pointed the other way.

Classify each confirmed finding 🔴 should-fix / 🟡 could-fix / ⚪ skip.

### 3. Apply — serial, one fresh agent per finding

**The severity routing table lives in `pr-verification-classification.md`** — it is the
shared classifier all three backends defer to, and duplicating it here is how the two
copies came to disagree about autonomous ⚪ within a single commit. Read it there:
→ `~/.claude/commands/slopstop-pr-refs/pr-verification-classification.md`

The two rules it encodes, restated because they are the ticket's point and a reader must
not have to follow a pointer to learn them: **a confirmed 🔴 is never left unfixed, in
either mode**, and **an unconfirmed finding is never fixed, in either mode.**

Fix agents **write, so they run serially** — identical reasoning to Step 1's four
appliers, and the identical failure if ignored. One fresh agent per finding, each given
the finding and the cited code, applying its own fix.

**This session does not apply findings, and does not filter them.** Every finding that
was refuted is recorded with the reason it was refuted; none is silently dropped.

## Commit and push each round

After a round's fix agents complete and `git status --porcelain` is non-empty:

```
git add -A
git commit -m "$(cat <<'EOF'
[$TICKET] code review round $ROUND

Refs: $TICKET
Co-Authored-By: Claude <model> using slopstop <noreply@anthropic.com>
EOF
)"
git push $PR_REMOTE $BRANCH
```

Do not run `/simplify` here. Step 1 already ran, and re-running it inside the review loop
puts a quality pass on top of unreviewed fixes every round.

## Termination — one cap, owned by 7e

**Do not add a counter here.** The 5-round cap lives in `pr-verification-classification.md`
Step 7e and is shared by all three backends; a second `$ROUND` in this file collides with
it by name and counts different things (finds vs applies). The earlier draft of this file
did exactly that while asserting the cap was shared.

Exit conditions, as 7e defines them:

1. A round producing **no new confirmed findings** — converged.
2. `$ROUND > 5` — capped.

**Record which exit was taken.** On a cap exit, report every remaining finding, unapplied.
A capped run that looks like a converged one is the failure the bound exists to make
visible; silently dropping the remainder is worse than the loop.

Round count and exit condition are written to `advisory.step_6` — they are the step's own
account of itself. **Timing goes in the `step_6` gate entry proper**, since a measured
elapsed time is a fact rather than a claim:

```json
"step_6": {
  "sha": "<head sha>", "result": "pass", "at": "<ISO-8601 Z>",
  "agents": [
    {"role": "find:correctness", "round": 1, "started": "...", "ended": "...", "elapsed_s": 96},
    {"role": "score:3",          "round": 1, "started": "...", "ended": "...", "elapsed_s": 41},
    {"role": "fix:3",            "round": 1, "started": "...", "ended": "...", "elapsed_s": 133}
  ],
  "rounds": [{"round": 1, "started": "...", "ended": "...", "elapsed_s": 412}]
}
```

This is the step where cost can run away: one scoring agent and one *serial* fix agent per
finding, up to 5 rounds. Ten findings at ~2.5 min each is ~25 min of serial fix time per
round before the cap is even approached. Record every spawn — a round total alone hides
which role is expensive. See `gates-json.md` § Timing fields.

## Exit

Continue to Step 7f. Report: findings found / confirmed / applied / refuted, the round
count, and which exit condition ended the cycle.
