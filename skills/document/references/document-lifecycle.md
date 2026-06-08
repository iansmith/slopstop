# When to use :document

- **At the "In Review" gate** — run right after `:merge`. Reviewers see the ticket's agreed plan, DoD, and findings alongside the PR. Without it, the ticket may still hold only the original problem statement.
- **Mid-ticket checkpoint** — push a snapshot for stakeholder visibility (PM, client). Re-run any time; idempotent.
- **Inlined by `/slopstop:archive`** — archive's Step 3 runs this skill's body, then moves the local dir. If `:document` stops on divergence, `:archive` propagates the stop.

## Lifecycle position

```
:merge       → code merged, ticket advanced to In Review, branch cleaned up.
               Docs NOT touched on the ticket — :merge deliberately stops short.
                                       │
                                       ▼
:document    → push plan + DoD-confirmation + findings to the ticket. Now the
               reviewer has the ticket-as-document alongside the PR.
                                       │
            (reviewer reads the ticket + the PR, signs off, transitions
             the ticket to a terminal Done-type state)
                                       │
                                       ▼
:archive     → push any last documentation updates (idempotent — usually a
               clean no-op), then mv local tracking to ticket-archive/.
```

The separation is deliberate: `:merge` ships code, `:document` populates the ticket for review, `:archive` closes the local lifecycle. Workflows without an "In Review" gate collapse `:document` and `:archive` into a single `:archive` invocation — `:document`'s body is inlined there anyway.
