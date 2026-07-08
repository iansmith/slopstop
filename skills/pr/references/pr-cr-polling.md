# PR CodeRabbit Polling — Full Implementation (Step 6-cr)

## First review vs. incremental re-review — the in-place-edit trap

> On the **first** review of a PR, CodeRabbit posts fresh artifacts: a Review object, maybe inline comments, and a new walkthrough issue-comment. On **every subsequent** review (i.e. after you push more commits), CodeRabbit does **NOT** post a new walkthrough and usually does **NOT** post a new Review object or new inline comments. Instead it **edits artifacts in place**:
>
> - **Walkthrough issue-comment:** edited in place — bumping its `updated_at`, rewriting the `## Walkthrough` body, and updating its `📥 Commits … between <old-head> and <new-head>` line to the new HEAD sha. A clean incremental pass leaves the body as `"No actionable comments were generated in the recent review."`.
> - **Inline review comments:** also edited in place — CR updates the body of the original comment. The `commit_id` field on those comments **stays as the original (first-push) SHA**, not the new HEAD sha.
>
> **Consequence:** a poll that merely counts "does any `coderabbitai[bot]` review / inline comment / walkthrough exist?" is **correct only for the first review**. On a re-poll it matches the **stale prior-review artifacts on iteration 1** and returns instantly — reporting the OLD feedback as if it were the review of your new commit, before CodeRabbit has even started the incremental pass. The fix is to gate completion on artifacts that reference **`$HEAD_SHA`** (the current commit), not on mere existence.
>
> **Second consequence — findings routing:** because inline comments retain the original `commit_id` after an in-place edit, the `inline_count` query (filtered on `commit_id == $HEAD_SHA`) returns **0** even when real findings exist. Do **not** use `inline_count == 0` alone to conclude a re-review is clean. After the completion signal fires, fetch all CR inline comments unfiltered to determine whether findings exist (see post-loop check below).

The reliable completion signal for both first and incremental reviews: a `coderabbitai[bot]` walkthrough issue-comment whose body both carries a walkthrough marker AND references `$HEAD_SHA`.

## Execution model — required

**Never run this poll in the foreground.** The Bash tool has a 10-minute hard cap; the 20-iteration loop takes up to 20 minutes and will be killed around iteration 10, reporting a false timeout.

**Required execution:**
1. Create a `STATUS_FILE` path before launching: e.g. `STATUS_FILE=$(mktemp /tmp/cr-poll-XXXXXX.txt)`.
2. Launch the poll script as a **background** Bash command: `run_in_background: true`, `timeout: 1200000` (20 min in ms).
3. When the background command finishes, you are re-invoked via a completion notification.
4. Read `$STATUS_FILE` — the last line is one of:
   - `DONE iter=N clean` — CR reviewed, no actionable comments.
   - `DONE iter=N all_cr_inline=M review_count=K` — CR reviewed, M inline findings.
   - `TIMEOUT iter=20` — no CR completion signal within 20 minutes.

**Status file example:**
```
START 2026-07-08T10:00:00Z HEAD=abc1234
WAIT iter=1/20 2026-07-08T10:01:01Z
WAIT iter=2/20 2026-07-08T10:02:03Z
DONE iter=5 all_cr_inline=3 review_count=0
```

## Polling shell script

```bash
OWNER=$($GH repo view --json owner --jq .owner.login)
REPO=$($GH repo view --json name --jq .name)
HEAD_SHA=$(git rev-parse HEAD)   # gate on the commit we just pushed, not "any review"

# STATUS_FILE must be set by the caller before launching this as a background command.
# (run_in_background: true, timeout: 1200000)
echo "START $(date -u +%Y-%m-%dT%H:%M:%SZ) HEAD=$HEAD_SHA" >> "$STATUS_FILE"
completed=0

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
  # Fetch all CR inline comments once and derive two counts:
  #   inline_count  — commit_id-filtered, drives completion detection on first reviews
  #   all_cr_inline — unfiltered, used post-loop for findings routing (on re-reviews CR
  #                   edits comments in place, so commit_id stays the original sha)
  _cr_pr_comments=$($GH api "repos/$OWNER/$REPO/pulls/$PR/comments" \
    --jq "[.[] | select(.user.login==\"coderabbitai[bot]\")]")
  inline_count=$(printf '%s' "$_cr_pr_comments" | jq "[.[] | select(.commit_id==\"$HEAD_SHA\")] | length")
  all_cr_inline=$(printf '%s' "$_cr_pr_comments" | jq "length")
  review_count=$($GH api "repos/$OWNER/$REPO/pulls/$PR/reviews" \
    --jq "[.[] | select(.user.login==\"coderabbitai[bot]\" and .commit_id==\"$HEAD_SHA\")] | length")
  if [ "$head_reviewed" -gt 0 ] || [ "$inline_count" -gt 0 ] || [ "$review_count" -gt 0 ]; then
    if [ "$all_cr_inline" -gt 0 ] || [ "$review_count" -gt 0 ]; then
      echo "CodeRabbit feedback received for $HEAD_SHA: $all_cr_inline inline comments, $review_count finalized reviews"
      echo "DONE iter=$i all_cr_inline=$all_cr_inline review_count=$review_count" >> "$STATUS_FILE"
    else
      echo "CodeRabbit review complete for $HEAD_SHA — no actionable comments"
      echo "DONE iter=$i clean" >> "$STATUS_FILE"
    fi
    completed=1
    break
  fi
  echo "WAIT iter=$i/20 $(date -u +%Y-%m-%dT%H:%M:%SZ)" >> "$STATUS_FILE"
  echo "Waiting for CodeRabbit to review $HEAD_SHA ($i/20)..."
  sleep 60
done

# If the loop exhausted all iterations without a completion signal:
if [ "$completed" = 0 ]; then
  echo "TIMEOUT iter=20" >> "$STATUS_FILE"
fi
```

## Timeout handling

**Timeout (20 iterations, no completion signal for `$HEAD_SHA`):** no walkthrough references the current head and no review/inline comment is stamped with it after 20 minutes. Likely causes: CodeRabbit isn't installed on the repo, the webhook is stuck/slow, the service is down, the PR's base isn't covered by CodeRabbit's config and the `@coderabbitai review` mention in Step 5c didn't take, OR (common on re-polls) the incremental pass simply hasn't landed yet. Before declaring timeout, cross-check the walkthrough's `updated_at` and its `📥 Commits` line directly — an in-place edit naming `$HEAD_SHA` is completion even if the strict `contains` check lagged. Print `"CodeRabbit didn't post a completion signal for $HEAD_SHA in 20 minutes. Check the PR page directly: $PR_URL. To resume polling once CodeRabbit responds: re-enter from Step 6-cr directly with the current $HEAD_SHA — do NOT re-run /slopstop:pr (the 'PR already exists' pre-flight check will abort before reaching the poll step)."` and skip to Step 7.

## Post-loop findings routing

`all_cr_inline` is populated by the loop's final iteration (the same API request that drives `inline_count` — no extra call needed). Use it alongside `review_count` to route:

- `all_cr_inline > 0 || review_count > 0` → findings path (7-pre / 7d-findings); read all CR inline comments, not just those with `commit_id == HEAD_SHA`.
- Otherwise → clean pass (the normal shape of a re-review: walkthrough edited in place, body typically `"No actionable comments were generated in the recent review."`); route to clean path (7-pre / 7d-clean).

`review_count` is filtered by `commit_id == HEAD_SHA`; it catches new Review objects on first reviews. On re-reviews CR does not post a new Review object, so `review_count` is 0 — `all_cr_inline` is the determining signal.

Do NOT re-surface findings from a prior review cycle — the walkthrough's HEAD_SHA reference confirms these are the results of the current review pass.
