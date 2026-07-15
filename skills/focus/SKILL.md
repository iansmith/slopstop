---
description: Mid-session ticket re-tag. Use /slopstop:focus <TICKET> (e.g. /slopstop:focus BILL-201) to re-point this session's router attribution without branch creation or ticket transition. Use /slopstop:focus --clear to reset. Requires [fleet.router] enabled = true.
disable-model-invocation: true
---

# /slopstop:focus

Lightweight mid-session re-tag command.

## Behaviors

1. `/slopstop:focus <TICKET>` (e.g. `/slopstop:focus BILL-201`) POSTs `/tag` to re-point attribution. Does nothing else.

2. Invalid argument errors: `"Usage: /slopstop:focus <TICKET> (e.g. /slopstop:focus BILL-201) or /slopstop:focus --clear"`

3. Router disabled/unreachable: `"Router is <disabled | unreachable> — attribution not updated."` (:focus emits this message explicitly, overriding the shared recipe's default silence).

4. `/slopstop:focus --clear` (or `/slopstop:focus untagged`) clears the run-id mapping.

5. No run-id in headers: `"Attribution unavailable — session launched without X-Slopstop-Run."`

## Implementation

See shared recipe at `~/.claude/commands/slopstop-start-refs/router-tag-post.md` for POST /tag pattern.

**Parse order:** Check for `--clear` or the literal argument `untagged` FIRST. Only run the ticket-format regex check on arguments that aren't one of those two.

Validate ticket format: `^[A-Za-z][A-Za-z0-9]*-\d+$`

Read `[fleet.router] enabled` from `.project-conf.toml`.

Extract `X-Slopstop-Run` from `ANTHROPIC_CUSTOM_HEADERS`.

When router is disabled or unreachable, :focus emits its own status message (overriding the shared recipe's default silence).

No silent failures — every path reports to user.
