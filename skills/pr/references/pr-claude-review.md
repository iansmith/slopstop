# PR Claude Code Review — Full Implementation (Step 6-claude)

**Tier-gated:** on the `trivial` tier, Step 6 (this backend) is **skipped
unconditionally** — the tier alone decides, and no `gates.json` `step_6` entry needs to
exist (schema: `~/.claude/commands/slopstop-pr-refs/pr-size-classifier.md`). A sha-matched
entry licenses the separate *resume* skip on a re-run at an unchanged sha; it is never a
precondition of the tier skip. On `standard` and `large`, it always runs.

## The rule this step enforces

**The session that wrote the code never reviews it, and never decides which criticisms of
it are valid.**

PR #411 recorded `step_6: pass` from a review the authoring session performed on its own
work. The trigger was a name collision; the cause was that this file gated its isolation on
a flag, so nothing defined what happened when the flag was absent — and the answer it fell
into was "review yourself."

That whole class of failure is now closed by construction. `/slopstop:review` carries
`context: fork` in its frontmatter, so it runs in a subagent with **no access to this
conversation**. There is no flag to omit and no fallback to fall into.

**Nothing here invokes the built-in `/code-review`.** That skill is
`disable-model-invocation` — only a human typing it can launch it — so every call site that
appeared to was inert. It is the right tool when a human is at the keyboard; it is not
reachable from a skill, which is why this one exists.

## The loop

```
$ROUND = 1
loop:
  verdict = Skill(skill: "slopstop:review",
                  args: "--scope $PR --mode <autonomous|interactive> --frozen $RED_SHA")

  REVIEW BLOCKED: <r>  -> exit "blocked", surface <r>, do not retry
  REVIEW CLEAN         -> exit "converged"
  REVIEW APPLIED: <n>  -> commit and push this round's fixes
  anything else        -> exit "blocked", surface the raw verdict — never assume it applied

  if $ROUND >= 5       -> exit "capped", report the findings from the LAST round
  $ROUND += 1
```

**Commit before the cap check, not after.** The fork applies with `Edit` and never hands
findings back, so a cap that fires first leaves round 5's fixes — including confirmed 🔴 —
uncommitted in the working tree, and nothing downstream commits them.

**Pass the scope, mode and frozen sha explicitly.** The fork has no conversation history:
`$PR`, `$BASE` and `$RED_SHA` are unreachable from inside it. A fork left to guess falls
back to `origin/HEAD` — the remote's *default* branch, not this PR's base — which is the
same defect the Phase 0 suite pins as a forbidden token.

**Each round is a fresh fork.** Round N+1 has no memory of round N, so it can neither
defend nor rationalise the previous round's fixes — stronger isolation than one context
carrying every round, which is what the hand-built version did.

**The cap is 5 and it lives here**, not in Step 7e. 7e is the bot backends' loop (`pr/SKILL.md`
Step 7: "Bot backends only; the Claude path skips to Step 7f"), so a Claude-path counter
delegated there would never initialise — the cap simply would not exist. Do not delegate it.

On a **capped** exit, report every remaining finding, unapplied. A capped run that reads as
converged is the failure the bound exists to make visible.

## Commit and push each round

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

Do not run a separate cleanup pass here. The review covers reuse, simplification,
efficiency and altitude in the same round it covers correctness.

## Scope, mode and the frozen baseline are arguments

The fork has no conversation history, so nothing it needs is ambient. Pass all three:
`--scope` (the PR number or ref range), `--mode` (`autonomous` when `[autonomous] enabled`,
else `interactive`), and `--frozen` (the Phase 0 red-test sha — derive it as
`pr-slop-detection.md` § Step 2d does, scoped to this branch, never by grepping all of
history).

## Effort and model

Both are set in `skills/review/SKILL.md`'s frontmatter (`model:`, `effort:`). Frontmatter is
the only channel that reaches a **forked** skill, which is why `$PR_EFFORT` has no consumer
on this path. Change the tier by editing the skill's frontmatter, not by adding a flag here.

The `Agent` tool has no `effort` *parameter*, but that never meant effort was unreachable —
a subagent definition's frontmatter carries it, and absent one a spawn inherits the invoking
session's effort. See `design/agent-effort-capability.md`.

## Every mode, one path

A forked skill behaves identically in an interactive session, an autonomous run, and a
headless fleet agent. Probed 2026-08-04: `claude -p "/<forked skill>"` inside a git
worktree ran to completion — exit 0, `NO_HISTORY`, its own subagent transcript. Under `-p`
the harness waits for a fork synchronously, so the background-notification routing that
deadlocks a worktree agent never arises.

There is therefore **no `--inline` variant of this step and no per-backend divergence.** If
the fork cannot run, stop and say so; never review in this session instead.

## Gate entry

Write `step_6` to `$TRACKING_DIR/$TICKET/gates.json` (schema:
`~/.claude/commands/slopstop-start-refs/gates-json.md`) once the loop exits — `"pass"` when
it converged, `"fail"` when it exited capped or blocked with findings outstanding.

Record a `rounds[]` entry per round (`round`, `started`, `ended`, `elapsed_s`, `applied`)
and an `exit` of `converged` | `capped` | `blocked`. Both are defined in
`gates-json.md` § `rounds` and `exit`. `exit` is not optional: `result: "pass"` cannot
distinguish a run that converged from one that hit the cap, and that distinction is the
whole reason the bound exists.

## Exit

Continue to Step 7f. Report: rounds run, findings applied, findings reported for human
judgment, findings refuted, and the exit condition.
