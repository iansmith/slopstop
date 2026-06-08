# GitHub Backend Detection

Run two ToolSearches in parallel:

```text
ToolSearch(query="select:mcp__plugin_github_github__issue_write,mcp__plugin_github_github__issue_read", max_results=4)
ToolSearch(query="select:mcp__github__create_issue,mcp__github__update_issue", max_results=4)
```

Resolution order:

1. Canonical `mcp__github__` search non-empty → `$GH_BACKEND = "MCP"`, `$GH_MCP_NS = "mcp__github__"`.
2. Plugin search non-empty → `$GH_BACKEND = "MCP"`, `$GH_MCP_NS = "mcp__plugin_github_github__"`.
3. Both empty → `$GH_BACKEND = "CLI"`. Locate `gh` binary by trying `/usr/local/bin/gh`, `$HOME/.local/bin/gh`, `/opt/homebrew/bin/gh`, then `command -v gh`. Save as `$GH`. If none resolve: stop with `"Neither GitHub MCP nor 'gh' CLI found."`. Verify auth: `$GH auth status` must succeed.
