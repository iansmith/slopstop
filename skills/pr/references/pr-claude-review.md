# PR Claude Code Review — Full Implementation (Step 6-claude)

## Build args

Always include `--effort $PR_EFFORT --comment`. Add `--fix` if `$PR_FIX == true`.

## Skill invocation blocks

```
# $PR_FIX == false (default):
Skill({skill: "code-review", args: "--effort $PR_EFFORT --comment"})

# $PR_FIX == true:
Skill({skill: "code-review", args: "--effort $PR_EFFORT --comment --fix"})
```

`--comment` posts findings as inline PR comments directly on PR `#$PR`. `--fix` (only when `$PR_FIX == true`) applies fixable findings to the working tree.

## --fix working tree modification steps

**If `$PR_FIX == true` and the skill modified the working tree** (i.e. `git status --porcelain` is non-empty after the Skill call returns):

1. Run `/simplify` on changed files. Apply its findings.
2. Stage: `git add -A`
3. Commit with HEREDOC:
   ```
   git commit -m "$(cat <<'EOF'
   [$TICKET] code-review --fix (effort: $PR_EFFORT)

   Refs: $TICKET
   Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
   EOF
   )"
   ```
4. Push: `git push $PR_REMOTE $BRANCH`
5. Print: `"code-review --fix applied changes and committed. Pushed to update the PR."`

The code-review skill's own output is the review for this PR — its verdict structure replaces the CodeRabbit classify/present steps.

## Iterate-until-clean (when `$PR_FIX == true`)

*(Analogous loop for the CodeRabbit backend: Step 7e in `pr-verification-classification.md`.)*

When `$PR_FIX == false`: the review posts findings as inline PR comments and the skill stops. Continue to Step 8.

When `$PR_FIX == true`: after committing and pushing the first round of fixes, re-run the review and repeat until no new actionable findings remain.

Let `$ROUND = 1` after the initial `--fix` commit+push above.

### Per-iteration steps

1. Increment `$ROUND`.
2. Run: `Skill({skill: "code-review", args: "--effort $PR_EFFORT --fix"})` (no `--comment` on re-runs — the initial pass already posted inline comments; subsequent rounds apply fixes only to avoid duplicate comment threads).
3. If the skill modified the working tree (`git status --porcelain` non-empty):
   - Run `/simplify` on changed files. Apply its findings.
   - Stage and commit:
     ```
     git add -A
     git commit -m "$(cat <<'EOF'
     [$TICKET] code-review --fix (round $ROUND)

     Refs: $TICKET
     Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
     EOF
     )"
     ```
   - Push: `git push $PR_REMOTE $BRANCH`
   - Return to step 1.
4. If the working tree is unchanged (no new CONFIRMED or PLAUSIBLE findings were applied): exit loop.

### What gets applied vs. skipped

- **CONFIRMED + PLAUSIBLE** findings → applied.
- **REFUTED** findings → skipped.

### Exit conditions

- **Clean exit:** working tree unchanged after a `--fix` run → no actionable findings remain → continue to Step 8.
- **Max iterations:** 5 rounds total (including the first one before this loop). Exit when `$ROUND > 5` after incrementing. Continue to Step 8; any remaining CONFIRMED/PLAUSIBLE findings are not applied.
