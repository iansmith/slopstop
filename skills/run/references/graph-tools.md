# Codebase knowledge graph — when and how to use it

When the `codebase-memory-mcp` MCP server is available, prefer its graph tools over
grep/Read for **structural** code queries. The graph is pre-indexed and returns focused,
typed results — a `trace_path` call replaces a grep-then-read-each-file chain that
costs 5–10× the tokens.

## Tool selection

| Question | Graph tool | Replaces |
|----------|-----------|----------|
| What functions/types exist named X? | `search_graph` | `grep -rn "func X\|class X"` |
| What calls function X? / What does X call? | `trace_path` | grep for symbol + Read each hit |
| Module layout, package boundaries | `get_architecture` | ls + Read multiple files |
| Multi-hop: X calls Y which imports Z | `query_graph` | chained greps |
| Exact source of a symbol | `get_code_snippet` | Read with offset/limit guessing |
| Text search with structural context | `search_code` | grep (still valid as fallback) |

## When to fall back to grep/Read

- Literal string search in non-code files (config, markdown, YAML)
- The graph index does not cover the file (`check_index_coverage` returns uncovered)
- The query is about file content, not structure (e.g. "does this config key appear?")

## Verification rule

**`check_index_coverage` before any negative or exhaustive claim.** "No callers exist"
or "this is the only implementation" must be checked against coverage — the graph is
best-effort, not proof of completeness. A negative claim on an uncovered file is
unverified.

## Availability

The tools are present when `codebase-memory-mcp` is in the session's MCP server list.
If the tools are not available, proceed with grep/Read as before — graph tools are an
optimization, not a dependency.
