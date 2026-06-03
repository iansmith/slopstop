# GitHub backend primitives — Design Document

**Status:** Draft, 2026-05-25. Updated 2026-06-03 — PR-level primitives added; `gh auth status` conditionalization documented (BILL-60).

## Summary

The 4 lifecycle skills (`:start`, `:document`, `:archive`, `:merge`) currently dispatch between Linear (`mcp__linear-server__*`) and JIRA (`mcp__atlassian__*`) at three points: Step 1 (MCP detection / `$SYSTEM` resolution), each skill's call sites for issue read/write operations, and `:merge`'s "advance one state" logic. For github-backed projects (those with `system = "github"` in `.project-conf.toml`), each skill currently stops at Step 1 with *"No ticket-system MCP found."*

This document defines the github backend that closes that gap. It enumerates the github-specific implementation of every primitive the 4 skills need, picks one canonical dispatch shape (MCP-preferred, `gh` CLI fallback — symmetric with how `:pr` already works), and specifies the exact snippets each skill should embed at its call sites. The 4 skills consume this doc — each adds a `**GitHub:**` block alongside its existing `**JIRA:**` / `**Linear:**` blocks, copying the relevant snippet verbatim.

The doc exists so the four skills stay consistent and the dispatch decisions are made once, not re-litigated per skill.

## Goals

- Concrete, verbatim-copyable snippets for every github operation a lifecycle skill performs.
- One canonical Step 1 detection block (3-way ToolSearch + `$SYSTEM` + `$GH_BACKEND` resolution).
- Symmetric with `:pr`'s existing MCP-preferred / CLI-fallback shape — no new dispatch pattern invented.
- Tolerant of github MCP namespace variance (canonical `mcp__github__*` vs Anthropic-managed `mcp__plugin_github_github__*`).
- Idempotency notes per primitive so `:document`'s skip-when-current and divergence detection extend cleanly.

## Non-goals

- A general GitHub Issues API reference. This doc covers only what the 4 lifecycle skills consume.
- GitHub Projects v2 / status fields / native state machine support. Github's state machine is intentionally shallow here — label-based via `[status_labels]`, with binary OPEN/CLOSED as the only intrinsic state.
- Cross-skill shared helper file. Each `SKILL.md` is self-contained; the snippets in this doc get copied (not included) into each skill that needs them. If duplication becomes painful later, factor then.
- Migration of existing Linear/JIRA logic to use the github model. Different systems, different shapes — leave them be.

## Architectural decisions

These are settled here so the 4 skills don't have to re-decide each.

### 1. MCP-preferred, `gh` CLI fallback (mirror `:pr`)

Each lifecycle skill's Step 1 runs a third `ToolSearch` for github MCP tools alongside the existing JIRA + Linear searches. If github MCP tools are present, set `$GH_BACKEND = "MCP"` and use MCP tool calls at each call site. If not, set `$GH_BACKEND = "CLI"`, resolve `$GH` via the trial-path logic from `:pr` Step 4a, and use `gh` CLI invocations at each call site.

Rationale: `:pr` already established this shape. Keeping the lifecycle skills symmetric means a future github MCP installation is picked up automatically without further skill changes.

### 2. Tool-name namespace fallback

Github MCPs may be installed under either of two namespaces:

- `mcp__github__*` — canonical (e.g., open-source GitHub MCP server).
- `mcp__plugin_github_github__*` — Anthropic's managed `github@claude-plugins-official` plugin's namespacing.

The Step 1 `ToolSearch` tries the canonical names first. On empty result, tries the plugin-namespaced variant. If both empty, fall through to `$GH_BACKEND = "CLI"`. The Step 1 detection block (below) encodes this fallback.

### 3. No shared cross-skill helper file

Each `SKILL.md` is self-contained — there's no include mechanism, and a cross-skill shared file would need a new convention. Github logic gets copied verbatim from this design doc into each of the 4 consumer skills, the same way JIRA and Linear blocks are duplicated today. If maintenance pain accumulates, factor into a shared `skills/_shared/github.md` (or similar) then.

### 4. `[status_labels]` parsing — inline TOML read snippet

`.project-conf.toml` is parsed inline by each skill (no shared parser exists today). The github backend needs to read the nested `[status_labels]` table — slightly trickier than the flat top-level `system` / `key` / `prefix`. A reusable Bash snippet is specified once (below) and embedded at each skill's call site where a label name is needed.

## Step 1 detection block (canonical)

Embed this verbatim into each lifecycle skill's Step 1, alongside the existing JIRA + Linear ToolSearch calls. Run the three searches in parallel (single message, three tool calls).

```
ToolSearch(query="select:mcp__atlassian__getJiraIssue,mcp__atlassian__getAccessibleAtlassianResources,mcp__atlassian__getTransitionsForJiraIssue,mcp__atlassian__transitionJiraIssue", max_results=8)

ToolSearch(query="select:mcp__linear-server__get_issue,mcp__linear-server__save_issue,mcp__linear-server__list_issue_statuses", max_results=8)

# New for github — try canonical names first
ToolSearch(query="select:mcp__github__get_issue,mcp__github__add_issue_comment,mcp__github__update_issue,mcp__github__list_issue_comments", max_results=8)
```

Set `$SYSTEM`:

- JIRA tools only (and `.project-conf.toml` says `system = "jira"`) → `JIRA`
- Linear tools only (and `system = "linear"`) → `Linear`
- Github MCP tools resolved above (and `system = "github"`) → `GitHub`; **`$GH_BACKEND = "MCP"`**
- Github MCP search returned empty AND `system = "github"` → run the fallback ToolSearch:
  ```
  ToolSearch(query="select:mcp__plugin_github_github__get_me,mcp__plugin_github_github__add_issue_comment,mcp__plugin_github_github__issue_write", max_results=8)
  ```
  If non-empty → `$SYSTEM = "GitHub"`, **`$GH_BACKEND = "MCP"`** (the actual tool names are `mcp__plugin_github_github__*`; record the namespace prefix as `$GH_MCP_NS = "mcp__plugin_github_github__"` so call sites can construct the right tool name).
  If still empty → `$SYSTEM = "GitHub"`, **`$GH_BACKEND = "CLI"`** (resolve `$GH` via the snippet below).
- Multiple systems detected ambiguously (the user's `.project-conf.toml` says one thing but tools for another are present) → trust `.project-conf.toml`'s `system` value. The other systems' tools are coincidentally available; they're not the active backend.
- Neither MCP nor matching `system` value → stop with `"No ticket-system MCP found for system='<value>' in .project-conf.toml. Configure the matching MCP and retry."`

The key rule: `.project-conf.toml`'s `system` field is authoritative. The ToolSearches are about *resolving the backend implementation* (MCP vs CLI for github; MCP for JIRA/Linear), not about *choosing the system*. This avoids the ambiguous case where the user has both Linear and github MCPs installed and the skills can't tell which project they're in.

## `$GH` binary discovery (CLI path)

Used when `$GH_BACKEND = "CLI"`. Lifted from `:pr` Step 4a verbatim.

> For the **CLI** path, find the `gh` binary. Try each in order; use the first one where `<path> --version` succeeds:
>
> 1. `/usr/local/bin/gh`
> 2. `$HOME/.local/bin/gh`
> 3. `/opt/homebrew/bin/gh`
> 4. `command -v gh` (i.e. whatever `$PATH` resolves)
>
> Save as `$GH`. If none resolve, stop:
> ```
> Neither GitHub MCP nor `gh` CLI found. Install one of:
> - gh CLI: https://cli.github.com/
> - GitHub plugin: /plugin install github@claude-plugins-official
> ```

Verify auth: `$GH auth status` succeeds.

Embed this snippet verbatim into each lifecycle skill's Step 1 immediately after `$GH_BACKEND` is set to `CLI`.

## `gh auth status` pre-flight conditionalization

Several lifecycle skills guard their pre-flight with `gh auth status`. When `$GH_BACKEND = "MCP"`, this check is irrelevant — the MCP uses Claude Code's own auth context — and running it would require `gh` on PATH, the dependency we're making optional.

Rule: only run `gh auth status` when `$GH_BACKEND = "CLI"`. Embed the conditionalized form in each skill that currently runs it unconditionally (`:merge`, `:doc-sync`):

```bash
if [ "$GH_BACKEND" = "CLI" ]; then
  $GH auth status || { echo "Not authenticated — run 'gh auth login' first."; exit 1; }
fi
```

When `$GH_BACKEND = "MCP"`, skip the check; if an MCP call later fails on auth, surface that error verbatim — the MCP layer owns its own authentication.

## `[status_labels]` read snippet

Used when `$SYSTEM = "GitHub"` and the skill needs the in-progress or in-review label name. Reads the `[status_labels]` table from `.project-conf.toml` in cwd.

Bash one-liner per key (no TOML parser dependency — minimal grep/sed):

```bash
# Read [status_labels].in_progress (required for github projects).
IN_PROGRESS_LABEL=$(awk '
  /^\[status_labels\]/ { in_section=1; next }
  /^\[/ && !/^\[status_labels\]/ { in_section=0 }
  in_section && /^[[:space:]]*in_progress[[:space:]]*=/ {
    sub(/^[^=]*=[[:space:]]*"/, "")
    sub(/".*$/, "")
    print
    exit
  }
' .project-conf.toml)

# Same shape for in_review (optional — empty if not present).
IN_REVIEW_LABEL=$(awk '
  /^\[status_labels\]/ { in_section=1; next }
  /^\[/ && !/^\[status_labels\]/ { in_section=0 }
  in_section && /^[[:space:]]*in_review[[:space:]]*=/ {
    sub(/^[^=]*=[[:space:]]*"/, "")
    sub(/".*$/, "")
    print
    exit
  }
' .project-conf.toml)
```

If `$IN_PROGRESS_LABEL` is empty (github project but no `[status_labels].in_progress`): stop with `"system='github' requires [status_labels].in_progress in .project-conf.toml. Run /slopstop:gh-init or add it manually."`

`$IN_REVIEW_LABEL` empty is fine — that's the signal for 3-state workflow (used by `:merge`).

## Workflow shape detection (used by `:merge`)

Github's workflow is binary by default (OPEN / CLOSED). `[status_labels]` adds intermediate states. Two supported workflows:

| `in_progress` | `in_review` | Workflow shape | `:merge` behavior |
|---|---|---|---|
| Set | Unset | **3-state** (todo → in-progress → done) | `gh issue close $N` + remove `in_progress` label |
| Set | Set | **4-state** (todo → in-progress → in-review → done) | Swap: remove `in_progress`, add `in_review`. Issue stays open. `:archive` closes it later. |

`:merge` reads `$IN_PROGRESS_LABEL` and `$IN_REVIEW_LABEL` (per the snippet above) and dispatches based on whether `$IN_REVIEW_LABEL` is empty.

No introspection of label history or comments needed — the workflow shape is declared in `.project-conf.toml`.

## Primitives

Each primitive lists both backends (MCP and CLI) plus the consumer(s). MCP names assume canonical namespace; if `$GH_MCP_NS = "mcp__plugin_github_github__"` was recorded in Step 1, substitute that prefix.

### Read issue (state + body + labels + assignees + milestone)

**Consumer:** `:start` Step 2, `:document` Step 2, `:archive` Step 2, `:merge` Step 2.

| Backend | Invocation |
|---|---|
| MCP | `mcp__github__get_issue(owner=$OWNER, repo=$REPO, issueNumber=$N)` |
| CLI | `$GH issue view $N --json number,state,body,labels,assignees,milestone,url` |

`$OWNER` and `$REPO` come from `.project-conf.toml`'s `key` field, which is `owner/repo` for github projects.

`$N` is the numeric part of `$TICKET` (e.g. `$TICKET = BILL-8` → `$N = 8`).

Returns JSON. Consumer parses fields as needed:
- `state`: `"OPEN"` or `"CLOSED"` (use for terminal-state gate)
- `body`: the description markdown (use for divergence detection)
- `labels`: array of `{name, color, description}` — find `$IN_PROGRESS_LABEL` / `$IN_REVIEW_LABEL` membership
- `assignees`, `milestone`: for `task_plan.md` metadata at `:start` time

### Read comments

**Consumer:** `:document` Step 2 (find the existing DoD and findings comments by leading marker).

| Backend | Invocation |
|---|---|
| MCP | `mcp__github__list_issue_comments(owner=$OWNER, repo=$REPO, issueNumber=$N)` |
| CLI | `$GH api repos/$OWNER/$REPO/issues/$N/comments` |

Returns array of `{id, body, user.login, created_at, updated_at}`. Consumer matches by leading marker (e.g. `## Definition of Done` or `## Findings (from local tracking)`) to find the comment to update vs. create.

### Set issue body (description)

**Consumer:** `:document` Step 6 (description update).

| Backend | Invocation |
|---|---|
| MCP | `mcp__github__update_issue(owner=$OWNER, repo=$REPO, issueNumber=$N, body=$BODY)` |
| CLI | `$GH issue edit $N --body "$BODY"` (or HEREDOC to preserve markdown) |

CLI HEREDOC form for multi-line bodies (recommended):
```bash
$GH issue edit $N --body "$(cat <<'EOF'
<body content>
EOF
)"
```

**Idempotency:** caller should compare the local `$BODY` (whitespace-trimmed) to the gh-fetched body (also trimmed) and skip the call if equal. Github normalizes `\r\n` to `\n` on its end, so the trim is necessary. Existing JIRA/Linear logic already does this; the github path follows the same pattern.

### Add comment

**Consumer:** `:document` Step 6 (DoD comment create, findings comment create), `:archive` Step 4 (delegates to `:document`).

| Backend | Invocation |
|---|---|
| MCP | `mcp__github__add_issue_comment(owner=$OWNER, repo=$REPO, issueNumber=$N, body=$BODY)` |
| CLI | `$GH issue comment $N --body "$BODY"` (HEREDOC for multi-line) |

**Idempotency:** the caller distinguishes "create new" from "update existing" using the read-comments primitive. If a comment with the expected leading marker exists, use `edit comment` instead of `add comment`.

### Edit comment

**Consumer:** `:document` Step 6 (DoD/findings comment update when content diverged).

| Backend | Invocation |
|---|---|
| MCP | `mcp__github__update_issue_comment(owner=$OWNER, repo=$REPO, commentId=$ID, body=$BODY)` |
| CLI | `$GH api -X PATCH "repos/$OWNER/$REPO/issues/comments/$ID" -f body="$BODY"` |

`$ID` is the numeric comment id from the read-comments primitive.

**Idempotency:** same whitespace-trimmed equality check as for body. Skip if the gh-fetched comment body matches local.

### Add label

**Consumer:** `:start` Step 3 (transition to In Progress), `:merge` Step 5 (4-state: add `in_review`).

| Backend | Invocation |
|---|---|
| MCP | `mcp__github__add_issue_labels(owner=$OWNER, repo=$REPO, issueNumber=$N, labels=[$LABEL])` |
| CLI | `$GH issue edit $N --add-label "$LABEL"` |

Github silently accepts adding a label that's already on the issue (idempotent by default). The skill doesn't need to pre-check.

**Pre-condition:** `$LABEL` must already exist on the repo. The label `status:in-progress` is created by `/slopstop:gh-init` (when implemented; see design/ticket-gh-init.md). For the bootstrap on slopstop itself, the label was created manually before BILL-8 started.

### Remove label

**Consumer:** `:merge` Step 5 (3-state: remove `in_progress`; 4-state: remove `in_progress` while adding `in_review`).

| Backend | Invocation |
|---|---|
| MCP | `mcp__github__remove_issue_label(owner=$OWNER, repo=$REPO, issueNumber=$N, label=$LABEL)` |
| CLI | `$GH issue edit $N --remove-label "$LABEL"` |

Github silently accepts removing a label that wasn't on the issue (idempotent by default).

### Close issue

**Consumer:** `:merge` Step 5 (3-state only; 4-state leaves it open for `:archive` to close).

| Backend | Invocation |
|---|---|
| MCP | `mcp__github__update_issue(owner=$OWNER, repo=$REPO, issueNumber=$N, state="closed")` |
| CLI | `$GH issue close $N` |

`gh issue close` is idempotent (closing a closed issue succeeds quietly). No pre-check needed.

## PR-level primitives (`:pr`, `:merge`)

These primitives cover pull request operations consumed by `:pr` (PR creation, CodeRabbit trigger, polling) and `:merge` (PR resolution, pre-merge gating, merge, post-merge verification). The same `$GH_BACKEND` dispatch applies. MCP tool names assume the `mcp__plugin_github_github__` namespace; substitute `$GH_MCP_NS` as recorded in Step 1. `$PR` is always the numeric PR number (integer).

### List open PRs for branch

**Consumer:** `:merge` Step 1 (identify which PR to merge).

| Backend | Invocation |
|---|---|
| MCP | `${GH_MCP_NS}list_pull_requests(owner=$OWNER, repo=$REPO, head="$OWNER:$BRANCH", state="open", perPage=5)` |
| CLI | `$GH pr list --head $BRANCH --state open --json number,title,state,isDraft,mergeable,mergeStateStatus,reviewDecision,statusCheckRollup --limit 5` |

The `head` parameter requires `owner:branch` format for the MCP (e.g. `iansmith:feat/BILL-60`). Returns an array. Zero items → no open PR; more than one → surface the list and ask for `--pr <N>`; exactly one → `$PR`.

### Read PR details

**Consumer:** `:merge` Step 1 (pre-merge gates), Step 4 (post-merge verification).

| Backend | Invocation |
|---|---|
| MCP | `${GH_MCP_NS}pull_request_read(method="get", owner=$OWNER, repo=$REPO, pullNumber=$PR)` |
| CLI | `$GH pr view $PR --json number,title,headRefName,baseRefName,state,isDraft,mergeable,mergeStateStatus,reviewDecision,statusCheckRollup,url` |

For pre-merge gating, consumer checks: `state == "OPEN"`, `isDraft == false`, `mergeable != "CONFLICTING"`, `headRefName == $BRANCH`. For post-merge verification (`:merge` Step 4), re-call and assert `state == "MERGED"`; capture the merge commit SHA for the Step 7 summary.

Note: the same MCP tool's `get_comments` / `get_review_comments` / `get_reviews` methods drive the CodeRabbit polling fallback described below.

### Merge PR

**Consumer:** `:merge` Step 4.

| Backend | Invocation |
|---|---|
| MCP | `${GH_MCP_NS}merge_pull_request(owner=$OWNER, repo=$REPO, pullNumber=$PR, merge_method=$STRATEGY)` |
| CLI | `$GH pr merge $PR --$STRATEGY --delete-branch --auto=false` |

`$STRATEGY` ∈ `{"merge", "squash", "rebase"}`. Explicitly NOT `--auto`; the merge happens now or fails now.

**Remote branch deletion gap:** The CLI path's `--delete-branch` atomically removes the remote feature branch. The MCP `merge_pull_request` tool has no equivalent parameter — the remote branch must be deleted separately after a successful MCP merge:

- If `gh` is also installed (even when `$GH_BACKEND = "MCP"`): `$GH api -X DELETE "repos/$OWNER/$REPO/git/refs/heads/$BRANCH"`.
- If `gh` is absent: skip remote deletion and surface it explicitly: `"Remote branch '$BRANCH' was NOT deleted — merge_pull_request does not support delete-branch. Delete it from the GitHub UI."` This is a known gap (see Open questions).

### Create PR

**Consumer:** `:pr` Step 5b.

| Backend | Invocation |
|---|---|
| MCP | `${GH_MCP_NS}create_pull_request(owner=$OWNER, repo=$REPO, title=$TITLE, body=$BODY, head=$BRANCH, base=$BASE)` |
| CLI | `$GH pr create --title "$TITLE" --body "$(cat <<'EOF'\n<body>\nEOF\n)" --base "$BASE" --head "$BRANCH"` |

Use the HEREDOC form for CLI to preserve markdown in `$BODY`. Both backends return the PR number and URL; capture as `$PR` and `$PR_URL`.

### Get default branch

**Consumer:** `:pr` Pre-flight (`$DEFAULT_BRANCH`), `:merge` Step 6a (switch-and-pull base ref).

`gh repo view --json defaultBranchRef` has no direct MCP equivalent. Use the following fallback chain — steps 1–3 are pure git and require neither `gh` nor MCP:

1. `git symbolic-ref refs/remotes/origin/HEAD 2>/dev/null | sed 's@^refs/remotes/origin/@@'` — works for any standard `git clone`; empty if the remote HEAD wasn't tracked.
2. `git ls-remote --heads origin main` non-empty → `"main"`.
3. `git ls-remote --heads origin master` non-empty → `"master"`.
4. If `$GH_BACKEND = "CLI"`: `$GH repo view --json defaultBranchRef --jq .defaultBranchRef.name`.
5. Prompt: `"Couldn't auto-detect the default branch. Enter it (e.g. main, master, trunk):"`.

### Add PR comment

**Consumer:** `:pr` Step 5c (CodeRabbit trigger), `:pr` Step 6 CodeRabbit polling fallback (issue-style comments).

| Backend | Invocation |
|---|---|
| MCP | `${GH_MCP_NS}add_issue_comment(owner=$OWNER, repo=$REPO, issue_number=$PR, body=$BODY)` |
| CLI | `$GH pr comment $PR --body "$BODY"` |

GitHub's REST API exposes PR issue-comments (the non-review threaded kind) via `/issues/:number/comments` — identical to issue comments. So `add_issue_comment` works for PRs: pass the PR number as `issue_number`.

### CodeRabbit polling — MCP fallback

**Consumer:** `:pr` Step 6 (when `$GH` / `gh api` is not available).

`:pr` Step 6 normally polls via `gh api`. When `gh` is absent and `$GH_BACKEND = "MCP"`, substitute these MCP reads at each poll iteration:

| `gh api` call | MCP equivalent |
|---|---|
| `gh api repos/$OWNER/$REPO/issues/$PR/comments` (walkthrough comment) | `${GH_MCP_NS}pull_request_read(method="get_comments", owner=$OWNER, repo=$REPO, pullNumber=$PR)` |
| `gh api repos/$OWNER/$REPO/pulls/$PR/comments` (inline review comments) | `${GH_MCP_NS}pull_request_read(method="get_review_comments", owner=$OWNER, repo=$REPO, pullNumber=$PR)` |
| `gh api repos/$OWNER/$REPO/pulls/$PR/reviews` (finalized reviews) | `${GH_MCP_NS}pull_request_read(method="get_reviews", owner=$OWNER, repo=$REPO, pullNumber=$PR)` |

**Limitations vs. `gh api`:**

- **In-place-edit on re-review — do not gate on comment existence (critical):** When a new commit is pushed to an existing PR, CodeRabbit does NOT create a new walkthrough comment. It edits the existing one in-place, rewriting its body and updating the `📥 Commits … between X and <new-HEAD>` line to name the new HEAD SHA. Consequence: after the first review, a walkthrough comment always exists — so "does a walkthrough comment exist?" fires immediately on every subsequent poll, before CodeRabbit has even started reviewing the new head. That's a false positive that presents stale findings as current.

  The correct completion gate — for both first reviews and all subsequent re-reviews — is: **a walkthrough comment by `coderabbitai[bot]` whose body (a) matches the walkthrough marker (`<!-- walkthrough_start -->` or `## Walkthrough`) AND (b) contains `$HEAD_SHA` AND (c) does NOT match `[Cc]urrently processing`**. This is false until CodeRabbit finishes the in-place edit for the current head, at which point it becomes true. The MCP fallback uses the identical check — `get_comments` returns the comment body, apply the same three-condition test.

- **`commit_id` filtering (secondary signal only):** The `gh api` path additionally filters inline review comments and finalized reviews by `commit_id == $HEAD_SHA` to separate current-head findings from prior-review leftovers. The MCP `pull_request_read` response may not expose per-comment `commit_id`. This is a secondary signal — skip the `commit_id` filter when on the MCP path, and treat the walkthrough body gate as the sole completion indicator. This means on a re-review with new inline comments, the MCP path may briefly show prior-review inline comments before CodeRabbit posts new ones; acceptable given that the walkthrough gate correctly serializes completion.

- **Polling loop:** The `gh api` path runs a Bash `sleep 60` loop (20 iterations, 20 min max). The MCP-fallback path cannot sleep in Bash; the poll must be driven as iterated Claude tool calls with instruction pauses between them. This is slower and more token-intensive but functionally equivalent.

- **Preferred backend:** When `gh` is available alongside `$GH_BACKEND = "MCP"`, always use `gh api` for CodeRabbit polling (as `:pr` Step 4a already specifies). MCP polling is graceful degradation, not the canonical path.

## Per-skill consumption summary

Which skill needs which primitives, for quick reference when adding the `**GitHub:**` block:

| Skill | Primitives used |
|---|---|
| `:start` | Read issue (Step 2); Add label (Step 3) |
| `:document` | Read issue (Step 2); Read comments (Step 2); Set issue body (Step 6); Add comment (Step 6); Edit comment (Step 6) |
| `:archive` | Read issue (Step 2 terminal gate); delegates to `:document` for Step 4 push |
| `:merge` | Read issue (Step 2); **List open PRs (Step 1); Read PR details (Step 1 + Step 4); Merge PR (Step 4)**; Add label + Remove label + Close issue (Step 5, dispatched on workflow shape) |
| `:pr` | **Create PR (Step 5b); Add PR comment (Step 5c, Step 6 fallback); Get default branch (Pre-flight); CodeRabbit polling — MCP fallback (Step 6)** |

## Open questions / TBDs

- **Github MCP tool names are not stable yet.** The canonical tool list assumed above (`mcp__github__get_issue`, `mcp__github__add_issue_comment`, `mcp__github__update_issue`, etc.) is based on what's commonly installed. If a particular install exposes different names, the ToolSearch in Step 1 may need adjustment. The plugin-namespaced fallback (`mcp__plugin_github_github__*`) at least covers the Anthropic-managed install; other MCPs may need additional fallbacks added later.

- **Edit-comment MCP availability.** Some github MCP installs may not expose an edit-comment tool. If `$GH_BACKEND = "MCP"` but the edit-comment tool is missing, fall through to `$GH_BACKEND = "CLI"` *just for that operation* (and use `$GH api -X PATCH …`). Document this as a per-op fallback if it comes up in practice.

- **Multi-repo projects.** This doc assumes `key = "owner/repo"` is a single repo. Future work (cross-repo tickets, monorepos with multiple GH issue trackers) would need a richer `key` shape. Out of scope for this ticket.

- **Race on label add-then-remove (4-state `:merge`).** When `:merge` swaps labels in 4-state mode (`--remove-label in_progress --add-label in_review`), gh CLI does both in one invocation (atomic from the user's perspective). The MCP equivalent may require two separate calls; if the first succeeds and the second fails, the issue ends up label-less which is a confusing intermediate state. Caller should detect partial failure and either retry or surface clearly.

- **Remote branch deletion after MCP merge.** `merge_pull_request` has no `delete_branch` parameter (unlike `gh pr merge --delete-branch`). The CLI fallback (`gh api -X DELETE …`) works when `gh` is installed alongside MCP. When `gh` is fully absent, the remote branch is left for the user to delete manually. This is a known limitation of the current MCP surface; if the upstream MCP adds a `deleteBranch` parameter, adopt it and update the Merge PR primitive above.

## Consumers

- [skills/start/SKILL.md](../skills/start/SKILL.md) — Step 1 detection, Step 2 fetch (read issue), Step 3 transition (add label).
- [skills/document/SKILL.md](../skills/document/SKILL.md) — Step 1 detection, Step 2 fetch (read issue + read comments), Step 6 push (set body, add/edit comment).
- [skills/archive/SKILL.md](../skills/archive/SKILL.md) — Step 1 detection, Step 2 terminal gate (read issue → `state == "CLOSED"`).
- [skills/merge/SKILL.md](../skills/merge/SKILL.md) — Step 1 detection, Step 1 PR resolution (list PRs, read PR details), Step 2 compute next state (workflow shape from `.project-conf.toml`), Step 4 merge PR + post-merge verification, Step 5 apply (add label / remove label / close issue).
- [skills/pr/SKILL.md](../skills/pr/SKILL.md) — Step 4a backend detection (PR-level MCP tools), Step 5b create PR, Step 5c add PR comment (CodeRabbit trigger), Step 6 CodeRabbit polling MCP fallback.

## Dependencies

- [`project-conf-toml.md`](project-conf-toml.md) — defines `system = "github"`, `key = "owner/repo"`, `prefix`, and the `[status_labels]` table that this backend consumes.
- [`multi-ticket.md`](multi-ticket.md) — defines the lifecycle skill shape (`:start` / `:document` / `:archive` / `:merge`) that this backend slots into.
- [`ticket-gh-init.md`](ticket-gh-init.md) — bootstrap skill that writes `.project-conf.toml` + creates the labels this backend reads.

## See also

- BILL-8 — the ticket that implements this design across the 4 consumer skills (issue-level).
- BILL-60 — the ticket that adds PR-level MCP primitives to `:merge` and `:pr` and makes `gh` optional.
- BILL-2 (closed) — the precedent; surfaced the gap when its archived documentation never landed on the github issue.
