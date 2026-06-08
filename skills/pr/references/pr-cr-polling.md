# PR CodeRabbit Polling — Full Implementation (Step 6-cr)

## First review vs. incremental re-review — the in-place-edit trap

> On the **first** review of a PR, CodeRabbit posts fresh artifacts: a Review object, maybe inline comments, and a new walkthrough issue-comment. On **every subsequent** review (i.e. after you push more commits), CodeRabbit does **NOT** post a new walkthrough and usually does **NOT** post a new Review object or new inline comments. Instead it **edits the SAME walkthrough issue-comment in place** — bumping its `updated_at`, rewriting the `## Walkthrough` body, and updating its `📥 Commits … between <old-head> and <new-head>` line to the new HEAD sha. A clean incremental pass leaves the body as `"No actionable comments were generated in the recent review."` with no other artifact at all.
>
> **Consequence:** a poll that merely counts "does any `coderabbitai[bot]` review / inline comment / walkthrough exist?" is **correct only for the first review**. On a re-poll it matches the **stale prior-review artifacts on iteration 1** and returns instantly — reporting the OLD feedback as if it were the review of your new commit, before CodeRabbit has even started the incremental pass. The fix is to gate completion on artifacts that reference **`$HEAD_SHA`** (the current commit), not on mere existence.

The reliable completion signal for both first and incremental reviews: a `coderabbitai[bot]` walkthrough issue-comment whose body both carries a walkthrough marker AND references `$HEAD_SHA`.

## Polling shell script

```bash
OWNER=$($GH repo view --json owner --jq .owner.login)
REPO=$($GH repo view --json name --jq .name)
HEAD_SHA=$(git rev-parse HEAD)   # gate on the commit we just pushed, not "any review"

for i in $(seq 1 20); do
  # PRIMARY gate: a walkthrough whose body references THIS head. Works for the
  # first review (new walkthrough) AND every incremental one (same comment edited
  # in place, its "between … and <HEAD>" line now naming $HEAD_SHA). A clean
  # incremental pass produces ONLY this — no Review object, no inline comments.
  # The "Currently processing" guard prevents a placeholder comment (which may
  # already embed $HEAD_SHA) from being mistaken for a completed review.
  head_reviewed=$($GH api "repos/$OWNER/$REPO/issues/$PR/comments" \
    --jq "[.[] | select(.user.login==\"coderabbitai[bot]\"
      and (.body | test(\"<!-- walkthrough_start -->|## Walkthrough|Summary by CodeRabbit|No actionable comments|Actionable comments posted\"))
      and (.body | contains(\"$HEAD_SHA\"))
      and (.body | test(\"[Cc]urrently processing\") | not))] | length")
  # FINDINGS on this head (filtered by commit_id so prior-review artifacts on an
  # older sha don't masquerade as this review's output).
  inline_count=$($GH api "repos/$OWNER/$REPO/pulls/$PR/comments" \
    --jq "[.[] | select(.user.login==\"coderabbitai[bot]\" and .commit_id==\"$HEAD_SHA\")] | length")
  review_count=$($GH api "repos/$OWNER/$REPO/pulls/$PR/reviews" \
    --jq "[.[] | select(.user.login==\"coderabbitai[bot]\" and .commit_id==\"$HEAD_SHA\")] | length")
  if [ "$head_reviewed" -gt 0 ] || [ "$inline_count" -gt 0 ] || [ "$review_count" -gt 0 ]; then
    if [ "$inline_count" -gt 0 ] || [ "$review_count" -gt 0 ]; then
      echo "CodeRabbit feedback received for $HEAD_SHA: $inline_count inline comments, $review_count finalized reviews"
    else
      echo "CodeRabbit review complete for $HEAD_SHA — no actionable comments"
    fi
    break
  fi
  echo "Waiting for CodeRabbit to review $HEAD_SHA ($i/20)..."
  sleep 60
done
```

## Timeout handling

**Timeout (20 iterations, no completion signal for `$HEAD_SHA`):** no walkthrough references the current head and no review/inline comment is stamped with it after 20 minutes. Likely causes: CodeRabbit isn't installed on the repo, the webhook is stuck/slow, the service is down, the PR's base isn't covered by CodeRabbit's config and the `@coderabbitai review` mention in Step 5c didn't take, OR (common on re-polls) the incremental pass simply hasn't landed yet. Before declaring timeout, cross-check the walkthrough's `updated_at` and its `📥 Commits` line directly — an in-place edit naming `$HEAD_SHA` is completion even if the strict `contains` check lagged. Print `"CodeRabbit didn't post a completion signal for $HEAD_SHA in 20 minutes. Check the PR page directly: $PR_URL. You can re-run /slopstop:pr later (with --no-simplify, since the commit is already made) to re-poll."` and skip to Step 7.

## Clean incremental pass note

When `head_reviewed > 0` but `inline_count == 0 && review_count == 0`, that is the normal shape of a clean re-review — CodeRabbit reviewed `$HEAD_SHA` and found nothing, recorded only in the in-place-edited walkthrough (typically `"No actionable comments were generated in the recent review."`). Route it to the clean path (7-pre / 7d-clean); do NOT re-surface the prior review's findings as if they were new.
