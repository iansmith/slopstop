# GitHub Backend Detection

Run one ToolSearch to detect the plugin GitHub MCP (the only MCP namespace that exposes `issue_write`, which this skill uses):

```text
ToolSearch(query="select:mcp__plugin_github_github__issue_write,mcp__plugin_github_github__issue_read", max_results=4)
```

Resolution order:

1. Plugin search non-empty → `$GH_BACKEND = "MCP"`, `$GH_MCP_NS = "mcp__plugin_github_github__"`.
2. Empty → `$GH_BACKEND = "CLI"`. Locate `gh` binary by trying `/usr/local/bin/gh`, `$HOME/.local/bin/gh`, `/opt/homebrew/bin/gh`, then `command -v gh`. Save as `$GH`. If none resolve: stop with `"Neither GitHub MCP nor 'gh' CLI found."`. Verify auth: `$GH auth status` must succeed.
