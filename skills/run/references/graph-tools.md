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

## The split: graph for discovery, grep/Read for content

**Discovery** = finding where things are, what calls what, how code is structured.
**Content** = reading/editing actual file text, checking values, non-code files.

Graph owns discovery. grep/Read owns content. They are not fallbacks for each other —
they answer different questions.

### Discovery (graph tools — MUST use when available)

| Question | Tool |
|----------|------|
| What functions/types exist named X? | `search_graph` |
| What calls function X? / What does X call? | `trace_path` |
| Module layout, package boundaries | `get_architecture` |
| Multi-hop: X calls Y which imports Z | `query_graph` |
| Exact source of a symbol | `get_code_snippet` |
| Text search with structural context | `search_code` |

### Content (grep/Read — always correct for these)

- Reading file content to understand or edit it
- Checking exact string values, config keys, feature flags
- Non-code files: config, YAML, markdown, `.toml`, `.json`, `.gitignore`
- Test output, build logs, runtime artifacts
- Files `check_index_coverage` reports as uncovered

Using grep/Read for content is the right tool, not a fallback. Using grep for
discovery (finding callers, locating definitions, tracing dependencies) when graph
tools are available is wrong — state why if you do it.

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
