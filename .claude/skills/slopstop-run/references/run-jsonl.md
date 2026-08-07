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

`event` is `span` or `note`. A `span` line carries `state`:

| event | state | meaning |
|---|---|---|
| `span` | `started` | a span opened |
| `span` | `finished` | that span closed successfully |
| `span` | `failed` | that span closed unsuccessfully — **still a close** |
| `note` | — | a point-in-time fact, not a span. Never needs closing. |

```json
{"event":"span","stage":"prd","state":"started","at":"…"}
{"event":"span","stage":"prd","state":"finished","at":"…","result":"prd.md written — 8 decisions"}
```

*(This two-field shape replaced a flatter `event: started|finished|note` on 2026-08-06.
The first real `:design` run produced this shape on its own, and it is better: one glance
separates span lines from notes, and `stage` means the same thing on every line. The spec
moved to the writer rather than the other way round — but the two disagreeing at all is
what the validation rules below exist to catch.)*

`ticket` is omitted for run-level spans (`:design`'s and `:tickets`' work is not
per-ticket). `stage` is the worker skill's name for worker spans, or a short verb for
orchestrator-inline work.

## Which stages are spans, and which are notes

**A span measures a duration. A note records that something happened.** Choosing wrongly is
not cosmetic — it produces a file that fails validation, and a file that fails validation
reports no timing at all.

| use a **span** when | use a **note** when |
|---|---|
| a worker is launched | the act is a single atomic command or API call |
| a loop round runs (adversary, review) | the duration is noise and varies with nothing |
| a human is waited on | it is a point-in-time fact (a size, a verdict, a hold) |
| the work's duration varies with its input | |

**The test is whether the duration varies with the input**, not what it happened to measure
once. A worker launch that came back fast is still a span.

`:run`'s state-machine table marks every stage with this, so nothing has to be re-derived
per run. `:design` and `:tickets` have their own stages and the same rule applies to them.

### Why an atomic act must not be a span

`git switch -c` and `git commit` finish instantly. Bracketing one leaves two bad options and
no good one:

- **a zero-second span** — invariant 5 below calls that suspect, correctly, because it is
  indistinguishable from a stamp written from memory afterwards; or
- **a close-only line** — an orphan close, which invariant 2 rejects outright.

Both are wrong, and a run that picks either voids its own timing. Recorded live: a run wrote
close-only lines for `branch`, `phase0-commit` and the file-map check, its validation caught
all three, and the whole ticket's timing became unreportable — three instantaneous acts, no
duration lost, all timing gone. The instinct behind it was right (*these have nothing to
bracket*) and the schema simply never said a note was the answer.

### A note may fail

A note carries `result` like a span does, and **a note whose result is a failure stops the
ticket** exactly as a `failed` span would. It just does not need a `started` line to be
well-formed, so nothing has to be fabricated to make the record valid.

```json
{"ticket":"BILL-501","event":"note","stage":"branch","at":"…","result":"feat/BILL-501 from a1b2c3d"}
{"ticket":"BILL-502","event":"note","stage":"branch","at":"…","result":"failed: branch already exists"}
```

### `stage` comes from the table, never invented

Every `stage` value must be one the writer's own state machine lists. A run recorded a stage
called `filemap`; there is no such stage — the file-map check lives inside `tamper` — and
nothing caught it, because only span pairing was validated. One pass over the file is
supposed to reconstruct the run, and an invented name defeats exactly that. See invariant 6.

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

## Record the change size, or the timing answers nothing

Durations alone cannot tell you what to skip. "The review stage took 6 minutes" is only
useful next to "…on a 14-line, 2-file change." **Write the size signal as a `note` once the
diff exists** — after `implement`, before the PR:

```json
{"ticket":"BILL-501","event":"note","stage":"size","at":"…",
 "lines_changed":622,"files_changed":33,
 "production_lines":203,"production_files":2,
 "test_lines":419,"test_files":31,
 "test_globs":["*_test.go","**/*_test.*","testdata/**","tests/**","spec/**","__tests__/**"],
 "files":[
   {"path":"linker.go","added":131,"removed":46,"kind":"production"},
   {"path":"arfmt.go","added":15,"removed":11,"kind":"production"},
   {"path":"weak_def_test.go","added":241,"removed":0,"kind":"test"},
   {"path":"testdata/weak_armem.c","added":5,"removed":0,"kind":"test"}
 ],
 "tier":"standard","tier_basis":"production"}
```

### Take the numbers from `--numstat`, per file

```bash
git diff --numstat "$BASE"..HEAD
```

Three tab-separated columns per file: **added, removed, path**. Use this, not `--stat` —
`--stat` is formatted for humans, with aligned bars and abbreviated paths, and parsing it
back into numbers is a needless step that loses precision on long paths.

**Record one entry per file, not just the aggregates.** The aggregates are what you will
usually read, but they are a lossy summary of a classification that may turn out wrong:
if `test_globs` misses a language's convention, per-file data lets you **re-classify a past
run retroactively**. Aggregates alone cannot be re-asked, and a run cannot be repeated.

This is not theoretical. Reclassifying GAST-8 under two different glob sets:

| `test_globs` | production | tier |
|---|---|---|
| `*_test.go` only | 381 lines / 32 files | **`large`** |
| plus `testdata/**` and the rest | 203 lines / 2 files | **`standard`** |

One run, one diff, two answers — because 31 of its files were per-case C fixtures under
`testdata/`, which the narrower rule counts as production. Recording the aggregates alone
would have frozen whichever answer the rule of the day happened to give.

`kind` is `production` or `test`, decided by `test_globs`. The aggregates must equal the
sum of the per-file entries — if they disagree, the note is wrong and says so twice.

Two shapes `--numstat` emits that a naive parser gets wrong:

- **Binary files** give `-` for added and removed (`-⇥-⇥logo.png`). Count them in
  `files_changed`, contribute **0** to the line counts, and say how many were binary. A
  parser that reads `-` as a number crashes; one that skips the row silently undercounts
  the file.
- **Renames** appear as `old => new` in the path column when rename detection is on. Record
  the path as written and do not try to split it — a rename with no edits is 0/0 and should
  not inflate anything.

### Split production from tests, or the label is wrong every time

**`production_*` and `test_*` must be recorded separately.** The totals alone are actively
misleading here, and the first real run proved it. GAST-8 changed **33 files / 622 lines**
(added + removed, from `--numstat`), which the rule below calls **`large`**. Its production code was **2 files
/ 203 lines** — `standard`. The other 31 files, 419 lines, were tests and
one-C-fixture-per-case `testdata/` files.

**`lines_changed` is added + removed, not net.** GAST-8's production diff is +146/−57: 203
by this metric, 89 net. The ticket that specified this work quoted the net figure and
predicted `trivial`; recomputing it during implementation gave `standard`, and the
prediction was simply wrong. Two bands still separate the totals from the production
counts, which is the point — but state the metric you mean, because 89 and 203 fall in
different bands.

That is not an outlier, it is the design working. **Slopstop deliberately produces far more
test than implementation**, so a classifier fed the totals will call slopstop's own output
`large` essentially always, and skip nothing, forever. The mistake is not the thresholds;
it is counting the wrong thing.

**`test_globs` records the rule you classified by**, in the note itself. A later analysis
must not have to guess whether `testdata/**` counted as test material — the answer changes
the numbers, and a past run cannot be re-asked.

A path matching no test glob is production. When a language's convention is not in the list
above, add it and say so; do not silently classify by intuition.

### The tier is a label on data, not a decision

Compute it **from the production counts** — `tier_basis: "production"` records that — and
**record it. Nothing reads it. Nothing skips.**

| | trivial | standard | large |
|---|---|---|---|
| lines changed | ≤ 20 | 21–300 | > 300 |
| files changed | ≤ 2 | 3–15 | > 15 |

`trivial` needs **both** bands; `large` needs **either** threshold crossed; everything else
is `standard`.

**These numbers are a hypothesis, not a specification.** They are carried forward from a
classifier that was deleted in the 2026-08-06 reorg precisely so its thresholds would stop
being treated as settled. Recording the label next to the real durations is what will
confirm or move them. When enough runs exist, check whether cost actually clusters at these
boundaries — and if it does not, move them rather than defending them.

**Changing what is counted and changing where the boundaries sit are two experiments.**
This is the first; run it alone. Moving the thresholds in the same change makes neither
interpretable.

## One span per adversary round — never one span per loop

The adversary loop runs up to three rounds, and each round is a separate worker launch.
**Bracket each launch**: `started` when that round is launched, `finished`/`failed` when
its verdict comes back, carrying the round number and the verdict.

```json
{"ticket":"BILL-501","stage":"adversary","event":"span","state":"started","at":"…","round":2}
{"ticket":"BILL-501","stage":"adversary","event":"span","state":"finished","at":"…","round":2,"result":"FAIL: 3"}
```

Do **not** open one span at round 1 and close it at round 3 with notes in between. GAST-8
did exactly that and recorded **1050 seconds as a single lump** for rounds 1–3. The
adversary was the most expensive stage in that run — about 22 of 78 minutes — and whether
that is three even rounds or one expensive round and two cheap ones is precisely the
question a skip decision turns on. The notes recorded the verdicts; nothing recorded the
cost.

A round that is capped, escalated, or human-authorized past the cap is still its own span.

## Verification verdicts, the blessed SHA, and attempts

The verification stages leave three kinds of line. They are here rather than only in the
report because **the report is the orchestrator grading its own homework** — the file is the
external record, and a verdict that exists only in a summary cannot be audited against the
run that produced it.

**Every verdict is a `result` on the span that produced it, spelled exactly as
`handoff-verification.md` defines it** — `TAMPER CLEAN`, `TAMPER FAIL: <file>:<line>`,
`TAMPER BLOCKED: <guard>`, `FILEMAP CLEAN`, `FILEMAP FAIL: <paths>`,
`HANDOFF BLESSED: <sha>`, `HANDOFF FAIL: <n>`. Do not paraphrase them into prose; a later
pass over the file classifies on these strings.

```json
{"ticket":"BILL-501","event":"span","stage":"tamper","state":"started","at":"…"}
{"ticket":"BILL-501","event":"span","stage":"tamper","state":"failed","at":"…","result":"TAMPER FAIL: tests/test_codec.py:41"}
```

**The blessing is a `note`, and it carries the SHA it binds to.** A blessing recorded
without one is a blessing about nothing:

```json
{"ticket":"BILL-501","event":"note","stage":"handoff","at":"…",
 "verdict":"BLESSED","blessed_sha":"3f9a1c…"}
```

It is re-checked at merge. When the tip has advanced past `blessed_sha`, write a fresh
`handoff` span for the re-verification rather than editing the old note — the file is
append-only, and *both* blessings are the record of what happened.

**Attempts are counted from the file, not from memory.** An attempt is one `implement` or
`handoff` span that closed `failed`; nothing stores a counter. Counting them by reading is
what makes the count survive compaction, and it is why a resume can tell a first attempt
from a third. Record the diagnosis at the second failure as a `note` — `ticket-defect`,
`capability-gap`, or `undiagnosed` — because a bad ticket and a weak model look identical
in a failure count and completely different in a ledger that says which it was.

**A preserved stop gets its own `note`** naming the branch, both SHAs, the worktree path
where one exists, and the commit count. See `failure-and-salvage.md`; the branch name later
resolves to a *moved* tip, so the SHA is the truth and both are recorded.

## A hold is a note, not a span

A ticket held by an unsatisfied `Blocked by:` has **not run**, so it must not open a span.
Record a `note` when the hold is decided, and another when it is released:

```json
{"ticket":"BILL-502","event":"note","stage":"held","at":"…",
 "blocked_by":["BILL-501"],"unsatisfied":["BILL-501"],"reason":"not merged"}
{"ticket":"BILL-502","event":"note","stage":"released","at":"…","after":"BILL-501"}
```

The ticket's first real span opens **after** the release note. Two things this gets right
that a span would not: a held ticket contributes nothing to agent-seconds (nothing ran), and
it is not `waiting_for_user` — no human is being waited on, so folding it into human-idle
would inflate exactly the number that exists to separate machine time from a weekend.

A ticket held at run end simply has a `held` note and no spans. That is a complete,
well-formed record of a ticket that never started — **not** an unclosed span, and the
validation rules below must not read it as one.

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
   `(ticket, stage)`. **Spans only** — a note has nothing to close.
2. No `finished`/`failed` without a preceding `started` for that `(ticket, stage)`.
   **Spans only.** A stage recorded as a note cannot be an orphan close by construction,
   which is the point of marking them.
3. Every line parses as JSON and carries `at`.
6. Every `stage` value appears in the writer's own state-machine table. An unrecognised
   value is a failure — name it and the nearest legal value.
4. A completed run's last line is `{"event":"note","stage":"run_closed",...}`. Its absence
   means the orchestrator died mid-run — which is legitimate state, not corruption, but it
   is **not** a finished run.
5. **A non-`waiting_for_user` span of 0 seconds is reported as suspect.** Not an error —
   some work really is instant — but a span that opened and closed in the same second for
   work that produced a file is almost certainly a stamp written from memory afterwards
   rather than at the moment.

   This is not hypothetical. The first real `:design` run recorded `classify` finishing,
   `prd` starting *and* finishing, and `charter` starting *and* finishing at one identical
   timestamp: an 11.6 KB PRD and a 3.8 KB charter, both measured at zero seconds. The
   human-idle bracketing in the same run was flawless across eight interleaved waits. The
   discipline held where it was hard and lapsed where it was easy, because writing four
   stamps at the end *feels* like bookkeeping rather than measurement.

   Report suspect spans by name alongside the timing. A zero that is announced can be
   investigated; a zero that is averaged in silently corrupts every conclusion drawn from
   the file.

**Validate at two points, without exception:** on resume, before continuing; and at run
end, before reporting anything.

**When validation fails, report no timing numbers at all.** Name what broke, precisely and
by invariant — **unclosed spans** for invariant 1, **orphan closes** for invariant 2,
**unknown stages** for invariant 6. They are different defects with different causes and
"validation failed" alone tells the next reader nothing. Then stop. This is the rule that matters — a broken record must not be able to produce a
plausible-looking summary. Partial data that flows to a consumer as if whole is the exact
failure being designed out, and "best effort" here recreates it.

## Writing discipline

The `started` line is written **as part of the same step that launches the work**, and the
`finished` line **as part of the same step that receives the result** — never as a separate
thing to remember afterwards. A stamp that is its own step is a stamp that gets skipped;
that is precisely how the predecessor produced one file in three weeks across three repos.

**Take the timestamp from the clock, not from memory.** Every `at` comes from an actual
`date -u +%FT%TZ` at the instant of the transition. Reconstructing several stamps at the
end of a phase is how four transitions end up sharing one second — the file still validates,
still looks complete, and has silently lost the durations it existed to record.

Append with `>>`. Never rewrite, never compact, never delete a line — history is the point,
and both endpoints are needed for every duration.
