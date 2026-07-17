# PR Claude Code Review — Full Implementation (Step 6-claude)

## Inline code review (when `--inline` was passed)

Skip the Skill invocation. Perform the review directly:

1. Get the PR diff: `gh pr diff #$PR` (or `git diff origin/$BASE..HEAD`).
2. Review the diff inline across three dimensions:
   - **Correctness bugs** — off-by-one, null dereference, race condition, wrong logic
   - **Reuse/simplification** — duplicated logic, unnecessary indirection, dead code
   - **Efficiency** — algorithmic issues, unnecessary allocations, blocking in hot paths
3. For each finding: record file, line, verdict (CONFIRMED / PLAUSIBLE / REFUTED), description.
4. Apply CONFIRMED and PLAUSIBLE findings:
   - If `$PR_FIX == true`: apply fixes with Edit tool. Simplify changed sections inline (do NOT call `/simplify` — that spawns an agent). Stage, commit, push using the same commit format as the normal `--fix` flow. Re-run the inline review up to 4 additional rounds until no new CONFIRMED/PLAUSIBLE findings remain.
   - If `$PR_FIX == false`: post findings as a consolidated PR comment: `gh pr comment #$PR --body "..."`.
5. `--comment` in inline mode posts a single consolidated comment rather than per-line diff comments (per-line targeting requires the multi-agent workflow's line-mapping pass).

Exit: if no CONFIRMED or PLAUSIBLE findings after the initial pass, print `"Inline code review: clean ✅"` and continue to Step 7f.

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

When `$PR_FIX == false`: the review posts findings as inline PR comments and the skill stops. Continue to Step 7f.

When `$PR_FIX == true` and the working tree was **unchanged** after the initial `--fix` run: the branch is already clean — continue to Step 7f.

## Iterate-until-clean (when `$PR_FIX == true`)

*(Analogous loop for the CodeRabbit backend: Step 7e in `pr-verification-classification.md`.)*

Runs only after the initial `--fix` commit+push (steps 1–5 above). Re-runs the review and repeats until no new actionable findings remain.

Let `$ROUND = 1` after the initial `--fix` commit+push above.

### Per-iteration steps

1. Increment `$ROUND`. If `$ROUND > 5`: exit the loop — continue to Step 7f; any remaining CONFIRMED/PLAUSIBLE findings are not applied.
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
   - Return to **Per-iteration step 1** (Increment `$ROUND`).
4. If the working tree is unchanged (no new CONFIRMED or PLAUSIBLE findings were applied): exit loop.

### What gets applied vs. skipped

- **CONFIRMED + PLAUSIBLE** findings → applied.
- **REFUTED** findings → skipped.

### Exit conditions

- **Clean exit:** working tree unchanged after a `--fix` run → no actionable findings remain → continue to Step 7f.
- **Max iterations:** the pre-loop commit is round 1; this loop runs at most 4 more (rounds 2–5).
