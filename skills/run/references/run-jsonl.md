# `run.jsonl` — the one definition

Every orchestrator (`:design`, `:tickets`, `:run`) writes this file. Read this instead of
inventing a shape; three divergent schemas is three analyses that disagree.

## What it is

An **append-only JSONL** recording every state transition of a run. It is simultaneously
three things, which is why there is only one of it:

1. **The state machine** — where each ticket has got to.
2. **The resume point** — a long run gets compacted; if state lives only in the
   orchestrator's context, compaction loses the run.
3. **The timing record** — every transition is timestamped by definition, so the log read
   end to end *is* the timing data. There is no second artifact.

## Where it lives

| writer | path |
|---|---|
| `:design`, `:tickets` | `scratch/runs/$RUN_ID/run.jsonl` |
| `:run` | **each ticket's own tracking dir** — one file per ticket |

Per-ticket placement for `:run` means an archived ticket carries its own timing, and there
is no "which umbrella?" question for an ad-hoc ticket list. Analysis across a run is
concatenation.

## The orchestrator is the sole writer

No worker writes here. No worker resolves the tracking dir. A worker returns its result;
the orchestrator stamps it. One writer means no interleaved-append races across tickets
running concurrently, and it means a worker cannot record a state the orchestrator does not
know about.

## Line shape

One JSON object per line. **Every line carries `at`** — ISO-8601 UTC, `date -u +%FT%TZ`.

```json
{"ticket":"BILL-501","stage":"red-tests","event":"started","at":"2026-08-06T14:02:11Z"}
{"ticket":"BILL-501","stage":"red-tests","event":"finished","at":"2026-08-06T14:07:48Z","result":"4 tests, all red"}
{"ticket":"BILL-501","stage":"implement","event":"started","at":"2026-08-06T14:07:52Z"}
{"ticket":"BILL-501","stage":"implement","event":"failed","at":"2026-08-06T14:31:02Z","result":"2 of 4 still red"}
```

`event` is one of:

| event | meaning |
|---|---|
| `started` | a span opened |
| `finished` | that span closed successfully |
| `failed` | that span closed unsuccessfully — **still a close** |
| `note` | a point-in-time fact, not a span. Never needs closing. |

`ticket` is omitted for run-level spans (`:design`'s and `:tickets`' work is not
per-ticket). `stage` is the worker skill's name for worker spans, or a short verb for
orchestrator-inline work.

## Human waits are spans too

**This is the whole reason the file can distinguish machine time from a weekend.** Whenever
the orchestrator blocks on a human, it brackets that wait:

```json
{"stage":"waiting_for_user","event":"started","at":"...","result":"grill Q7"}
{"stage":"waiting_for_user","event":"finished","at":"...","result":"grill Q7"}
```

Wall clock is meaningless on its own — a `:plan` span once measured 45,843 seconds because
someone went to bed, and one interactive ticket clocked 550.9 minutes wall against 45.5
minutes of actual agent work. The orchestrator knows when it is blocked, because it is the
thing doing the blocking. So it records it, and nothing has to guess afterwards.

Also write a `session_resume` note on every resume. A session that dies and restarts days
later leaves a gap bracketed by nothing; that note bounds it.

## Computing time

One pass over one file:

| quantity | computation |
|---|---|
| wall clock | `last.at − first.at` |
| human idle | `Σ` `waiting_for_user` spans |
| **active time** | `wall − human_idle` |
| agent-seconds | `Σ` worker spans — *exceeds* active under parallelism, like CPU-seconds vs elapsed |
| unattributed | active minus the union of attributed spans |

**"Active" is active *elapsed*, not inference time.** Tool execution, model inference and
orchestrator overhead all sit inside it. Splitting those needs transcript-level data, which
this design deliberately does not collect. Say "active", never "compute".

**Report unattributed time. Never redistribute it.** It is a number, not a rounding error.

## Validation — how an incomplete record announces itself

**Read this part twice.** The predecessor system failed here, not at writing.
`~/gaston/.slopstop/metrics/pipeline.json` held three keys — no `started_at`, no `branch`,
no `completed_at`, at the wrong path — and **passed every check that existed**. A partial
write that looked like a successful one. Its numbers flowed downstream as though complete.

An unclosed span here has exactly that shape: a `started` with no `finished` is
indistinguishable from a short span unless something looks.

**The invariants:**

1. Every `started` is closed by exactly one `finished` or `failed` with the same
   `(ticket, stage)`.
2. No `finished`/`failed` without a preceding `started` for that `(ticket, stage)`.
3. Every line parses as JSON and carries `at`.
4. A completed run's last line is `{"event":"note","stage":"run_closed",...}`. Its absence
   means the orchestrator died mid-run — which is legitimate state, not corruption, but it
   is **not** a finished run.

**Validate at two points, without exception:** on resume, before continuing; and at run
end, before reporting anything.

**When validation fails, report no timing numbers at all.** Name the unclosed spans and
stop. This is the rule that matters — a broken record must not be able to produce a
plausible-looking summary. Partial data that flows to a consumer as if whole is the exact
failure being designed out, and "best effort" here recreates it.

## Writing discipline

The `started` line is written **as part of the same step that launches the work**, and the
`finished` line **as part of the same step that receives the result** — never as a separate
thing to remember afterwards. A stamp that is its own step is a stamp that gets skipped;
that is precisely how the predecessor produced one file in three weeks across three repos.

Append with `>>`. Never rewrite, never compact, never delete a line — history is the point,
and both endpoints are needed for every duration.
