# archive-system-detection — Step 1 detail

## Backend resolution — read `system` first, then search once

Read `system` from `.project-conf.toml` and set `$SYSTEM` (title-cased: `JIRA`, `Linear`,
`GitHub`) **before** searching. Then run **only** that system's ToolSearch — a matching
search returns full tool schemas, so searching for backends this project does not use
buys nothing and costs thousands of tokens per invocation.

**JIRA** —

```
ToolSearch(query="select:mcp__atlassian__getJiraIssue,mcp__atlassian__editJiraIssue,mcp__atlassian__addCommentToJiraIssue,mcp__atlassian__getAccessibleAtlassianResources", max_results=8)
```

Empty → stop: `"system='jira' in .project-conf.toml but no Atlassian MCP found. Configure it and retry."`

**Linear** —

```
ToolSearch(query="select:mcp__linear-server__get_issue,mcp__linear-server__save_issue,mcp__linear-server__save_comment", max_results=8)
```

Empty → stop: `"system='linear' in .project-conf.toml but no Linear MCP found. Configure it and retry."`

**GitHub** — resolve `$GH_BACKEND`:
- Canonical search: `ToolSearch(query="select:mcp__github__get_issue,mcp__github__add_issue_comment,mcp__github__update_issue,mcp__github__list_issue_comments", max_results=8)`. Non-empty → `$GH_BACKEND = "MCP"`, `$GH_MCP_NS = "mcp__github__"`.
- Canonical empty → run fallback: `ToolSearch(query="select:mcp__plugin_github_github__get_me,mcp__plugin_github_github__add_issue_comment,mcp__plugin_github_github__issue_write", max_results=8)`. If non-empty → `$GH_BACKEND = "MCP"`, `$GH_MCP_NS = "mcp__plugin_github_github__"`.
- Both empty → `$GH_BACKEND = "CLI"`. Find `gh` binary by trial path: `/usr/local/bin/gh`, `$HOME/.local/bin/gh`, `/opt/homebrew/bin/gh`, then `command -v gh`. Save as `$GH`. If none resolve, stop: `"Neither GitHub MCP nor 'gh' CLI found. Install one of: gh CLI (https://cli.github.com/) or the github plugin (/plugin install github@claude-plugins-official)."`. Verify auth: `$GH auth status` must succeed.

See `design/github-backend-primitives.md` for the full primitives + rationale.
