# PR Simplify Pass — Full Implementation (Step 1)

## Snapshot commands

```bash
git diff > /tmp/pr-before-simplify.diff && git diff --staged >> /tmp/pr-before-simplify.diff
```

## Agent invocation

```
Agent(
  subagent_type: "code-simplifier",
  description: "Simplify uncommitted changes",
  prompt: "Review the uncommitted changes in this working tree (against HEAD). Identify and simplify dead code, duplicated logic, over-eager defensive coding, and unnecessary complexity that crept in during implementation. Apply the simplifications directly to the working tree. The user will review the resulting diff before committing. Do not change behavior — only structure, readability, and redundancy."
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
