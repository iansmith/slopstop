---
description: Semantic search over the project's RAG-indexed ticket corpus and code graph. /slopstop:search "<query>" finds tickets by semantic similarity (descriptions + comments); optional subcommands --callers, --implementors, --blast-radius, and --ticket-code navigate the SCIP code graph. Reads [rag] from .project-conf.toml (endpoint, corpus_scope); gracefully degrades if [rag] is absent or if the RAG service is not running.
disable-model-invocation: true
---

# /slopstop:search

Semantic search over the project's ticket corpus and code graph, using the local RAG service.

Five modes: semantic ticket search (default), `--callers`, `--implementors`, `--blast-radius`, and `--ticket-code`. The RAG service must be running locally — if it is not, the skill prints a clear error and stops.

## Arguments

`$ARGUMENTS` — the full argument string passed to this command.

If `$ARGUMENTS` is empty, or if `$ARGUMENTS` starts with `--` and does not match any known flag below (e.g. bare `--callers`, `--callers=foo`, unrecognised flag): print usage and stop. For the unrecognised-flag case, prepend `"Unknown flag or missing argument."` before the usage block.

```
Usage:
  /slopstop:search "<query>"                       semantic ticket search
  /slopstop:search --callers <moniker>             who calls this symbol?
  /slopstop:search --implementors <moniker>        what implements this interface?
  /slopstop:search --blast-radius <moniker>        what breaks if I change this?
  /slopstop:search --ticket-code <ticket-id>       what code did this ticket touch?
```

Parse mode from `$ARGUMENTS`:
- Starts with `--callers` followed by whitespace → `$MODE = "callers"`, `$MONIKER` = remainder (strip leading/trailing whitespace and quotes).
- Starts with `--implementors` followed by whitespace → `$MODE = "implementors"`, `$MONIKER` = remainder.
- Starts with `--blast-radius` followed by whitespace → `$MODE = "blast-radius"`, `$MONIKER` = remainder.
- Starts with `--ticket-code` followed by whitespace → `$MODE = "ticket-code"`, `$TICKET_ID` = remainder.
- Otherwise → `$MODE = "search"`, `$QUERY` = `$ARGUMENTS` stripped of surrounding quotes.

## Step 1 — Read config

Read `.project-conf.toml` from cwd.

- If the file does not exist: stop with `"No .project-conf.toml in cwd. Run /slopstop:gh-init (for GitHub) or create the file manually with system + key."`.
- Extract `system` (top-level key — e.g. `"github"`, `"linear"`, `"jira"`).
- Extract `[rag].endpoint` if present; default to `"http://127.0.0.1:7777"`. Store as `$RAG_ENDPOINT`.
- Extract `[rag].corpus_scope` if present; default to the value of `system`. Store as `$CORPUS_SCOPE`.

(If `[rag]` section is absent entirely, the defaults apply — do NOT stop. This is expected for projects that haven't configured a custom endpoint.)

## Step 2 — Load tools and health check

Load all RAG tools in one call (mode is already known from the Arguments section above):

```
ToolSearch(
  query="select:mcp__slopstop-rag__rag_health,mcp__slopstop-rag__search_tickets,mcp__slopstop-rag__get_callers,mcp__slopstop-rag__get_implementors,mcp__slopstop-rag__get_blast_radius,mcp__slopstop-rag__get_ticket_code",
  max_results=8
)
```

Call `rag_health()`.

Evaluate the response:
- If the tool call raises an error (connection refused, MCP server not found, etc.) → health failed.
- If the response has `"postgres"` set to anything other than `"ok"` → health failed.
- If the response has `"schema"` set to anything other than `"ok"` → health failed.

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

Run the tool call for the current mode:

| Mode | Tool call |
|---|---|
| `search` | `search_tickets(query=$QUERY, k=5, rerank=true, project=$CORPUS_SCOPE)` |
| `callers` | `get_callers(moniker=$MONIKER)` |
| `implementors` | `get_implementors(moniker=$MONIKER)` |
| `blast-radius` | `get_blast_radius(moniker=$MONIKER)` |
| `ticket-code` | `get_ticket_code(ticket_id=$TICKET_ID)` |

## Step 4 — Render results

### Search results (`$MODE = "search"`)

If the result list is empty:
```
No results found for '$QUERY'.

The corpus may not be indexed yet — see rag-service/README.md for sync instructions.
```
Stop.

For each result (rank 1–N, already sorted by the service), bind these fields from the chunk:
- `$RESULT_TICKET_ID` = `result.ticket_id` (the ticket key, e.g. `BILL-42`).
- `$RANK` is the 1-based position in the result list.
- `$SCORE` is formatted to two decimal places (e.g. `0.87`).
- `$KIND` is the `kind` field (e.g. `description`, `comment`).
- `$CHUNK_TEXT` is the `text` field truncated to the first 3 lines (split on `\n`), then truncated to 240 characters if the result still exceeds that; append `…` if truncated.

Then render:

```
### $RANK. **$RESULT_TICKET_ID** · $KIND · score $SCORE

$CHUNK_TEXT
```

After rendering all results, append:
```
_Top $N results. For more filters (source, kind, provenance, date range) use the `search_tickets` MCP tool directly._
```

### Code-graph results (`$MODE ∈ {callers, implementors, blast-radius, ticket-code}`)

Print a heading based on mode:

| Mode | Heading |
|---|---|
| `callers` | `## Callers of \`$MONIKER\`` |
| `implementors` | `## Implementors of \`$MONIKER\`` |
| `blast-radius` | `## Blast radius of \`$MONIKER\`` |
| `ticket-code` | `## Code touched by $TICKET_ID` |

If zero results: print `"No results found."` and stop.

For each result row (fields: `moniker`, `file_path`, `line`, `location`, `lang`, `repo`, `external`):
- If `external` is true: `- \`result.moniker\` _(external — not in local index)_`
- Otherwise: `- \`$location\`` with `location` in `file_path:line` form — if `location` is already pre-formatted by the server use it directly, otherwise construct it.

After listing results, append the count:
```
$N result(s).
```
