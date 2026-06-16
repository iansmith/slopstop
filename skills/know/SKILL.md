---
description: "Use when asked what a function does, who calls it, what tickets reference it, what its history is, or whether it might be dead code. Orchestrates get_code_context + callers-with-cc + search_tickets + commit history into a unified answer about a code symbol. --dead-code flag runs a dead-candidates sweep instead."
---

# /slopstop:know

Answer "what does this function do, who calls it, and what tickets changed it?" in one shot.

Two modes:
- **Symbol mode** (default): given a SCIP moniker or plain function name, assembles a unified view from the code graph, ticket corpus, and git history.
- **Dead-code mode** (`--dead-code`): scans for uncalled functions ranked by cyclomatic complexity, classified by confidence.

## Arguments

`$ARGUMENTS` — the full argument string.

**Symbol mode:** `$ARGUMENTS` is a SCIP moniker or a plain function/symbol name.
**Dead-code mode:** `$ARGUMENTS` starts with `--dead-code` (optionally followed by `--cc-threshold <N>`).

If `$ARGUMENTS` is empty or `--help`: print usage and stop.

```
Usage:
  /slopstop:know <moniker-or-name>          full symbol report
  /slopstop:know --dead-code                dead-code sweep (all CC)
  /slopstop:know --dead-code --cc-threshold <N>   dead-code sweep, CC >= N
```

## Step 1 — Read config and load tools

Read `.project-conf.toml` from cwd.
- Missing → stop: `"No .project-conf.toml in cwd."`
- Extract `[rag].endpoint` (default `"http://127.0.0.1:7777"`). Store as `$RAG_ENDPOINT`.
- Extract `[rag].corpus_scope` (default = `system` value). Store as `$CORPUS_SCOPE`.
- Extract `[rag].repo` if present (default `""`). Store as `$CODE_GRAPH_REPO`.

Load RAG tools in one call:
```
ToolSearch(
  query="select:mcp__slopstop-rag__rag_health,mcp__slopstop-rag__get_code_context,mcp__slopstop-rag__get_callers_with_cc,mcp__slopstop-rag__get_dead_candidates,mcp__slopstop-rag__search_tickets",
  max_results=8
)
```

Call `rag_health()`. On failure print the same error block as `/slopstop:search` and stop.

## Step 2 — Dead-code mode

*Skip to Step 3 when in symbol mode.*

Parse `--cc-threshold <N>` from `$ARGUMENTS` (default 0).

Call `get_dead_candidates(repo=$CODE_GRAPH_REPO, cc_threshold=N, limit=50)`.

Render tiered output:

```
## Dead-code candidates (CC >= <N>)

### likely_dead (<count>)
| Function | File | CC |
|---|---|---|
| `<moniker-name>` | `<file_path>` | <cc> |
...

### possibly_dead (<count>)
(functions with IMPLEMENTS edge or entry-point name — may still be live)
| Function | File | CC | Reason |
|---|---|---|---|
| `<moniker-name>` | `<file_path>` | <cc> | implements interface / entry-point name |
...

<N> candidates total. Run `/slopstop:know <moniker>` on any to get the full picture.
```

For `<moniker-name>`, extract just the simple name token (the part before `().` or `.`).
For `Reason`, show "implements interface" when `has_implements=true`, else "entry-point name".

Stop after rendering.

## Step 3 — Symbol mode: resolve the moniker

`$INPUT` = `$ARGUMENTS` stripped of surrounding whitespace and quotes.

**If `$INPUT` looks like a SCIP moniker** (contains `scip-` prefix): use it directly as `$MONIKER`.

**Otherwise** (plain function name): search for it.
- Call `search_tickets(query=$INPUT, k=5, rerank=true, project=$CORPUS_SCOPE, kind=["docstring"])`.
- If results include a `moniker` field: take the first non-null moniker as `$MONIKER`.
- If no docstring hit: call `search_tickets(query=$INPUT, k=3, rerank=false, project=$CORPUS_SCOPE)` for context only. Set `$MONIKER = null` and skip Steps 4–5 (no graph traversal possible). Render Step 6 with whatever ticket hits exist.

## Step 4 — Parallel graph + ticket queries

Run these **in parallel** (all independent):

| Call | Purpose |
|---|---|
| `get_code_context(monikers=[$MONIKER])` | ticket linkage via TOUCHES edges |
| `get_callers_with_cc(moniker=$MONIKER, repo=$CODE_GRAPH_REPO)` | callers + CC |
| `search_tickets(query=$INPUT, k=5, rerank=true, project=$CORPUS_SCOPE)` | semantic ticket hits |

## Step 5 — Commit history

From the `get_code_context` result, extract up to 5 most recent commits (already present in the `commits` list). No extra git call needed.

## Step 6 — Render unified report

```
## <simple-name> — symbol report

### What it is
<From docstring search hit (kind='docstring'), first 3 lines of `text`. Or: "No docstring found in ticket corpus.">

### Cyclomatic complexity
Target CC: <target_cc from get_callers_with_cc, or "unknown">

### Callers (<count>)
<If 0 callers: "No in-graph callers found. Consider running --dead-code sweep.">
<If callers present:>
| Caller | File | CC | Test |
|---|---|---|---|
| `<name>` | `<file_path>` | <cc or —> | <yes/no> |
...
<Show all callers, mark test=true rows with "(test)"  in the Test column.>

### Tickets that reference this symbol (<count>)
<Deduplicated list of ticket IDs from get_code_context + semantic search hits.>
<For each: "- BILL-42 — <first line of text from search hit, if available>">
<If none: "No ticket references found.">

### Recent commits (<count>, up to 5)
<From get_code_context commits list:>
- `<sha[0:7]>` <authored_at[0:10]> — <subject>
<If none: "No commit history found in graph.">
```

**Simple name extraction**: for a SCIP moniker like `"scip-python ... linesOverlap()."`, the simple name is the token immediately before the trailing descriptor suffix — e.g. `linesOverlap`.

## Rules

- Never fabricate CC values, callers, or ticket IDs. Show exactly what the graph returns.
- If the RAG service is not running, stop after the health check error.
- Parallel calls in Step 4 run concurrently; do not serialize them.
- Dead-code mode renders tiered output and stops; it does not invoke Step 3 or beyond.
