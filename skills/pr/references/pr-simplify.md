# PR Simplify Pass — Full Implementation (Step 1)

## Guard: sibling convention check

Before flagging an error-wrap, docstring, or boilerplate construct as redundant,
grep 2–3 sibling functions in the same file. If the pattern is the established
local convention, do NOT flag it — consistency with neighbors outranks local
terseness.

This guard applies to both the inline path and the agent invocation below.

## Inline simplify (when `--inline` was passed)

Skip the Agent spawn. Perform the simplify review directly:

1. Capture the working-tree diff: `git diff HEAD` (save as `$INLINE_DIFF` — slop detection reuses it).
2. Review the diff and apply simplifications using the Edit tool. Apply the same criteria as the agent prompt in the "Agent invocation" section below (dead code, duplicated logic, over-eager defensive coding, unnecessary abstraction). Do NOT change behavior — only structure, readability, and redundancy.
3. Apply the same before/after comparison as the "After simplify" section below (identical → silent; different → show delta, ask `continue / abort`).

## Snapshot commands

```bash
git diff > /tmp/pr-before-simplify.diff && git diff --staged >> /tmp/pr-before-simplify.diff
```

## Agent invocation

```
Agent(
  subagent_type: "code-simplifier",
  description: "Simplify uncommitted changes",
  prompt: "Review the uncommitted changes in this working tree (against HEAD). Identify and simplify dead code, duplicated logic, over-eager defensive coding, and unnecessary complexity that crept in during implementation. Apply the simplifications directly to the working tree. The user will review the resulting diff before committing. Do not change behavior — only structure, readability, and redundancy. Additionally, before flagging an error-wrap, docstring, or boilerplate construct as redundant, grep 2–3 sibling functions in the same file. If the pattern is the established local convention, do NOT flag it — consistency with neighbors outranks local terseness."
)
```

If the Agent tool reports `code-simplifier` is unavailable: print `"code-simplifier agent not available — install Claude Code's bundled agents, or proceed without it."` and ask `"Continue without simplify? (yes / no)"`. On `no`: stop.

## After simplify — capture and compare

```bash
git diff > /tmp/pr-after-simplify.diff && git diff --staged >> /tmp/pr-after-simplify.diff
```

Compare the two diffs:
- **Identical** — simplify found nothing to fix. Continue silently to Step 2.
- **Different** — simplify modified the working tree. Show the user the delta (`diff /tmp/pr-before-simplify.diff /tmp/pr-after-simplify.diff`, or just `git diff` against the snapshot reference) and ask:
  > simplify made the changes above. Continue with these incorporated, or abort to review/revert manually? (continue / abort)
  - On `continue`: proceed to Step 2.
  - On `abort`: stop. Remote state unchanged. The simplify changes remain in the working tree for the user to inspect/revert manually with `git checkout -p` or `git stash`.
