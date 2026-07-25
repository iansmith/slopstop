# PR: Push and Create (Steps 4 and 5)

## 4a. Locate the GitHub backend

Two ToolSearches in parallel for `mcp__github__*` tools. `$BACKEND` = `MCP` if found, else
`CLI`. Find `$GH` by trial path: `/usr/local/bin/gh`, `$HOME/.local/bin/gh`,
`/opt/homebrew/bin/gh`, then `command -v gh`. None → stop with install instructions.

Note this is the **code-hosting** backend. Step 7f resolves the *ticket-system* comment
backend separately; they are independent and can differ.

## 4b. Push the branch

- No upstream → `git push -u $PR_REMOTE $BRANCH`
- Ahead of upstream → `git push $PR_REMOTE $BRANCH`
- In sync → skip the push

On failure: stop with the git output verbatim. Never `git push --force`.

## 5a. Build title and body

- **Title:** `[$TICKET] <summary>`, from the most recent commit subject.
- **Body:** `## Summary` (1–3 bullets), `## Ticket` (URL), `## Test plan` (checklist).

## 5b. Create the PR

- **MCP:** the create-pull-request tool with `owner=$OWNER, repo=$REPO` — the canonical repo from `pr-repo` if set, else `key`.
- **CLI:** a HEREDOC with `$GH pr create --repo $OWNER/$REPO`. The explicit `--repo` matters: it targets the canonical repo even when `$PR_REMOTE` (the *push* remote) points at a personal fork.

Capture `$PR` and `$PR_URL`. Print `"PR created: $PR_URL (target: $BASE)"`.

## 5c. Trigger the review bot (CodeRabbit / Greptile only)

Skip if `$PR_BACKEND == "claude"` or `--no-poll`. Pre-flight already resolved `--inline` to
the claude backend, so that case is covered here — a bot trigger posted for a poll that
never runs would leave an unanswered `@bot review` on the PR, implying a review is pending.

If `$BASE != $DEFAULT_BRANCH`: post the backend-specific trigger (`@coderabbitai review` /
`@greptile review`). On failure: warn and continue.

**Skipping the trigger is NOT the same as skipping the poll.** On auto-review repos the bot
reviews without being asked, but Step 6-cr / 6-greptile still run — auto-review is not
self-verifying.
