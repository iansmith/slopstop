# Plan: Explore Prompt Template (Step 1c detail)

Full prompt to pass to the `Explore` subagent:

```
Investigate the codebase for ticket $TICKET ($TICKET_TITLE).

Ticket description:
<paste from task_plan.md's Original description>

Constraint on this investigation: <$ARGUMENTS or "none">

Find and report:
1. Relevant modules and file boundaries
2. Entry points (functions / types that any change would start from)
3. Dependencies (what the relevant code depends on; what depends on it)
4. Existing patterns to honor (conventions, public API contracts, etc.)
5. Risks (anti-patterns to avoid, fragile areas, places where changes ripple unexpectedly)

Stay within the constraint. Do not investigate areas the constraint excludes, even if they look interesting.

Report in structured markdown with the five headings above.
```
