---
name: slopstop-gh-init
description: Bootstrap a GitHub repo for the slopstop ticket workflow. Creates status labels, writes .project-conf.toml. Invoke as /slopstop:gh-init (or /slopstop-gh-init). Idempotent — safe to re-run.
---

# /slopstop:gh-init

Bootstrap a GitHub-backed project for the `slopstop` ticket workflow.

**What it does (once):**
- Creates `status:in-progress` (and optionally `status:in-review`) labels on the GitHub repo.
- Writes `.project-conf.toml` in cwd with `system = "github"`, `key`, `prefix`, and `[status_labels]`.

Safe to re-run — all actions are idempotent.

## Autonomous mode

When `.project-conf.toml` will have (or already has) `[autonomous] enabled = true`, this skill runs
unmodified. There are no interactive prompts that would block an autonomous session. Provide
`--workflow` and `--prefix` flags to skip the two interactive questions.

## Arguments

```
/slopstop:gh-init [--workflow {3,4}]
                  [--prefix PREFIX]
                  [--in-progress-label NAME]   (default: status:in-progress)
                  [--in-progress-color HEX]    (default: fbca04)
                  [--in-review-label NAME]     (default: status:in-review)
                  [--in-review-color HEX]      (default: 0e8a16)
```

- `--workflow 3|4` — skip the workflow question (Step 4).
- `--prefix PREFIX` — skip the prefix question (Step 4). Must be 2–8 uppercase chars, filesystem-safe (e.g. `BENCH`, `BILL`).
- Label name/color overrides apply to label creation only; they do not affect what gets written to `[status_labels]` in `.project-conf.toml` unless `--in-progress-label` / `--in-review-label` are provided (in which case those names are used both for creation and for the config file).

## Step 1 — Pre-flight

Run in parallel:

1. `git rev-parse --is-inside-work-tree` — must succeed. If not: stop with `"Run inside a git repository with a GitHub remote."`
2. `git remote get-url origin` — must contain `github.com`. If no remote or non-GitHub host: stop with `"No GitHub remote found at origin. Add one first."`
3. `gh auth status` — must exit 0. If not: stop with `"GitHub CLI not authenticated. Run \`gh auth login\` first."`

## Step 2 — Detect owner/repo

```bash
gh repo view --json nameWithOwner -q .nameWithOwner
```

Save as `$OWNER_REPO` (e.g. `iansmith/slopstop-bench`). Split on `/`: `$OWNER`, `$REPO`.

If this command fails (e.g. repo not yet pushed to GitHub): stop with `"Could not determine GitHub repo. Ensure the repo exists on github.com and 'origin' is set."`

## Step 3 — GitHub backend detection

Run two ToolSearches in parallel to resolve `$GH_BACKEND` and `$GH`:

```
ToolSearch(query="select:mcp__plugin_github_github__issue_write,mcp__plugin_github_github__issue_read", max_results=4)
ToolSearch(query="select:mcp__github__create_issue,mcp__github__update_issue", max_results=4)
```

Resolution:
1. Canonical `mcp__github__*` non-empty → `$GH_BACKEND = "MCP"`, `$GH_MCP_NS = "mcp__github__"`.
2. Plugin search non-empty → `$GH_BACKEND = "MCP"`, `$GH_MCP_NS = "mcp__plugin_github_github__"`.
3. Both empty → `$GH_BACKEND = "CLI"`. Try `/usr/local/bin/gh`, `$HOME/.local/bin/gh`, `/opt/homebrew/bin/gh`, then `command -v gh`. Save as `$GH`. If none found: stop with `"Neither GitHub MCP nor 'gh' CLI found."`.

## Step 4 — Questions (interactive only)

Skip each question if its corresponding flag was supplied.

**Repo confirmation** (always asked unless running in a known-good autonomous context):

```
Confirm repo: iansmith/slopstop-bench  [y/N]
```

If `n` or empty: stop with `"No changes made."`

**Prefix question** (skip if `--prefix` supplied):

```
Ticket prefix (e.g. BILL, BENCH, MAZ)? 
```

Re-ask if empty or contains non-alphanumeric characters. Save as `$PREFIX`. Convert to uppercase.

**Workflow question** (skip if `--workflow` supplied):

```
Choose a workflow:

  3-state: todo → in-progress → done
  4-state: todo → in-progress → in-review → done

In BOTH workflows the PR process includes a pre-merge simplify pass and a
code review. Those are part of in-progress, not what in-review means.

The 4-state workflow adds in-review AFTER the code is complete relative to
its requirements — for shake-down validation: another person reviewing the
working code, OR the author dogfooding it before declaring it done.

Which workflow? [3/4]
```

Accept `3` or `4`. If empty or other: re-ask once, then stop with `"No changes made."`

## Step 5 — Explainer (printed before any action)

```
/slopstop:gh-init will make these changes to <OWNER_REPO>:

  Labels to create (if missing):
    • <IN_PROGRESS_LABEL>   (#<IN_PROGRESS_COLOR>)
    [• <IN_REVIEW_LABEL>    (#<IN_REVIEW_COLOR>)   — 4-state only]

  .project-conf.toml to write in cwd:
    system = "github"
    key    = "<OWNER_REPO>"
    prefix = "<PREFIX>"
    [status_labels]
    in_progress = "<IN_PROGRESS_LABEL>"
    [in_review  = "<IN_REVIEW_LABEL>"   — 4-state only]

It will NOT modify issues, PRs, branches, or any other repo settings.

Proceed? [y/N]
```

If `n` or empty: stop with `"No changes made."`

## Step 6 — Existing config check

If `.project-conf.toml` already exists in cwd:

1. Parse it (use Python `tomllib` inline or shell line-matching — whatever is available).
2. If `system` is not `"github"`: stop with `"Existing config has system='<value>'. Refusing to overwrite a non-GitHub project."`
3. If `key` does not match `$OWNER_REPO`: stop with `"Existing config points to '<key>'; current repo is '<OWNER_REPO>'. Refusing to overwrite."`
4. Otherwise note "existing config detected — will merge `[status_labels]`."

## Step 7 — Create labels (idempotent)

For each required label (`IN_PROGRESS_LABEL` always; `IN_REVIEW_LABEL` only for 4-state):

**Check existence:**

- **CLI:** `$GH label list --repo $OWNER_REPO --json name -q '.[].name'` — look for exact match.
- **MCP:** `${GH_MCP_NS}issue_read` (or equivalent list call) is not label-aware; fall back to CLI `gh label list` for the existence check even in MCP mode (labels are not in the issue MCP).

**If missing — create:**

```bash
$GH label create "<LABEL_NAME>" \
    --color "<HEX_NO_HASH>" \
    --description "<DESC>" \
    --repo "$OWNER_REPO"
```

Descriptions:
- `status:in-progress` → `"Ticket is actively being worked on"`
- `status:in-review` → `"Code complete; shake-down validation in progress"`

If `gh label create` fails: stop immediately with the error. Do not proceed to the next label or to config write.

**If already present:** print `"  label '<name>' already exists — skipping"` and continue.

## Step 8 — Write .project-conf.toml

Build the TOML content:

```toml
system = "github"
key    = "<OWNER_REPO>"
prefix = "<PREFIX>"

[status_labels]
in_progress = "<IN_PROGRESS_LABEL>"
# in_review = "<IN_REVIEW_LABEL>"   ← include only for 4-state
```

**If file absent:** write it directly using the Write tool (or shell heredoc). Use an atomic write: write to `.project-conf.toml.tmp` then rename to `.project-conf.toml`.

**If file exists and passed Step 6 checks:** read the existing content, replace or add `[status_labels]` section while preserving all other sections (`[rag]`, `[exp]`, `[autonomous]`, etc.), and rewrite. Use the same atomic write pattern.

## Step 9 — Output

```
ticket-gh-init complete.

  <result for in-progress label>   (created | already existed)
  <result for in-review label>     (created | already existed | skipped — 3-state)
  .project-conf.toml               (written | updated — merged [status_labels])

Next steps:
  /slopstop-create-gh <title>   — create your first issue
  /slopstop-start <PREFIX>-N    — begin work on an existing issue
```

## Error matrix

| Condition | Behavior |
|---|---|
| Not in a git repo | Stop: `"Run inside a git repository with a GitHub remote."` |
| No GitHub remote | Stop: `"No GitHub remote found at origin."` |
| `gh auth status` fails | Stop with auth instructions |
| `gh repo view` fails | Stop: `"Could not determine GitHub repo."` |
| Existing config for wrong system | Stop: `"Existing config has system='<v>'. Refusing to overwrite."` |
| Existing config for wrong repo | Stop: `"Existing config points to '<key>'. Refusing to overwrite."` |
| Label creation fails | Stop with raw API/CLI error; report any labels already created |
| Config write fails | Stop with OS error; temp file + rename prevents partial write |
| User cancels repo confirm | Stop: `"No changes made."` |
| User cancels workflow question | Stop: `"No changes made."` |
| User cancels final proceed | Stop: `"No changes made."` |
