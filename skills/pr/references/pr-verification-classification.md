# PR Verification and Classification — Full Process (Step 7)

## 7-pre. Zero-findings fast path

If Step 6 broke on `head_reviewed` alone (i.e. `inline_count == 0` AND `review_count == 0` for `$HEAD_SHA`), skip the verification + decision tree (there's nothing to classify) and go straight to the **clean-verdict presentation** at 7d-clean below. This is the common shape of a clean incremental re-review (the walkthrough was edited in place; no review/inline artifact was posted). Fetch only the walkthrough comment for the optional excerpt; skip the inline + review fetches.

## 7-full. Full-findings path — fetch commands

Fetch CodeRabbit's findings **for the current head** — filter by `commit_id == $HEAD_SHA` so a prior review's artifacts on an older sha don't get re-presented:

```bash
# Inline review comments (the substantive line-level suggestions) — current head only
$GH api "repos/$OWNER/$REPO/pulls/$PR/comments" \
  --jq "[.[] | select(.user.login==\"coderabbitai[bot]\" and .commit_id==\"$HEAD_SHA\") | {path, line, body, diff_hunk}]"

# Review summaries (state, body, timestamp) — current head only
$GH api "repos/$OWNER/$REPO/pulls/$PR/reviews" \
  --jq "[.[] | select(.user.login==\"coderabbitai[bot]\" and .commit_id==\"$HEAD_SHA\") | {state, body, submitted_at}]"

# The walkthrough issue-comment (single comment, edited in place across reviews —
# do NOT filter by commit_id; it has none. Take the coderabbit walkthrough whose
# body references $HEAD_SHA).
$GH api "repos/$OWNER/$REPO/issues/$PR/comments" \
  --jq "[.[] | select(.user.login==\"coderabbitai[bot]\" and (.body | contains(\"$HEAD_SHA\"))) | {body, updated_at}]"
```

> **Caveat — unresolved findings from a PRIOR head.** Filtering by `commit_id == $HEAD_SHA` shows only what CodeRabbit flagged on the latest commit. Inline comments from an earlier review that you neither fixed nor resolved still hang on the PR under their old `commit_id` and won't appear in the filtered fetch. If the current head is clean but you want to double-check nothing earlier was dropped, re-run the inline fetch without the `commit_id` filter and look for unresolved (`in_reply_to_id == null`, not outdated) comments. Mention any you find rather than silently omitting them.

## 7a. Read the actual code

Before judging, open the file CodeRabbit is commenting on (use `path` and `line` from the comment, plus 20–30 lines of surrounding context). For "X is unused" or codebase-pattern claims, also grep the broader repo for the symbol or pattern. The classification must be grounded in what the code actually does, not what CodeRabbit asserts it does.

## 7b. Verify CodeRabbit's premise

Common failure modes — check whichever applies:

| CodeRabbit claim | How to verify |
|---|---|
| "X is unused / dead code" | `grep -r "<symbol>"` across the repo (and across reverse deps if it's an exported API). Could be called via reflection, plugin registry, dynamic dispatch. |
| "X can be null / undefined" | Check the type signature / contract. Is the input actually nullable, or is non-null guaranteed upstream? |
| "Missing await" | Is the called function actually async? Read its signature. |
| "Use idiom Y instead of Z" | Grep neighboring files. Does the codebase use Y or Z? The codebase's existing convention wins over generic best practice. |
| "X is a security risk" | Is the input actually attacker-controlled at this call site? An internal-only function with internal-only inputs isn't a security risk regardless of how the operation looks. |
| "Race condition" | Is concurrent access actually possible here, or is the call site single-threaded by construction? |

If CodeRabbit's premise turns out to be **false**, the verdict is **⚪ Skip — "premise wrong: <specifics>"** and you stop processing this comment.

## 7c. Classify by decision tree

If the premise checks out, apply these questions in order. The first one that matches wins:

1. **Does the suggestion fix a bug, security issue, data loss, or runtime crash?**
   Concrete failure mode (off-by-one in a slice that returns wrong data, SQL injection, silently-swallowed error that should propagate, missing null check that crashes on real input).
   → **🔴 Should fix**

2. **Does the suggestion contradict an established pattern in the codebase?**
   Check neighboring files. If the codebase consistently uses approach X and CodeRabbit suggests Y, codebase wins. (Consistency has more compounding value than any single generic best practice.)
   → **⚪ Skip — "contradicts convention: <file you checked>"**

3. **Is it a clear improvement with positive ROI?**
   Simpler code, fewer edge cases, removes a dependency, better error message, a test for a real edge case (not a speculative one).
   → **🟡 Could fix**

4. **Is it a pure stylistic nit with no functional benefit?**
   "Consider renaming foo to fooValue", "extract this 3-line block to a helper", "use template literal instead of string concat" (when both are equivalent in context).
   → **⚪ Skip — "stylistic nit, no functional benefit"**

5. **Otherwise** (legitimate refactor that's not strictly better, speculative test coverage, documentation that's nice-to-have):
   → **🟡 Could fix** (default to optional)

## 7d. Present format

```
CodeRabbit review of PR #$PR — $N inline comments, $M finalized reviews

🔴 Should fix ($N1):

  📄 <file>:<line>
     CodeRabbit: "<first ~120 chars of the comment body, with a trailing … if truncated>"
     Verdict:    <one-line summary of the recommended fix>
     Why:        <reasoning, including any verification you did (e.g. "confirmed the symbol is only used here")>

  📄 <file>:<line>
     ...

🟡 Could fix ($N2):

  📄 <file>:<line>
     CodeRabbit: "..."
     Verdict:    ...
     Why:        ...

⚪ Skip ($N3):

  📄 <file>:<line>
     CodeRabbit: "..."
     Verdict:    Skip
     Why:        <"premise wrong: ..." | "contradicts convention: ..." | "stylistic nit, no functional benefit">

Walkthrough summary:
<excerpt of the walkthrough comment if it adds useful context beyond the inline comments — otherwise omit this section>

PR: $PR_URL
```

After presenting: if any 🔴 or 🟡 findings exist → proceed to **Step 7e** (fix-and-iterate loop). If only ⚪ findings remain or none → continue to Step 8.

## 7d-clean. Clean-verdict presentation (zero-findings fast path + loop exit)

```
CodeRabbit review of PR #$PR — clean ✅

CodeRabbit found no actionable comments to address.

<optional: paste the "Summary by CodeRabbit" section of the walkthrough comment verbatim, indented 2 spaces, if the user might want context on what CodeRabbit looked at. Omit if the walkthrough is just generic acknowledgement text.>

PR: $PR_URL
```

Continue to Step 8. *(This path is also the loop exit for Step 7e — when a re-review returns clean, the loop ends here.)*

## Step 7e — Fix-and-iterate loop (🔴 and 🟡 findings)

Runs after Step 7d when any 🔴 or 🟡 findings are present. Applies all actionable findings, re-polls, and repeats until CodeRabbit returns clean.

### Per-iteration steps

Let `$ROUND = 1` on first entry. Increment at the top of each subsequent iteration.

1. **Apply findings** — for each 🔴 and 🟡 finding in the Step 7d output, edit the file at the cited location to apply the fix. Read 20–30 lines of context first; implement the fix CodeRabbit described. ⚪ findings are NOT applied — skip them entirely.

2. **Simplify** — invoke the `simplify` skill on the changed files. Apply any findings it returns.

3. **Commit:**
   ```
   git add -A
   git commit -m "$(cat <<'EOF'
   [$TICKET] Fix CR findings (round $ROUND)

   Refs: $TICKET
   Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
   EOF
   )"
   ```

4. **Push:** `git push $PR_REMOTE $BRANCH`

5. **Update `$HEAD_SHA`:** `HEAD_SHA=$(git rev-parse HEAD)`

6. **Re-poll** — jump back to **Step 6-cr** with the new `$HEAD_SHA`. The polling loop will wait for CodeRabbit to process the new commit.

### Exit conditions

- **Clean exit:** the re-poll fires 7d-clean (CodeRabbit returns "no actionable comments" for the current `$HEAD_SHA`) → exit loop → continue to Step 8.
- **Only ⚪ remain:** after applying all 🔴/🟡 findings, if the next round returns only ⚪ verdicts → exit loop → continue to Step 8 (present the ⚪ findings as-is for human review).
- **Max iterations:** after 5 fix-and-push cycles, exit the loop regardless. Surface any remaining 🔴/🟡 findings and continue to Step 8 with a note: `"Loop limit reached after 5 rounds — N finding(s) remain. Address manually."`

### Notes

- **Re-review inline-edit behavior:** on 2nd+ rounds, CodeRabbit edits its inline comments in place (original `commit_id` is preserved). The `all_cr_inline` (unfiltered) count drives findings routing — this is handled correctly in the polling script (pr-cr-polling.md). Do NOT re-surface ⚪ findings from prior rounds.
- **Commit identity:** each round gets its own commit so `git bisect` can trace exactly which CR finding introduced each change.
