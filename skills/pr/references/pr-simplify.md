# PR Simplify Pass — Full Implementation (Step 1)

## Guard: sibling convention check

Before flagging an error-wrap, docstring, or boilerplate construct as redundant,
grep 2–3 sibling functions in the same file. If the pattern is the established
local convention, do NOT flag it — consistency with neighbors outranks local
terseness.

This guard applies to both the inline path and the agent invocation below.

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

## Inline simplify (when `--inline` was passed)

Skip the Agent spawn. Perform the simplify review directly:

1. Capture the branch diff: `git diff "$SIMPLIFY_BASE"` (save as `$INLINE_DIFF` — slop detection reuses it, and needs the same scope).
2. Review the diff and apply simplifications using the Edit tool. Apply the same criteria as the agent prompt in the "Agent invocation" section below (dead code, duplicated logic, over-eager defensive coding, unnecessary abstraction). Do NOT change behavior — only structure, readability, and redundancy.
3. Apply the same before/after comparison as the "After simplify" section below (identical → silent; different → show delta, ask `continue / abort`).

## Snapshot commands

```bash
git diff "$SIMPLIFY_BASE" > /tmp/pr-before-simplify.diff
```

## Agent invocation

```
Agent(
  subagent_type: "code-simplifier",
  description: "Simplify the branch's changes",
  prompt: "Review this branch's changes: run `git diff $SIMPLIFY_BASE` (one ref, not a range — it covers committed and uncommitted work together). Do not modify any test file that was present in the Phase 0 red-test commit; those are frozen. Identify and simplify dead code, duplicated logic, over-eager defensive coding, and unnecessary complexity that crept in during implementation. Apply the simplifications directly to the working tree. The user will review the resulting diff before committing. Do not change behavior — only structure, readability, and redundancy. Additionally, before flagging an error-wrap, docstring, or boilerplate construct as redundant, grep 2–3 sibling functions in the same file. If the pattern is the established local convention, do NOT flag it — consistency with neighbors outranks local terseness."
)
```

If the Agent tool reports `code-simplifier` is unavailable: print `"code-simplifier agent not available — install Claude Code's bundled agents, or proceed without it."` and ask `"Continue without simplify? (yes / no)"`. On `no`: stop.

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
