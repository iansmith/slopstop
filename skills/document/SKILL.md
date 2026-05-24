---
description: Sync the active ticket's local tracking documentation (task plan, DoD-confirmation evidence, findings) to the ticket on Linear/JIRA. Use /ticket-plugin:document to push or refresh the description + DoD-confirmation comment + findings comment WITHOUT ending the local lifecycle (no archive, no local-dir move, no state change). Idempotent — running it twice on unchanged local state is a clean no-op. Safe by default — if the ticket already has managed documentation that differs from what would be pushed (e.g., someone hand-edited the description), stops with a per-artifact diff explanation and refuses to push anything. --force overrides the divergence check. --dry-run shows what would happen without doing it. Auto-detects ticket system.
disable-model-invocation: true
---

# /ticket-plugin:document

Sync the active ticket's local documentation to the ticket on Linear/JIRA. Pure remote sync — does NOT touch local tracking, does NOT change ticket state, does NOT archive.

| Local source | Ticket target |
|---|---|
| `task_plan.md` (whole body) | Ticket **description**, with the prior original description preserved as `## Original description (preserved)` appendix |
| `task_plan.md`'s `## Definition of Done` section + evidence | Separate **comment** titled `## Definition of Done — Confirmation` |
| `findings.md` (if non-template) | Separate **comment** titled `## Findings (from local tracking)` |

Per-artifact safety: if the ticket already has a managed version (recognized by the content signatures above) and its content differs from what would be pushed, the skill stops with a diff report and refuses to push **any** of the three artifacts (all-or-nothing on the remote side). `--force` overrides.

`progress.md` is intentionally NOT pushed — per-session diary is too noisy for the durable record.

## Project scope (every ticket skill follows this rule)

Read `.project-prefix` from cwd. Call its contents `$PREFIX`.

**Only operate on `$PREFIX`'s tickets. Never read, write, or modify `CURRENT-*` files for any other prefix.**

If `.project-prefix` is missing in cwd: stop with `"No .project-prefix in cwd. Create one (e.g. echo MAZ > .project-prefix) and retry."`

## Arguments

- Optional `$ARGUMENTS`: a ticket key like `MAZ-26`. Must match `^$PREFIX-\d+$`. If empty, use the active `CURRENT-$PREFIX`.
- Optional `--force`: push the new content even when the ticket has a managed version that differs from expected. Surfaces a brief warning in Step 7's output for each overridden artifact.
- Optional `--dry-run`: compute everything (Steps 1–4) and print the per-artifact verdict + any diffs, then stop. No remote calls in Step 6.

If `$ARGUMENTS` is empty AND `CURRENT-$PREFIX` is empty: `"No active $PREFIX ticket to document; pass a ticket key as an argument or start a ticket first."` and stop.

Verify `~/.claude/ticket-active/$TICKET/` exists (or `~/.claude/ticket-archive/$TICKET/` for already-archived tickets). If neither: `"No local tracking found for $TICKET."` and stop.

## Step 1 — Detect ticket system

Run two ToolSearches in parallel:

```
ToolSearch(query="select:mcp__atlassian__getJiraIssue,mcp__atlassian__editJiraIssue,mcp__atlassian__addCommentToJiraIssue,mcp__atlassian__getAccessibleAtlassianResources", max_results=8)
ToolSearch(query="select:mcp__linear-server__get_issue,mcp__linear-server__save_issue,mcp__linear-server__save_comment,mcp__linear-server__list_comments", max_results=8)
```

Set `$SYSTEM`:
- JIRA only → `JIRA`
- Linear only (`mcp__linear-server__*`) → `Linear`
- Both → ask: `"Both JIRA and Linear MCP are configured. Which is $TICKET on? (jira / linear)"`
- Neither → stop: `"No ticket-system MCP found. Configure Atlassian or Linear MCP and retry."`

## Step 2 — Fetch current ticket state

We need both the description body AND the full comment list (to check for our managed comments by their titles).

**JIRA:**
- Get cloudId via `mcp__atlassian__getAccessibleAtlassianResources` (cache).
- `mcp__atlassian__getJiraIssue($TICKET, cloudId, fields=["status","description","summary"])`.
- For comments: use the appropriate Atlassian MCP comment-list tool (or `mcp__atlassian__getJiraIssue` with a comment-expanding field set if available). Fall back to a separate call if needed.

**Linear:**
- `mcp__linear-server__get_issue($TICKET)`.
- `mcp__linear-server__list_comments(issueId=$TICKET)`.

Store:
- `$REMOTE_DESC` = the current description body (markdown string)
- `$REMOTE_COMMENTS` = list of `{id, body, created_at, updated_at, author}` for all comments

## Step 3 — Compute the desired state from local files

Read `~/.claude/ticket-active/$TICKET/{task_plan,findings}.md` (or the `~/.claude/ticket-archive/$TICKET/` copy if active doesn't exist).

### 3a. Description

If `$REMOTE_DESC` contains the marker `## Original description (preserved)`:

- A prior `:document` or `:archive` run already published. Split on the separator:
  ```
  (managed_body, _, preserved_original) = $REMOTE_DESC.partition("---\n\n## Original description (preserved)\n\n")
  ```
- Preserve the `preserved_original` portion verbatim — DO NOT re-overwrite with the current description (the current description's body-before-marker IS the prior managed body, not the original).
- `$EXPECTED_DESC = <body of task_plan.md> + "\n\n---\n\n## Original description (preserved)\n\n" + preserved_original`

If `$REMOTE_DESC` does NOT contain the marker:

- The current description IS the original — no prior publish.
- `$EXPECTED_DESC = <body of task_plan.md> + "\n\n---\n\n## Original description (preserved)\n\n" + $REMOTE_DESC`

### 3b. DoD-confirmation comment

If `task_plan.md` has NO `## Definition of Done` section → set `$EXPECTED_DOD = null` (skip; no comment to push). Otherwise build the expected comment body:

```
## Definition of Done — Confirmation (<UTC ISO 8601 timestamp>)

Confirming each DoD item from the agreed plan against the work delivered:

<for each DoD item in task_plan.md's ## Definition of Done section:>
  ✅ **<item restated from task_plan.md>**
     Evidence: <test name(s) passing, commit SHA(s), PR link, manual verification note from progress.md if any>

  <OR if evidence is missing:>
  ⚠️ **<item>** — Could not confirm.
     Reason: <why — e.g., "no red test was written for this behavior" or "manual verification step still pending">
     What this means: <what the client should know>

Confirmed at: <UTC timestamp, ISO 8601>
```

Evidence-gathering sources, per DoD item:

- **Phase 0 red test status:** if `task_plan.md` has a `**Test command:**` line, run it (or rely on the most recent test result captured in `progress.md` — typically a `## /ticket-pr` or `## Implementation` section). Match red-test names against DoD items to confirm green.
- **Commits and PR:** `gh pr list --search "$TICKET" --state merged --json number,url,mergeCommit` for the merged PR + merge commit SHA. `git log --grep "[$TICKET]" --oneline` for ticket-anchored commits. (When inlined by `:archive` after a `:merge`-or-manual-merge has already happened, the merge commit and PR URL are likely captured in `progress.md` already.)
- **Manual / observable verification:** read `progress.md` for `## Update` sections that document hands-on verification.

**Never fake a confirmation.** If evidence isn't there, use ⚠️ and explain plainly. A ⚠️ item is more honest (and more useful to the client) than a ✅ that doesn't hold up.

Set `$EXPECTED_DOD` to the assembled comment body. Note the `Confirmed at:` timestamp line — Step 4b strips it before comparison.

### 3c. Findings comment

If `findings.md` is template-empty (no `## ` headings, no prose past the placeholder scaffold) → set `$EXPECTED_FINDINGS = null` (skip).

Otherwise:

```
$EXPECTED_FINDINGS = "## Findings (from local tracking)\n\n" + <body of findings.md verbatim>
```

## Step 4 — Classify each artifact

For each artifact (`description`, `dod`, `findings`):

### 4a. Find the managed version on the ticket

- **Description**: managed = `$REMOTE_DESC` contains the literal string `## Original description (preserved)`. Managed body = the portion before the `---\n\n## Original description (preserved)\n\n` separator. If no marker, the description is **unmanaged** (original) → category: `new`.
- **DoD comment**: managed = comments whose body's first non-blank line starts with `## Definition of Done — Confirmation` (allowing the optional ` (<timestamp>)` suffix). If multiple match, pick the one with the latest `updated_at`. If none AND `$EXPECTED_DOD == null` → category: `skip` (nothing to push, nothing to compare). If none AND `$EXPECTED_DOD != null` → category: `new`.
- **Findings comment**: same logic, matching first line `## Findings (from local tracking)`.

### 4b. Compare via loose-normalize

For each artifact with both a managed version AND an expected version:

Normalize both sides:

1. Collapse all sequences of whitespace (spaces, tabs, newlines) to a single space.
2. Strip leading and trailing whitespace.
3. For the DoD comment ONLY: remove the entire `Confirmed at: ...` line from both sides BEFORE normalizing (it's dynamic per-push; ignoring it lets pure timestamp changes be treated as `unchanged`). Also remove the `## Definition of Done — Confirmation (<timestamp>)` header timestamp.

If `normalize(expected) == normalize(actual_managed)` → category: `unchanged`.
Else → category: `divergent`.

### 4c. Per-artifact categories

Each artifact ends up in one of:

- `new` — not yet on the ticket; Step 6 will push.
- `unchanged` — already current; Step 6 skips cleanly.
- `divergent` — ticket has a managed version that differs from expected; **Step 5 stops** unless `--force`.
- `skip` — nothing to push (no DoD section in task_plan.md, or findings.md template-empty).

## Step 5 — Safety check

If any artifact is `divergent` AND `--force` is NOT set, STOP. Do NOT proceed to Step 6.

```
STOP — ticket $TICKET has managed documentation that differs from what would be pushed.

<for each divergent artifact:>
  ── <artifact name> ──────────────────────────────
  Local (expected, what would be pushed):
    <first ~12 lines of $EXPECTED_<artifact>, with … if truncated>
  Remote (actual, currently on the ticket):
    <first ~12 lines of actual_managed_<artifact>, with … if truncated>

Likely causes:
  - Someone edited the ticket on $SYSTEM after a prior :document/:archive push.
  - Your local task_plan.md / findings.md has been updated since the last push and represents a divergent intent.
  - A different /ticket-plugin session (different cwd, different machine) pushed an alternative version.

To proceed:
  - Run /ticket-plugin:document --force to overwrite the ticket's version with the local version. (Recommended only after eyeballing the diff above.)
  - OR reconcile manually: edit task_plan.md / findings.md to match the ticket, OR edit the ticket to match local, then re-run /ticket-plugin:document.
  - --dry-run shows the diff again without pushing.

No remote calls made. Local tracking unchanged.
```

The skill exits cleanly here. Not an error — a deliberate refusal.

## Step 6 — Push (skip if `--dry-run`)

For each artifact in category `new`, OR (with `--force`) category `divergent`:

### 6a. Description

JIRA: `mcp__atlassian__editJiraIssue($TICKET, cloudId, description=$EXPECTED_DESC)`.
Linear: `mcp__linear-server__save_issue(id=<issue id>, description=$EXPECTED_DESC)`.

Do NOT touch ticket status.

### 6b. DoD-confirmation comment

- If `new`: post a new comment via JIRA `mcp__atlassian__addCommentToJiraIssue` / Linear `mcp__linear-server__save_comment(issueId=$TICKET, body=$EXPECTED_DOD)`.
- If `divergent` + `--force`:
  - If the MCP supports editing the existing comment by id, edit it in place.
  - If it doesn't, post a new comment AND leave the old one in place (most teams' MCPs don't expose edit-comment cleanly). Mention this in Step 7's output so the user can manually delete the stale comment if they want.

### 6c. Findings comment

Same shape as 6b.

`unchanged` artifacts: silently skip — they're already current. `skip` artifacts: silently skip — nothing to push.

If Step 6 push fails on any single artifact mid-loop: print which succeeded and which didn't, do NOT attempt rollback (we have no remote-rollback mechanism), report cleanly. User can re-run after addressing the failure — succeeded pushes will become `unchanged` on the retry.

## Step 7 — Confirm

```
Documented $TICKET (<state name> on $SYSTEM).

Description:   <"updated (new)" | "updated (--force overrode divergent version)" | "already current — skipped" | "skipped (nothing to push)">
DoD comment:   <"posted (new)" | "posted (--force overrode divergent comment; old comment left on ticket)" | "already current — skipped" | "skipped (no DoD section in task_plan.md)">
Findings:      <"posted (new)" | "posted (--force overrode divergent comment; old comment left on ticket)" | "already current — skipped" | "skipped (findings.md template-empty)">

<if any divergent artifact was overridden by --force and the MCP couldn't edit-in-place:>
Note: --force pushed new versions, but the prior managed comments are still on the ticket. Delete them manually on $SYSTEM if you want a clean record:
  - <link to / id of stale DoD comment>
  - <link to / id of stale findings comment>
```

For `--dry-run`, replace each verb in the summary lines with the conditional ("would update" / "would post" / etc.) and end with `(dry-run — no remote calls made)`.

## Rules

- **Does NOT change ticket state. Does NOT touch local tracking. Does NOT clear `CURRENT-$PREFIX`.** Those belong to `/ticket-plugin:archive`. `:document` is a pure remote-sync operation, callable at any point in a ticket's life.
- **Idempotent.** Same local state + same ticket state → second consecutive run is a clean no-op (all artifacts `unchanged`).
- **Safe by default.** If the ticket has a managed version that differs from expected, refuse-and-explain. `--force` is the explicit escape hatch.
- **All-or-nothing on push.** If ANY artifact is `divergent` without `--force`, NONE of the artifacts get pushed. Don't half-publish.
- **`progress.md` is intentionally never pushed.** Per-session diary is too noisy for the durable record.
- Failure handling:
  - Ticket-system detection fails: error and stop. No state changed.
  - Ticket fetch fails: error and stop. No state changed.
  - Divergence detected without `--force`: print the report, exit cleanly. Not an error — a refusal.
  - Push fails mid-loop on any artifact: report which succeeded and which didn't. Don't roll back (no mechanism). User re-runs after addressing the failure.

## When to use

- **At the "In Review" workflow gate, so reviewers can review the *ticket* too.** This is the headline use case. Many teams use `In Review` as a real gate — a reviewer (teammate, tech lead, QA, product owner) reads the *ticket itself* alongside the PR to understand what's being shipped: what was the agreed scope? what's the Definition of Done? what plan was actually executed? `:document` is what puts those answers on the ticket. Without it, the ticket may still hold only the original problem statement when the reviewer opens it — they see "what was wrong" but nothing about "what's being delivered" or "what they're reviewing for." Run `:document` right after `:merge` (which advances the ticket to `In Review` but deliberately does not push docs), and the reviewer has the full picture before deciding whether to advance the ticket toward `Done`.
- **Standalone, mid-ticket checkpoint.** Push a snapshot of the current docs to the ticket for stakeholder visibility (PM wants to see how the plan is shaping up; client filed the ticket and wants to see progress on the DoD; etc.), then keep working. Re-run anytime — idempotent.
- **Inlined by `/ticket-plugin:archive`.** Archive's Step 4 inlines this skill's body to publish the final docs, then proceeds to its Step 5 local move. If `:document` stops on divergence, `:archive` propagates the stop and the local dir stays put for clean re-run after the user resolves the divergence.

## Where `:document` fits in the lifecycle

```
:merge       → code merged, ticket advanced to In Review, branch cleaned up.
               Docs NOT touched on the ticket — :merge deliberately stops short.
                                       │
                                       ▼
:document    → push plan + DoD-confirmation + findings to the ticket. Now the
               reviewer working the In Review state has the ticket-as-document
               to review alongside the PR.
                                       │
            (reviewer reads the ticket + the PR, signs off, transitions
             the ticket to a terminal Done-type state)
                                       │
                                       ▼
:archive     → push any last documentation updates (idempotent — usually a
               clean no-op because :document already pushed), then mv local
               tracking to ticket-archive/ and clear CURRENT-<PREFIX>.
```

The separation is deliberate: `:merge` ships code (deterministic, immediate), `:document` populates the ticket for the reviewer (when ready for review), `:archive` closes the local lifecycle (after the reviewer has signed off). Workflows that have no `In Review` gate (where `:merge` advances straight to Done) collapse `:document` and `:archive` into a single `:archive` invocation — `:document`'s body is inlined there anyway.
