# Codebase knowledge graph — when and how to use it

**You MUST use graph tools for structural code queries when `codebase-memory-mcp` is
available.** This is not a suggestion. Before your first grep for a function name,
symbol, caller, or type definition, check whether graph tools are in your tool list.
If they are, use them — not grep. The graph is pre-indexed and returns focused, typed
results; a `trace_path` call replaces a grep-then-read-each-file chain that costs
5–10× the tokens.

**Why this is a MUST, not a preference.** Measured across six runs (PLTF-2723,
SOP-562–564, PLTF-2736, SOP-586, PLTF-2727): 1,262+ grep/Read discovery calls and
**zero** graph calls, even with the tools available and every repo indexed. "Prefer"
does not work. The tools exist, the data is there, and the fallback is not needed.

## First action for any worker that reads code

Before doing any code discovery, run `list_projects` to confirm the graph is available
and the project is indexed. If it succeeds, you have graph tools — use them for every
structural query below. If it fails, fall back to grep/Read and note the failure.

## Tool selection

| Question | Graph tool | grep/Read (use ONLY when graph unavailable) |
|----------|-----------|----------------------------------------------|
| What functions/types exist named X? | `search_graph` | `grep -rn "func X\|class X"` |
| What calls function X? / What does X call? | `trace_path` | grep for symbol + Read each hit |
| Module layout, package boundaries | `get_architecture` | ls + Read multiple files |
| Multi-hop: X calls Y which imports Z | `query_graph` | chained greps |
| Exact source of a symbol | `get_code_snippet` | Read with offset/limit guessing |
| Text search with structural context | `search_code` | grep (still valid as fallback) |

## When grep/Read is correct (not a fallback)

- Literal string search in non-code files (config, markdown, YAML)
- The graph index does not cover the file (`check_index_coverage` returns uncovered)
- The query is about file content, not structure (e.g. "does this config key appear?")

Using grep for these is correct, not a failure. Using grep to find function callers or
symbol definitions when graph tools are available IS a failure — state why if you do it.

## Verification rule

**`check_index_coverage` before any negative or exhaustive claim.** "No callers exist"
or "this is the only implementation" must be checked against coverage — the graph is
best-effort, not proof of completeness. A negative claim on an uncovered file is
unverified.

## Availability

The tools are present when `codebase-memory-mcp` is in the session's MCP server list.
Every fleet repo is indexed. If the tools are genuinely not available (the MCP server
is not connected), proceed with grep/Read — but this is an abnormal condition, not the
default. Note it in your output so the orchestrator can diagnose.
