---
description: Semantic search over the project's RAG-indexed ticket corpus and code graph. /slopstop:search "<query>" finds tickets by semantic similarity (descriptions + comments); optional subcommands --callers, --implementors, --blast-radius, and --ticket-code navigate the SCIP code graph. Reads [rag] from .project-conf.toml (endpoint, corpus_scope); gracefully degrades if [rag] is absent or if the RAG service is not running.
disable-model-invocation: true
---

# /slopstop:search

Semantic search over the project's ticket corpus and code graph, using the local RAG service.

Five modes: semantic ticket search (default), `--callers`, `--implementors`, `--blast-radius`, and `--ticket-code`. The RAG service must be running locally — if it is not, the skill prints a clear error and stops.

## Arguments

`$ARGUMENTS` — the full argument string passed to this command.

If `$ARGUMENTS` is empty, or starts with `--` but does not match a known flag (e.g. bare `--callers`, `--callers=foo`, unrecognised flag): print usage and stop. For the unrecognised-flag case, prepend `"Unknown flag or missing argument."`.

```
Usage:
  /slopstop:search "<query>"                       semantic ticket search
  /slopstop:search --callers <moniker>             who calls this symbol?
  /slopstop:search --implementors <moniker>        what implements this interface?
  /slopstop:search --blast-radius <moniker>        what breaks if I change this?
  /slopstop:search --ticket-code <ticket-id>       what code did this ticket touch?
```

Parse mode from `$ARGUMENTS` (each flag must be followed by whitespace and a value):

| Prefix | `$MODE` | Capture |
|---|---|---|
| `--callers` | `callers` | `$MONIKER` = remainder (strip whitespace + quotes) |
| `--implementors` | `implementors` | `$MONIKER` = remainder |
| `--blast-radius` | `blast-radius` | `$MONIKER` = remainder |
| `--ticket-code` | `ticket-code` | `$TICKET_ID` = remainder |
| _(none of the above)_ | `search` | `$QUERY` = `$ARGUMENTS` stripped of surrounding quotes |

## Step 1 — Read config

Read `.project-conf.toml` from cwd.

- If the file does not exist: stop with `"No .project-conf.toml in cwd. Run /slopstop:gh-init (for GitHub) or create the file manually with system + key."`.
- Extract `system` (top-level key — e.g. `"github"`, `"linear"`, `"jira"`).
- Extract `[rag].endpoint` if present; default to `"http://127.0.0.1:7777"`. Store as `$RAG_ENDPOINT`.
- Extract `[rag].corpus_scope` if present; default to the value of `system`. Store as `$CORPUS_SCOPE`.

(If `[rag]` is absent entirely, defaults apply — do NOT stop.)

## Step 2 — Load tools and health check

Load all RAG tools in one call:

```
ToolSearch(
  query="select:mcp__slopstop-rag__rag_health,mcp__slopstop-rag__search_tickets,mcp__slopstop-rag__get_callers,mcp__slopstop-rag__get_implementors,mcp__slopstop-rag__get_blast_radius,mcp__slopstop-rag__get_ticket_code",
  max_results=8
)
```

Call `rag_health()`.

Health fails if: MCP error, `postgres` != `"ok"`, or `schema` != `"ok"`.

On health failure, print:

```
RAG service is not running or not ready.

postgres: <value from response, or "unreachable">
schema:   <value from response, or "unreachable">

Start the service with:
  docker start slopstop-rag-dev        # if using the dev container
  make rag-dev-start                   # or via the Makefile

Then re-run your search.
```

Stop. Do not attempt the query.

## Step 3 — Execute query

| Mode | Tool call |
|---|---|
| `search` | `search_tickets(query=$QUERY, k=5, rerank=true, project=$CORPUS_SCOPE)` |
| `callers` | `get_callers(moniker=$MONIKER)` |
| `implementors` | `get_implementors(moniker=$MONIKER)` |
| `blast-radius` | `get_blast_radius(moniker=$MONIKER)` |
| `ticket-code` | `get_ticket_code(ticket_id=$TICKET_ID)` |

## Step 4 — Render results

### Search results (`$MODE = "search"`)

Render each result with rank, ticket ID, kind, score, and first 3 lines of text (max 240 chars). Append count footer.

→ Read `~/.claude/commands/slopstop-search-refs/search-result-render-search.md` for the full render spec.

### Code-graph results (`$MODE ∈ {callers, implementors, blast-radius, ticket-code}`)

Print a mode-specific heading; list each result as `` `$location` ``, marking external entries. End with result count.

→ Read `~/.claude/commands/slopstop-search-refs/search-result-render-codegraph.md` for the full render spec.
