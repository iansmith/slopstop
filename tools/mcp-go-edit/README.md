# go-edit — whitespace-tolerant Go editor MCP server

A tiny stdio MCP server (stdlib-only Python, no deps) exposing one tool,
`mcp__go-edit__edit`. It is a drop-in for the built-in `Edit` tool, specialized
for `.go` files:

- **Whitespace-tolerant matching** — `old_string` matches the file ignoring
  whitespace *shape*: every run of whitespace in `old_string` matches `\s+` in
  the file. You don't have to reproduce exact tabs/indentation.
- **gofmt on every edit** — after a successful replacement it runs `gofmt -w`
  on the file.
- **Atomic** — if `gofmt` rejects the post-edit file (broken syntax), the
  original is restored and the tool returns an error. A green edit is always a
  gofmt-clean edit.

Same uniqueness rule as `Edit`: exactly one match unless `replace_all=true`.

## Why it lives in the repo

The slopstop fleet launches headless coding agents (`claude -p`) that edit the
Go router. Two defects this buys us:

1. Agents kept leaving files unformatted — this run integrated 6 gofmt-dirty
   files because no leaf DoD required `gofmt` and agents never ran it. go-edit
   makes every edit gofmt-clean or fail, closing that gap at the source.
2. Exact-whitespace `Edit` failures waste agent turns re-reading files to
   reproduce tabs. Whitespace-tolerant matching removes that class of retry.

Vendored (committed) so fleet worktrees carry it and the run is reproducible
without depending on any path outside the repo.

## Wiring

**Interactive maintainer sessions** — registered in the repo-root `.mcp.json`
via `${CLAUDE_PROJECT_DIR}/tools/mcp-go-edit/server.py`.

**Headless fleet agents** — project `.mcp.json` servers are not auto-enabled in
`claude -p` (they'd need interactive approval), so the launch line passes the
server explicitly and allows the tool:

```
claude -p "<brief>" --model haiku --effort medium --permission-mode auto \
  --mcp-config /Users/iansmith/ticket-plugin/tools/mcp-go-edit/fleet-mcp-config.json \
  --allowedTools "Bash(gh:*)" "Bash(git:*)" "Bash(go:*)" "Bash(python3:*)" \
                 "Write" "Edit" "mcp__go-edit__edit" \
  --add-dir /Users/iansmith/ticket-plugin/.slopstop \
  --output-format stream-json --verbose > <run>/streams/BILL-<N>.jsonl 2>&1
```

The brief must instruct the agent to **prefer `mcp__go-edit__edit` over `Edit`
for any `.go` file** (built-in `Edit` stays available for non-Go files and as a
fallback).

`fleet-mcp-config.json` uses an absolute path to *this* (main-repo) copy of
`server.py` so it resolves identically from every worktree, independent of when
the vendoring commit lands on master.
