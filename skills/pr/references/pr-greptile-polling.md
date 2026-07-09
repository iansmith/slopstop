# PR Greptile Polling — Full Implementation (Step 6-greptile)

## Greptile's review model

Greptile posts a GitHub PR review (state: `COMMENTED`) when its analysis is complete. It may also post inline PR comments. The bot's GitHub login is `greptile-dev[bot]`.

Unlike CodeRabbit, Greptile does not post an issue-level walkthrough comment; completion is signaled by the PR review object itself. On incremental re-reviews (after a new push), Greptile posts a fresh review for the new head SHA — it does not edit prior artifacts in place.

## Execution model — required

**Never run this poll in the foreground.** The Bash tool has a 10-minute hard cap; the 20-iteration loop takes up to 20 minutes and will be killed around iteration 10, reporting a false timeout.

**Required execution:**
1. Create a `STATUS_FILE` path before launching: e.g. `STATUS_FILE=$(mktemp /tmp/gr-poll-XXXXXX.txt)`.
2. Launch the poll script as a **background** Bash command: `run_in_background: true`, `timeout: 1200000` (20 min in ms).
3. When the background command finishes, you are re-invoked via a completion notification.
4. Read `$STATUS_FILE` — the last line is one of:
   - `DONE iter=N clean` — Greptile reviewed, no inline comments.
   - `DONE iter=N all_gr_inline=M review_count=K` — Greptile reviewed, M inline findings.
   - `TIMEOUT iter=20` — no Greptile completion signal within 20 minutes.

## Polling shell script

```bash
OWNER=$($GH repo view --json owner --jq .owner.login)
REPO=$($GH repo view --json name --jq .name)
HEAD_SHA=$(git rev-parse HEAD)   # gate on the commit we just pushed

# STATUS_FILE must be set by the caller before launching this as a background command.
# (run_in_background: true, timeout: 1200000)
echo "START $(date -u +%Y-%m-%dT%H:%M:%SZ) HEAD=$HEAD_SHA" >> "$STATUS_FILE"
completed=0

for i in $(seq 1 20); do
  # Fetch all PR reviews by the Greptile bot for this head SHA.
  review_count=$($GH api "repos/$OWNER/$REPO/pulls/$PR/reviews" \
    --jq "[.[] | select(.user.login==\"greptile-dev[bot]\" and .commit_id==\"$HEAD_SHA\")] | length")

  # Normalize transient API errors to 0 so comparisons below never see non-integer input.
  case "$review_count" in ''|*[!0-9]*) review_count=0 ;; esac

  if [ "$review_count" -gt 0 ]; then
    # Fetch inline comments only once a review exists — avoids wasted API calls per WAIT iteration.
    all_gr_inline=$($GH api "repos/$OWNER/$REPO/pulls/$PR/comments" \
      --jq "[.[] | select(.user.login==\"greptile-dev[bot]\")] | length")
    case "$all_gr_inline" in ''|*[!0-9]*) all_gr_inline=0 ;; esac
    if [ "$all_gr_inline" -gt 0 ]; then
      echo "Greptile feedback received for $HEAD_SHA: $all_gr_inline inline comments, $review_count review(s)"
      echo "DONE iter=$i all_gr_inline=$all_gr_inline review_count=$review_count" >> "$STATUS_FILE"
    else
      echo "Greptile review complete for $HEAD_SHA — no actionable comments"
      echo "DONE iter=$i clean" >> "$STATUS_FILE"
    fi
    completed=1
    break
  fi
  echo "WAIT iter=$i/20 $(date -u +%Y-%m-%dT%H:%M:%SZ)" >> "$STATUS_FILE"
  echo "Waiting for Greptile to review $HEAD_SHA ($i/20)..."
  sleep 60
done

if [ "$completed" = 0 ]; then
  echo "TIMEOUT iter=20" >> "$STATUS_FILE"
fi
```

## Timeout handling

**Timeout (20 iterations, no completion signal):** Greptile has not posted a review for the current head SHA after 20 minutes. Likely causes: Greptile app not installed on the repo, webhook stuck, service down, or PR base isn't covered by the Greptile plan. Print: `"Greptile didn't post a review for $HEAD_SHA in 20 minutes. Check the PR page directly: $PR_URL. To resume polling once Greptile responds: re-enter from Step 6-greptile directly with the current $HEAD_SHA — do NOT re-run /slopstop:pr (the 'PR already exists' pre-flight check will abort)."` and skip to Step 7.

**If the timeout fires around iteration 10:** the poll ran in the foreground — Bash tool's 10-minute cap killed it. That is a false timeout caused by execution model error. Re-run as a background command.

## Post-loop findings routing

- `all_gr_inline > 0` → findings path: fetch all Greptile inline comments and proceed to Step 7 full classification.
- Otherwise → clean pass: proceed to Step 7 clean presentation.

## Step 7 — Fetch commands

Use these in place of the CodeRabbit fetch commands in `pr-verification-classification.md`:

```bash
# Inline review comments from Greptile
$GH api "repos/$OWNER/$REPO/pulls/$PR/comments" \
  --jq "[.[] | select(.user.login==\"greptile-dev[bot]\") | {path, line, body, diff_hunk}]"

# Review summaries from Greptile (current head only)
$GH api "repos/$OWNER/$REPO/pulls/$PR/reviews" \
  --jq "[.[] | select(.user.login==\"greptile-dev[bot]\" and .commit_id==\"$HEAD_SHA\") | {state, body, submitted_at}]"
```

Greptile does not post a walkthrough issue-comment; omit that fetch. Present format is the same as `pr-verification-classification.md` Step 7d, with `Greptile review of PR #$PR` as the header.

The clean-verdict format (7d-clean), fix-and-iterate loop (7e), and all classification rules are identical to the CodeRabbit flow — substitute `$PR_GR_FIX` for `$PR_CR_FIX` throughout.
