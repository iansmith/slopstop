# Post-commit graph re-index hook (BILL-90)

## Overview

After every successful `git commit` in a slopstop session, the code graph
should be refreshed automatically. This document describes the `PostToolUse`
hook mechanism, the `graph_index_on_commit` config key, and the hook's
expected behavior.

## Mechanism

Claude Code's `PostToolUse` hook fires after a tool call completes. The hook
is registered on the `Bash` tool. On each Bash call that ends with exit
code 0 and whose `tool_input.command` matches `\bgit commit\b`, the hook
triggers a background graph re-index.

### Hook configuration shape (project `.claude/settings.json`)

```json
{
  "hooks": {
    "PostToolUse": [
      {
        "matcher": "Bash",
        "hooks": [
          {
            "type": "command",
            "command": "bin/post-commit-reindex.sh"
          }
        ]
      }
    ]
  }
}
```

The hook script (`bin/post-commit-reindex.sh`) is responsible for:

1. Checking that the completed Bash call was a `git commit` (inspect
   `$CLAUDE_TOOL_INPUT_COMMAND` or parse stdin).
2. Verifying the RAG service is healthy (`GET /healthz`).
3. Running the SCIP indexer pipeline against the post-commit tree
   (same pipeline as BILL-59/BILL-84), then POSTing the resulting
   index to `POST /code-graph/ingest`.
4. Logging `[graph] indexing triggered after commit <sha>` to stderr
   (visible in the session status line).

All of this runs in the background (hook exits 0 immediately, spawning
the indexer as a background process). The commit itself is never blocked.

## Config key: `graph_index_on_commit`

In `.project-conf.toml`:

```toml
[hooks]
graph_index_on_commit = true   # default: true when RAG service is healthy
```

When `false`, the `PostToolUse` hook is a no-op (skips the re-index).
When `true` (default) and the RAG service is unavailable, the hook logs a
warning and exits 0 without blocking the commit.

## Cyclomatic complexity (CC) on function nodes

Every Function node written or updated by the post-commit indexer must carry
`cyclomatic_complexity: int` (the `PROP_CYCLOMATIC_COMPLEXITY` schema constant
from BILL-89). The indexer pipeline:

1. Uses the SCIP indexer's native CC output when available (scip-go supports
   this; scip-typescript may in future versions).
2. Falls back to a `lizard` post-processing pass for Python (and any other
   language in `[code-graph] languages` where SCIP doesn't emit CC natively).

When neither source provides CC for a function, the property is omitted from
the Cypher SET clause so that any existing value is preserved (MERGE semantics).

## Failure handling

- RAG service unavailable → log warning, skip re-index, exit 0. Commit succeeds.
- SCIP indexer error → log error with sha, exit 0. Commit succeeds.
- Hook script itself errors → Claude Code logs the hook failure; commit already succeeded.

## Installation

The hook will be part of the plugin install flow and will not require a manual
`.git/hooks/` step. The `bin/post-commit-reindex.sh` script and the
`.claude/settings.json` hook registration will be included in the plugin's
project scaffold (applied by `/slopstop:gh-init` or equivalent setup command).
