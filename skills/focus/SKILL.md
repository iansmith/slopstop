---
description: Mid-session ticket re-tag. Use /slopstop:focus <TICKET> (e.g. /slopstop:focus BILL-201) to re-point this session's router attribution without branch creation or ticket transition. Use /slopstop:focus --clear to reset. Requires [fleet.router] enabled = true.
disable-model-invocation: true
---

# /slopstop:focus

Lightweight mid-session re-tag command.

## Behaviors

1. `/slopstop:focus <TICKET>` (e.g. `/slopstop:focus BILL-201`) POSTs `/tag` to re-point attribution. Does nothing else.

2. Invalid argument errors: `"Usage: /slopstop:focus <TICKET> (e.g. /slopstop:focus BILL-201) or /slopstop:focus --clear"`

3. Router disabled/unreachable: `"Router is <disabled | unreachable> — attribution not updated."`

4. `/slopstop:focus --clear` (or `/slopstop:focus untagged`) clears the run-id mapping.

5. No run-id in headers: `"Attribution unavailable — session launched without X-Slopstop-Run."`

## Implementation

See shared recipe at `skills/start/references/router-tag-post.md` for POST /tag pattern.

Validate ticket format: `^[A-Za-z][A-Za-z0-9]*-\d+$`

Read `[fleet.router] enabled` from `.project-conf.toml`.

Extract `X-Slopstop-Run` from `ANTHROPIC_CUSTOM_HEADERS`.

Health-check: `curl -s http://<host>:<port>/spend`

On success, POST: `curl -X POST -H "Content-Type: application/json" -d '{"run":"<run-id>","ticket":"<TICKET>"}' http://<host>:<port>/tag`

Clear path POSTs with empty ticket string.

No silent failures — every path reports to user.
