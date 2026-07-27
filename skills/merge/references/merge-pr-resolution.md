# Merge: PR Backend, Resolution, and Pre-merge Gates (Step 1 detail)

Steps 1a–1d plus the gate lists. The spine keeps the *decisions* — adopt mode exists,
CLOSED refuses while MERGED adopts — and this file carries how each is determined.

## 1a. Detect GitHub PR backend

Run two ToolSearches in parallel:

```
ToolSearch(query="select:mcp__github__list_pull_requests,mcp__github__pull_request_read,mcp__github__merge_pull_request,mcp__github__create_pull_request", max_results=8)
ToolSearch(query="github list pull requests merge pull request", max_results=5)
```

Set `$GH_PR_BACKEND` and `$GH_MCP_NS`:

- Canonical `mcp__github__*` tools found → `MCP`, `$GH_MCP_NS = "mcp__github__"`.
- Canonical empty → fallback `ToolSearch(query="select:mcp__plugin_github_github__list_pull_requests,mcp__plugin_github_github__pull_request_read,mcp__plugin_github_github__merge_pull_request", max_results=8)`. Non-empty → `MCP`, `$GH_MCP_NS = "mcp__plugin_github_github__"`.
- Both empty → `CLI`. Find `$GH` by trial path: `/usr/local/bin/gh`, `$HOME/.local/bin/gh`, `/opt/homebrew/bin/gh`, then `command -v gh`. None → stop: `"Neither GitHub MCP nor 'gh' CLI found. Install one of: gh CLI (https://cli.github.com/) or the github plugin (/plugin install github@claude-plugins-official)."` Then `$GH auth status` — not authenticated → stop.

`$OWNER`/`$REPO` = `pr-repo` if present, else parse from `key`. Full primitives and
rationale: `design/github-backend-primitives.md`.

## 1b. Find the PR

**`$TARGET_GIVEN = true`** (explicit ticket arg): the PR may be in **any** state —
already merged, or closed. Resolve `$PR`, set `$BRANCH` from `headRefName`, and run the
MERGED/CLOSED/OPEN dispatch there. Applies **whether or not `--pr <N>` was given**:
→ Read `~/.claude/commands/slopstop-merge-refs/merge-target-given.md`

Then return here for 1c and the gates.

**`$TARGET_GIVEN = false`** (the default): if `--pr <N>` was given, use it as `$PR` and
skip the search. Otherwise search open PRs on `$BRANCH`.

- **MCP:** `${GH_MCP_NS}list_pull_requests(owner=$OWNER, repo=$REPO, head="$OWNER:$BRANCH", state="open", perPage=5)`. `head` requires `owner:branch` format, e.g. `iansmith:feat/BILL-60`.
- **CLI:** `$GH pr list --head $BRANCH --state open --json number,title,state,isDraft,mergeable,mergeStateStatus,reviewDecision,statusCheckRollup --limit 5`

Zero results → refuse: `"No open PR found for branch $BRANCH. Create one first."` More
than one → print the list, ask `"Multiple open PRs on $BRANCH; pass --pr <N> to
choose."`, stop. Exactly one → that's `$PR`.

## 1c. Read PR details

- **MCP:** `${GH_MCP_NS}pull_request_read(method="get", owner=$OWNER, repo=$REPO, pullNumber=$PR)`
- **CLI:** `$GH pr view $PR --json number,title,headRefName,baseRefName,state,isDraft,mergeable,mergeStateStatus,reviewDecision,statusCheckRollup,url,mergeCommit,mergedAt`

`mergeCommit`/`mergedAt` are read **here** so adopt mode has the merge SHA without a
second round-trip — Step 4 never runs to produce it. The MCP path returns both already.

## 1d. Adopt mode — the PR is already merged

`$ADOPT = true` when `state == "MERGED"`. This is the recovery path for a PR merged
**outside** `:merge` (the GitHub web UI, a bare `gh pr merge`): everything `:merge` does
*after* the merge — advancing the ticket, updating tracking, pushing docs, cleaning up
branches, archiving — is still pending and safe to do.

When `$ADOPT`: capture `$MERGE_COMMIT` from 1c (`mergeCommit.oid` on CLI), **skip Step 4
entirely**, run Steps 5–10 normally. `$ADOPT` is false on the normal `OPEN` path, where
Step 4 runs and produces `$MERGE_COMMIT`.

## Pre-merge gates (refuse-and-explain)

Every gate below decides from data 1c already fetched, with one exception: the DoD gate
reads the PR diff, and its fallback path reads the ticket body. Those are the only
remote calls past this point.

Always checked, adopt mode included:

- `state == "CLOSED"` — `"PR #$PR is closed without being merged. Its work was abandoned, so advancing $TICKET would misreport it. Reopen the PR, or transition the ticket manually."` Distinct from MERGED **on purpose**: a merged PR is adopted, not refused.
- `headRefName != $BRANCH` — `"PR #$PR's head ref is '$headRefName', not the expected branch '$BRANCH'. Aborting to avoid merging the wrong PR."` Applies in adopt mode too — never adopt the wrong PR.

**Skipped when `$ADOPT` is true** — these either govern whether a merge *can happen*
(re-litigating mergeability would refuse a PR that is provably fine) or cannot be
meaningfully scored once the PR is already merged:

- `isDraft == true` — `"PR #$PR is a draft. Mark ready for review first."`
- `mergeable == CONFLICTING` — `"PR #$PR has merge conflicts. Resolve and re-push first."`
- `mergeable == UNKNOWN` — `"GitHub hasn't computed mergeability yet. Wait a few seconds and re-run."`
- **Definition of Done not satisfied** — any item scoring `not-met` or `unverifiable`
  refuses the merge. Interactive mode has no override; `[autonomous] on_dod_not_met`
  is the only escape hatch.
  → Read `~/.claude/commands/slopstop-merge-refs/merge-dod-gate.md`

## Pre-merge soft warnings (mention, allow proceeding via confirmation)

Also skipped when `$ADOPT` — all four describe merge-readiness a merged PR has
demonstrated.

- `mergeStateStatus == BLOCKED` (e.g. required reviews unsatisfied) — note it; the user may have a temporary admin-merge override planned.
- `mergeStateStatus == BEHIND` — base has new commits; the user may want to rebase.
- `reviewDecision == REVIEW_REQUIRED` or `CHANGES_REQUESTED` — note it.
- Any failing or pending check in `statusCheckRollup` — list the check names.
