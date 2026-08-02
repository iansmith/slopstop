# Design brief — move metric emission from prose to lifecycle

**For a `/slopstop:design` session.** Written 2026-08-02, after running BILL-282
end-to-end specifically to test whether the existing metrics plumbing produces a
usable measurement. It half worked, and the half that failed did so for a reason
that reframes the whole problem.

Everything below is observed, not inferred. Reproduce any of it before designing on it.

---

## What we set out to measure

How long a ticket takes, how long a fleet agent takes from launch to confirmed
handoff, and what each costs in tokens. The existing pieces looked sufficient:
`pipeline.json` for wall-clock, the `cost-tracker.py` Stop hook for tokens, the
router for per-ticket USD.

## What we actually found

### Finding 1 — the emit is discretionary, so it mostly doesn't happen

`metrics_emit_path` had been set in three fleet repos since ~2026-07-16. In that
time the entire fleet produced **one** `pipeline.json` (gaston's), containing only
`ticket` and two Phase 0 counts. No `started_at`, no `branch`, no `completed_at` —
and written to `.slopstop/metrics/pipeline.json` rather than the
`.slopstop/metrics/<TICKET>/pipeline.json` that every consumer resolves.

The cause is not a broken writer. **There is no writer.** Skills are prose; the
stub exists only if the agent executing `:start` chooses to follow the instruction.
That run didn't, and `:plan`'s "create it if absent" fallback silently absorbed the
omission — so a missing stub produced a plausible-looking file instead of an error.

BILL-282's run produced a complete, correctly-pathed record — but only because the
executing agent was deliberately watching for it. That is not a property you can
build a benchmark on.

### Finding 2 — the Stop hook is session-anchored; cost needs to be ticket-anchored

BILL-282's window was `06:26:13Z → 06:31:26Z` (5.2 min). **Zero `costs.jsonl` rows
landed inside it.** The nearest preceding row was 06:14:03, twelve minutes earlier.

The Stop hook fires when a *session turn* ends, not when a ticket completes. A
ticket finished inside one uninterrupted agent turn produces no row in its own
window at all. This is worse for the fleet, not better: a headless `claude -p` runs
an entire ticket in a single invocation, so the hook fires exactly once, at the very
end, with one cumulative total covering everything it did.

Timestamp-joining `costs.jsonl` against `pipeline.json` therefore cannot work in
general. The earlier plan — add a `ticket` field, make rows deltas — treats the
symptom. The defect is the trigger.

### Finding 3 — transcripts already carry ticket attribution, for free

`~/.claude/projects/` contains one directory per working directory, and fleet agents
run in worktrees named after their ticket:

```
-Users-iansmith-lyos-mobile-v2-worktrees-PLTF-2454
-Users-iansmith-aatoolkit-worktrees-AATK-10
```

The ticket is in the path. Transcripts also carry per-message `usage` and `model`
(this is what the Stop hook and `baseline/analyze.py` already read). So the raw
material for per-ticket token accounting exists today, with no new plumbing and no
launch-time configuration.

### Finding 4 — the router cannot see interactive work, by construction

`ANTHROPIC_BASE_URL` and the tagging headers are fixed at process launch, and a
session cannot re-point itself mid-flight (`router/README.md`, Phase-1 limit 2).
Throughout this work the router read `requests: 0`. Its counters are also in-memory
— a restart zeroes them, with no history endpoint.

## The design question

**Move metric emission from discretionary prose to a mechanical, lifecycle-triggered
mechanism.** Findings 1 and 2 are the same defect seen from two sides: emission is
attached to the wrong thing (an agent's compliance; a session's end) instead of to
the ticket lifecycle events that actually delimit the work.

Concretely, the shape to design toward:

- **`:start` and `:merge` are the anchors.** They already bracket a ticket exactly.
  A `:merge`-time read of the transcript — the same summation `cost-tracker.py`
  already performs — written into `pipeline.json` gives ticket-anchored tokens with
  no reliance on when a session happened to stop.
- **Mechanical, not narrated.** Whatever performs the emit should fail loudly when
  it cannot, rather than being an instruction an agent may skip. Gaston's file is
  the cautionary case: a partial write that looked like a successful one.
- **Fleet agents get the same treatment.** Launch → first commit → handoff-verified
  → stop_reason, per agent. `:plan` already records exactly these fields in
  structured `.agents.json`; `:run` records the same facts as prose in
  `fleet-state.md`. Closing that gap is most of item 4.

## What this implies for the router

For **metering**, transcripts strictly dominate it: they cover interactive sessions
the router cannot see, they carry per-message model and usage, and worktree agents
self-attribute by path with no headers. Pricing is not a router capability —
`prices.toml` is a table, and it can be applied wherever the arithmetic happens.
Keep the table (including its deliberate ~1.3× effective-rate adjustment, and label
any number derived from it as effective, not invoice-accurate).

The router remains the only source for: **Phase 2 tier-aware routing** (its actual
roadmap, not a metering feature); **non-Claude-Code or multi-provider clients**
(issue #241); and wire-level events a transcript never records — failed requests,
retries, raw byte metering.

None of those are what we are trying to measure now. If the lifecycle emit lands,
the launch-time `ANTHROPIC_BASE_URL` / `X-Slopstop-Run` dance is no longer required
for cost measurement, which removes a genuinely error-prone step.

**This is a recommendation to design against, not a decision to delete anything.**
Nothing here argues for removing the router; it argues that metering should stop
depending on it.

## Open questions for the session

1. **What performs the emit?** A hook has the wrong trigger (Finding 2). A skill
   instruction has the wrong reliability (Finding 1). A small script invoked by
   `:start`/`:merge` is the obvious third option — but that is the first executable
   code in a repo that went deliberately skills-only in BILL-136. Is that a line
   worth re-crossing, and if so, where does it live?
2. **How is a partial record detected?** Gaston's file passed every existing check.
   What makes an incomplete `pipeline.json` loud instead of plausible?
3. **`metrics_emit_path` has no documented path-resolution rule** — absent from
   `CONFIG.md`, not covered by `tracking-dir-resolution.md`. The relative form is
   de-facto convention only. Fleet agents run from linked worktrees, which is
   precisely where an unspecified relative path diverges. Specify it.
4. **Does the `:merge`-time transcript read work for fleet agents?** The agent's
   tokens are in *its* worktree transcript; `:merge` runs from the orchestrator.
   Reading across is possible (the path encodes the ticket) but needs designing.
5. **What happens to `costs.jsonl`?** If `:merge` reads transcripts directly, the
   Stop hook may be redundant — or may remain the only source for work that never
   becomes a ticket. Decide rather than letting both drift.

## Reproducing the evidence

```bash
cat ~/ticket-plugin/.slopstop/metrics/BILL-282/pipeline.json   # the complete record
cat ~/gaston/.slopstop/metrics/pipeline.json                   # the incomplete one
tail -3 ~/ticket-plugin/.slopstop/metrics/costs.jsonl          # rows outside the window
curl -s 'http://127.0.0.1:8484/spend?prefix=BILL'              # requests: 0
ls ~/.claude/projects/ | grep worktrees                        # ticket-in-path attribution
```

## Related

- `~/slopbench/docs/collect-enrichment.md` — the consumer-side spec, blocked on this.
- Issue #241 — router multi-provider model spec.
- BILL-282 (merged, `e5498fa`) — the ticket this was measured against.
