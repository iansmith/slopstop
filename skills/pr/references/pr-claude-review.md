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

1. Stage: `git add -A`
2. Commit with HEREDOC:
   ```
   git commit -m "$(cat <<'EOF'
   [$TICKET] code-review --fix (effort: $PR_EFFORT)

   Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
   EOF
   )"
   ```
3. Push: `git push origin $BRANCH`
4. Print: `"code-review --fix applied changes and committed. Pushed to update the PR."`

The code-review skill's own output is the review for this PR — its verdict structure replaces the CodeRabbit classify/present steps. Continue to Step 8.
