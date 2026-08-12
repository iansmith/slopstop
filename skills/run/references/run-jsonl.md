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

### The launch note — what a worker was actually given

> **PART ADVISORY, PART LOAD-BEARING — the tuple is not one thing (BILL-543).** BILL-496
> demoted the whole note on the grounds that `.slopstop/metrics/hook-events.jsonl` had
> replaced it. Measured 2026-08-09 across 413 hook events in three repos, that is true of two
> fields and false of two others, and the two it is false about are the ones anybody asks
> questions with. Per-field ownership is the table below; read it before deciding whether a
> missing value matters.
>
> Where this note and the hook record disagree **on a field the hook owns, the hook record is
> right**, and the disagreement is kept rather than repaired: it measures how reliably prose is
> followed, which is the open question this file sits in the middle of. Do not "fix" a
> disagreement by editing history.

**Every worker launch writes one note carrying the resolved tuple**, in the same step that
writes the `started` line and calls `Agent()`:

```json
{"ticket":"PLTF-2563","event":"note","stage":"implement","at":"…","launch":{
  "worker":"implement","tier":"small","model":"sonnet","effort":"high",
  "subagent_type":"slopstop-effort-high","subagent_type_used":"slopstop-effort-high"}}
```

| field | meaning | owner | if missing |
|---|---|---|---|
| `worker` | the skill invoked — the roster name in `worker-launch.md` | this note | **defect** |
| `tier` | the `[stage_tiers]` result, or the documented default when the key is absent | **this note, and nothing else** | **defect** |
| `model` | what `tier` resolved to, as passed on the `Agent()` call | this note; recoverable from the transcript until it is deleted | **defect** |
| `effort` | the resolved effort — the tier's, or **lower** where a stage requires it | the hook record | advisory |
| `subagent_type` | the carrier requested | this note | advisory |
| `subagent_type_used` | the carrier that actually resolved | the hook record (`agent_type`) | advisory |
| `subagent_model_env` | the value of `CLAUDE_CODE_SUBAGENT_MODEL`, **only when it is set** | this note | see below |

### Why `tier` and `model` are not advisory, whatever the rest of the tuple is

**No hook will ever emit `tier`.** It is a slopstop concept — the `[stage_tiers]` → `[tiers]`
resolution — and the harness has never heard of it. There is no second source to fall back
to, so a launch without it is a launch whose tier is gone.

**`model` is not in the hook payload.** Measured over 413 hook events across three fleet
repos (305 / 55 / 53): the keys present are `hook_event_name`, `session_id`,
`prompt_id`, `agent_id`, `agent_type`, `effort`, `cwd`, `permission_mode`, `at`, `source`,
`payload_keys`, `transcript_path`, `agent_transcript_path`. **`model` is absent from all
413.** A `SubagentStart`'s own `payload_keys` shows why — the harness hands the hook seven
fields and model is not one of them. This is not a recorder bug; the data never arrives.

`tools/metrics/derive.py` does recover `model_observed` per launch, but from the **session
transcript**, which is not durable: this file records that PLTF-2563's transcripts were
deleted at archive time for being 25 MB. A field that survives only until someone reclaims
disk is not a record.

So: **`worker`, `tier` and `model` are required on every launch note and are checked by
invariant 7.** `effort`, `subagent_type` and `subagent_type_used` stay advisory exactly as
BILL-496 left them, because for those three the hook record genuinely is authoritative and
genuinely is there.

**`subagent_type` and `subagent_type_used` are separate fields on purpose.**
`worker-launch.md` permits falling back to `general-purpose` when a carrier does not resolve.
Recorded as one field, a fallback is invisible: the run reads as configured while the effort
has silently reverted to the session's. Two fields make the fallback a diff, not a footnote.

### `CLAUDE_CODE_SUBAGENT_MODEL` — the one way this record is confidently wrong

That environment variable **outranks everything slopstop resolves**: the per-invocation
`model` parameter and subagent frontmatter both. If it is set, the `model` written above is
what the orchestrator *asked for* and not what ran, and every tier comparison built on this
file compares two tiers that were one tier.

**Check it at intake and record it.** Write `subagent_model_env` on every launch note **when
and only when the variable is set** — its presence is the alarm, so a run whose notes never
carry it is a run where it was never set. Do not write `null` or `""` to mean unset: an
explicit "no override" on 40 launch notes is noise, and this file's standing rule is that a
missing value and a zero value must not read alike.

A recorded model that is not the model that ran is worse than no record at all — no record
produces no conclusion, and this produces a confident wrong one.

**One note per launch, never per span.** A `gates` span covers `slop-check` and
`complexity-check` — two launches under one span, and they need not share a tier. Fields on
the span line cannot express that, and the first time two gate workers differ the span-level
version would report one of them as both.

**Why this is worth writing when the harness already knows it.** It is not novel data — the
harness records model and effort per subagent, and that record is the ground truth this note
is checked against. It is written because it is *small and durable*: PLTF-2563's session
transcripts were deleted at archive time for being 25 MB, and this tuple is a few hundred
bytes. An archived ticket has to stay auditable after the transcript is gone.

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

Compute it from the counts of **whatever the ticket's mode makes the deliverable**, and put
which in `tier_basis`. Then **record it. Nothing reads it. Nothing skips.**

| mode | count | `tier_basis` |
|---|---|---|
| `normal` | production | `"production"` |
| `refactor` | production | `"production"` — the tests are frozen, so production already *is* the deliverable |
| `backfill` | **test** | `"test"` — production is frozen; the test file is the deliverable |

| | trivial | standard | large |
|---|---|---|---|
| lines changed | ≤ 20 | 21–300 | > 300 |
| files changed | ≤ 2 | 3–15 | > 15 |

`trivial` needs **both** bands; `large` needs **either** threshold crossed; everything else
is `standard`.

**Backfill is not an exception bolted onto the rule — it is the rule.** The reason to count
production rather than totals is to count the deliverable and not the noise. In backfill
mode production changes are *forbidden*, so `production_lines` is **definitionally 0** and a
production basis counts nothing at all: every backfill ticket scores `trivial` regardless of
what it delivers. Measured on PLTF-2562 — `tier: "trivial"`, `tier_basis: "production"`,
`production_lines: 0`, **`test_lines: 334`** — a full backfill run with a mutation-proof
deliverable, labelled as the cheapest thing the vocabulary has.

**`tier` is one of `trivial` / `standard` / `large` and nothing else.** No qualifier, no
sentence, no fourth value. PLTF-2531 recorded 160 characters of reasoning *inside the field*
— `"medium — 312 production lines added across 7 files; the 4:1 test-to-production ratio
reflects…"` — which is unreadable to anything, names a band that does not exist here, and
disagrees with its own numbers (312 lines crosses `> 300`, so `large`). `medium` belongs to
the **model**-tier ladder (huge/large/medium/small); the two vocabularies share two words and
are not the same thing. Reasoning goes in `result`, which is what `result` is for.

**Record `production_lines`, `production_files`, `test_lines` and `test_files` as top-level
integers on the note.** Not nested, not implied by a per-file list a reader has to re-add.
GAST-8 recorded `{"lines_changed": 645, "files_changed": 36, "tier": "large"}` with no split
at all — the totals-based label this section exists to prevent, on the very run it uses as
its worked example.

`derive.py --check` validates all of the above and names each violation, because prose alone
produced four different note shapes across the nine runs measured on 2026-08-12.

**These numbers are a hypothesis, not a specification.** They are carried forward from a
classifier that was deleted in the 2026-08-06 reorg precisely so its thresholds would stop
being treated as settled. Recording the label next to the real durations is what will
confirm or move them. When enough runs exist, check whether cost actually clusters at these
boundaries — and if it does not, move them rather than defending them.

**Changing what is counted and changing where the boundaries sit are two experiments.**
This is the first; run it alone. Moving the thresholds in the same change makes neither
interpretable.

## One span per round — never one span per loop

**Every looping stage.** Stage 7's `adversary` (cap 3), stage 9's pinning pass
(`mutation-check --implemented`, cap 3), stage 10's `review` (cap 5) and stage 10b's
`handoff` all run a round as a separate worker launch. **Bracket each launch**: `started`
when that round is launched, `finished`/`failed` when its verdict comes back, carrying the
round number and the verdict.

The adversary is the worked example below because it is where the rule was first paid for,
but the rule is not about the adversary.

`round` goes on **both** endpoints — see invariant 1b. It is a label, not part of the pairing
key; invariant 1 states the key and this section does not restate it (universal §5).

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

## What a review primitive found — a field, not a sentence

**Every close of a `review`, `adversary` or `handoff` span carries a `findings` object.**
These are the review primitives; they are the only stages that produce findings classified by
severity, and they are the stages every "did the tier above buy anything?" question is about.

```json
{"ticket":"BILL-501","event":"span","stage":"review","state":"finished","at":"…","round":1,
 "result":"REVIEW APPLIED: 3 | applied 3 (blocker 1, major 2, minor 0) | reported 2 (blocker 0, major 0, minor 2)",
 "findings":{
   "applied":  {"blocker":1,"major":2,"minor":0},
   "reported": {"blocker":0,"major":0,"minor":2},
   "class":    {"behavioural":4,"presentational":1}}}
```

| key | meaning |
|---|---|
| `applied` | findings the worker fixed itself, by severity |
| `reported` | findings it surfaced and deliberately did **not** apply, by severity |
| `class` | the independent `behavioural`/`presentational` split over `applied` + `reported` |

**Severity and class are `adversary`'s vocabulary — `blocker`/`major`/`minor` and
`behavioural`/`presentational`, defined in `skills/adversary/SKILL.md` §Severity and §Class.**
They are not redefined here and there is no second set of names. `red`/`yellow`/`gray` is a
*rendering* choice for a report, downstream of this record, and must never be written into it.
Neither is 🔴/🟡, which is `slop-check`'s two-level gate vocabulary for a different question.

**Copy the numbers out of the worker's verdict line; never re-derive them from its prose.**
`review` returns the split on its verdict line (`skills/review/SKILL.md`), `adversary` returns
severities on its numbered findings. The orchestrator's job is transcription. Inferring a
severity the worker did not state is the exact failure this field exists to end — and the
`result` string stays on the line beside it precisely so the transcription can be audited.

**`applied` and `reported` are different findings and neither is the total.** A round that
finds five, fixes three and reports two has `APPLIED: 3` and a `findings` object summing to
five. Flattening them loses the case that matters most: declining to edit inside a frozen
Phase 0 file is *correct*, and it must not read as a fix that was never made.

**Refuted and unconfirmed findings are in neither triple.** A finding whose premise is wrong
is not a small defect; it is not a defect. Counting it would put it back into a distribution
it was removed from.

### An absent `findings` and an all-zero `findings` are different facts

This is the whole point of the field, and the failure this file has recorded twice already —
*"something measured zero, and zero read as fine."*

- **`findings` present, all zeros** — the worker ran and found nothing. A real, load-bearing
  measurement.
- **`findings` absent** — nothing was recorded. Says nothing about the code.

**Never write an all-zero object to stand in for a missing one**, and never let a reader
default an absent one to zero. A stage-10 review that was simply not instrumented would
otherwise read as a review that found nothing, which is the single most misleading value this
file could hold: it makes the lower tier look free.

`BLOCKED` closes carry **no** `findings` — a blocked worker never got as far as having any.
Its absence there is correct and needs no marker.

## Verification verdicts, the blessed SHA, and attempts

The verification stages leave three kinds of line. They are here rather than only in the
report because **the report is the orchestrator grading its own homework** — the file is the
external record, and a verdict that exists only in a summary cannot be audited against the
run that produced it.

**Every verdict is a `result` on the span that produced it, spelled exactly as
`handoff-verification.md` defines it** — `TAMPER CLEAN`, `TAMPER FAIL: <file>:<line>`,
`TAMPER BLOCKED: <guard>`, `FILEMAP CLEAN`, `FILEMAP FAIL: <paths>`,
`HANDOFF CORRECT: <sha>`, `HANDOFF SALVAGE: <n>`, `HANDOFF DROP: <n>`. Do not paraphrase
them into prose; a later pass over the file classifies on these strings.

**`HANDOFF BLESSED` / `HANDOFF FAIL` are the pre-BILL-535 spellings** and appear in every
`run.jsonl` written before 2026-08-10. A reader over historical files must accept both:
`BLESSED` maps to `CORRECT`, and `FAIL` maps to **neither** of the other two — the old verdict
did not distinguish repairable from unrepairable, so that information is simply absent from
those runs and must not be inferred. Do not rewrite history to the new vocabulary; the file is
append-only and a re-spelled verdict is a claim nobody made.

Worktree lifecycle is recorded on the `branch` note (creation: the worktree path and the fork
SHA) and the `merge` span (removal), so a run's worktrees are reconstructable without the
session. A ticket that stopped records neither removal — see `failure-and-salvage.md`, which
requires the worktree to survive and be locked.

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
| **worker time** | elapsed union of worker spans — merge overlaps, so parallel workers count once |
| **human wait** | `Σ` `waiting_for_user` **spans** — or `unknown`, see below |
| **orchestrator inline** | `wall − worker_time − human_wait` |
| agent-seconds | `Σ` worker spans *unmerged* — *exceeds* worker time under parallelism, like CPU-seconds vs elapsed |
| active time | `wall − human_wait` |

**"Active" is active *elapsed*, not inference time.** Tool execution, model inference and
orchestrator overhead all sit inside it. Splitting those needs transcript-level data, which
this design deliberately does not collect. Say "active", never "compute".

### Report the three-way split, always, as its own line

**Worker time, orchestrator inline time, human wait.** Name all three. A reader must not
have to subtract anything to learn where the run went — and must not have to notice that
the per-stage table does not sum to the wall clock.

```
wall clock              56m28s
  worker time           38m08s   (68%)   — 12 spans, merged
  orchestrator inline   18m20s   (32%)   — see attribution below
  human wait                 0           — no waiting_for_user records of any kind
```

**Orchestrator inline time is the interval between one span closing and the next opening.**
It is the orchestrator reading worker results, deciding, and writing files — real work,
already computable from what is written. It needs no new instruction and gets none: an
instruction to bracket every inline act is both unfollowable and the thing invariant 5 warns
about, because a zero-second span is a stamp written from memory.

**No stage owns this time, which is why it must have its own line.** On PLTF-2565 it was
18m20s — *larger than `implement` and `investigate` combined*. Halve every worker on that run
and a third of the clock still has no name on it.

### All unbracketed time counts. The 120s threshold is a reporting boundary, not a visibility one

Every second between spans belongs to the total, however small the slice. **The threshold
decides which gaps get listed individually, not which gaps get counted.**

| | |
|---|---|
| gaps **over** 120s | listed individually, with bounds and the preceding stage |
| gaps **at or under** 120s | summed into one line — never dropped |
| both | included in the orchestrator inline total |

BILL-494 added gap accounting at a 120s threshold, and a threshold that governs *visibility*
hides exactly the shape a busy run has: dozens of sub-minute slices, each individually
unremarkable, adding to minutes. On SOP-261 that residue is 6m43s across 11 slices. Reporting
zero for it, because no single slice cleared the bar, is an omission that reads as a
measurement.

**Attribute each interval to the stage boundary it follows**, so a reader can tell one long
think from a slow drip:

```
  after close          12m02s   13:15:40 -> 13:27:42
  after investigate     3m23s   12:39:23 -> 12:42:46
  after handoff         1m39s   13:09:41 -> 13:11:20
  under 120s            2m55s   (5 slices, not listed)
```

"12m after close" and "12m spread evenly" are different findings with different remedies.

### Human wait: `unknown` is a distinct answer from `0`, and the difference is load-bearing

Only a `waiting_for_user` **span** measures a human wait. A `waiting_for_user` **note** does
not — it records that a wait happened without bounding it.

| what the file contains | human wait |
|---|---|
| `waiting_for_user` spans | `Σ` of them |
| **notes but no spans** | **`unknown`** — waits happened and none was measured |
| neither, anywhere | `0` — and say *that is why*, not just the number |

**Never report `0` for the middle row.** Notes without spans mean the run blocked on a human
an unknown number of times for an unmeasured duration; calling that zero converts a missing
measurement into a confident wrong answer, and it inflates the orchestrator figure by exactly
the amount nobody measured. SOP-261 is the live case: **13 `waiting_for_user` notes and zero
spans**, over a 3h00m05s run with 1h20m47s unbracketed. Its human wait is `unknown`. It is
emphatically not `0`.

**When human wait is `unknown`, orchestrator inline time is unknown too** — you cannot
subtract a quantity you do not have. Report the pair, and refuse the split rather than
guessing at it:

```
wall clock              3h00m05s
  worker time           1h39m18s   (55%)   — 18 spans, merged
  orchestrator + human  1h20m47s   (45%)   — SPLIT UNKNOWN
                                             13 waiting_for_user notes, 0 spans
```

That report is less satisfying than three numbers and it is the only honest one. A tool that
cannot establish which of two things it is looking at must say so rather than pick the nearer.

**And the bottom row is weaker than it looks.** "No records of any kind → 0" rests on the
absence of a record, which is not the same as the absence of a wait — it is the same
proxy-for-identity mistake one row up, one step further back. State the basis in the report
(*"no `waiting_for_user` records of any kind"*) so the claim can be checked, and treat a large
unbracketed interval sitting where a human decision is known to have happened as a reason to
doubt it rather than a reason to round.

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

   **`(ticket, stage)` is the whole key. `round` is not part of it** — it is a label carried
   for attribution, so a reader can tell three adversary rounds from one lump. Spans that carry
   `round` are sequential by construction: a round closes before the next one opens, so the
   stage alone already pairs them unambiguously and a third key element buys nothing.

   This is a clarification, not a change, and it is written down because the ambiguity cost a
   real run. PLTF-2565 wrote its handoff round-1 `started` without `round` and its close with
   `round: 1`. Paired on `(stage, round)` that file shows one unclosed span and one orphan
   close; paired on `(stage)` — what this invariant has always said — it is clean. The
   orchestrator applied the stricter key, declared its own record invalid, and correctly
   refused to report timing for a run that had merged successfully. The numbers were
   recoverable the entire time.

   **Reporting no numbers is the right response to a broken record. The defect was that the
   record was not broken.** A rule strict enough to reject valid files costs exactly what a
   rule loose enough to accept invalid ones does, and it costs it while looking rigorous.

1b. **`round` appears on both endpoints of a span, or on neither.** A span carrying it on one
   side only is a **split pair** — report it by that name. It is neither an unclosed span nor
   an orphan close, and calling it either sends the reader after the wrong cause: nothing was
   dropped, the two halves were written to disagree. The span still pairs and its duration is
   still valid, so a split pair does **not** suppress timing; it is a defect in the label.
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
7. **Every worker launch has a launch note carrying `worker`, `tier` and `model`.** A `started`
   for a `W`-kind stage with no matching launch note is a **failure**, named as
   *"unattributed launch: `<stage>`"*. A note present but missing one of the three required
   fields is the same failure, named by field. The advisory fields — `effort`,
   `subagent_type`, `subagent_type_used` — are **not** checked here: the hook record owns them,
   and failing a run for their absence would contradict BILL-496 and punish a repo whose hooks
   are doing their job.

   **Scope it to `W` stages.** `intake`, `branch`, `phase0-commit`, `pr`, `bot-read`, `merge`
   and `close` launch nothing; demanding a launch note from them would fail every run forever,
   which is how a check gets disabled rather than fixed.
8. **Every close of a `review`, `adversary` or `handoff` span carries `findings`** — except a
   `BLOCKED` close, which correctly has none. A close missing it is
   *"uninstrumented review primitive: `<stage>` round `<n>`"*.

   **This one fails loudly on purpose.** An unrecorded finding count is indistinguishable from
   a clean review at read time, and it is indistinguishable in the direction that flatters the
   cheaper tier. That is the comparison this whole record exists to make honest, so the check
   is at run end where somebody sees it — not a warning in a log nobody reads.

**Validate at three points, without exception:** on resume, before continuing; at run end,
before reporting anything; and **at every span open**.

### Invariant 1 is checked when a span OPENS, not only at run end

> **ADVISORY, as of BILL-496**, along with the gap accounting below. Both are prose, and prose
> is the thing under test here — see the box further down quoting Anthropic's guidance that a
> prompted rule can fail in a long session. Durations now come from the hook record, which
> needs no cooperation from whoever is writing this file. Keep doing these: when they agree
> with the hooks, that is evidence the prose held; when they do not, that is the measurement.

Before writing any `started` line, check that no span is already open. If one is, the close
you are about to skip is the one that just became due — say so and write it now.

**And the mirror of it: before writing any `finished` or `failed`, check that a matching
`(ticket, stage)` span IS open.** If none is, you skipped the `started` — write it now, at the
time the work actually began, and then write the close. Do not emit the close on its own; that
is an orphan, it fails invariant 2, and under the rule below it costs the whole run's timing
rather than one span's.

**The case this catches is a stage the process runs TWICE ON PURPOSE**, where the second run
reads as a continuation of the first. There are two: `tamper` at stage 8a and again at 10b,
and any 10b re-verification after the blessing is voided. **A second run is a second span** —
open it. Do not reopen or re-close the first.

Measured on SOP-261, which lost its entire 3h00m05s of timing to exactly this:

```
[25] span tamper started  21:39:43
[26] span tamper finished 21:39:59   TAMPER CLEAN; FILEMAP CLEAN — implement commit 6192b78…
[45] span tamper finished 22:08:16   TAMPER CLEAN (re-checked at current tip 3a13583…)  ← no started
```

The same run did it a second time, and there the stage was wrong as well as the pairing: the
pre-merge blessing re-check was written as a `pr` close. It is not a re-run of `pr`. It belongs
to `merge`, recorded in that span's `started` result — which is what PLTF-2565 did correctly,
and why that file pairs clean while this one does not.

**This is the same argument that justifies the open-time check, applied to the other end**, and
it was not applied there for no better reason than that nobody wrote it down. Detection is
cheap and the repair window is short: caught here, the missing `started` is seconds old and
`date -u +%FT%TZ` is still nearly the right answer. Caught at run end, the honest timestamp is
gone, this schema rightly forbids reconstructing one, and the only thing left to do is refuse
to report.

**Timing is the entire point of this check.** PLTF-2563 lost the close on `implement`: the
orchestrator went from the worker's return straight to the next stage. Run-end validation
caught it an hour later, at which point the honest end time was unknowable and this schema
rightly forbids reconstructing one, so the run's own verdict was *"no timing numbers may be
derived from this file."* The same defect caught at the next span open is caught **seconds**
after it happens, while the worker has only just returned and `date -u +%FT%TZ` is still the
correct answer rather than a guess.

Detection is cheap and the repair window is short. Run-end detection has no repair window at
all — it only converts a lost measurement into a reported one.

> **This check is prose, and prose is not a guarantee.** Anthropic's own guidance is explicit
> that a model "can fail to follow a prompted rule" under pressure or **in a long session**,
> and that "a real guardrail needs to be deterministic — the enforcement methods are hooks and
> permissions." PLTF-2563 was a 97-minute run; a long session is the documented failure
> condition, not an unlucky one. So treat this as harm reduction, not enforcement: it narrows
> the window in which the fault is unrecoverable, and it does not close it. The deterministic
> form is a `PostToolUse` hook on `Agent` that appends the close and the launch note in code,
> where no instruction can be skipped.

### Unattributed gap time is named and summed

Report every interval between spans, with its bounds and the preceding stage. **The one
definition of how — including what the 120s threshold does and does not govern, and the
three-way split it feeds — is "Computing time" above**; do not restate it here (universal §5).

The part that belongs to *this* check is when to look: at every span open, not only at run
end. A gap noticed while it is still the current one can still be explained.

A run with zero `waiting_for_user` spans and hours of gaps must say which it is — measured
zero, or unmeasured. This is the third defect PLTF-2563 recorded against itself: human waits
went unbracketed, so idle time sat silently inside the stage durations and "active time" was
not computable while still looking computable. That is the same shape as invariant 5's
zero-second span, an omission that reads as a measurement, and it is why `unknown` is a
reportable value above.

The threshold matters less than the reporting. A stated gap can be investigated; an unstated
one inflates whatever stage happens to precede it.

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

**This rule was already here, in these words, and PLTF-2563 skipped it anyway.** The
orchestrator read the `implement` worker's return and moved to the next stage without writing
the close. Nothing about the instruction was ambiguous, so treat the following as the reason
rather than as an excuse:

> Anthropic's guidance on steering Claude Code states that Claude "will follow the instruction
> most of the time, but when under pressure, **in a long session** or an ambiguous situation …
> the model can fail to follow a prompted rule," and that "a real guardrail needs to be
> deterministic — the enforcement methods are hooks and permissions."

A `:run` is a long session by construction. So the practical rules:

- **Receiving a worker's result and writing its close are one act, not two.** If you have read
  the result and not yet written the line, you are already in the failure. Write it before you
  read the result closely enough to decide what comes next — the decision is what displaces the
  stamp.
- **Never batch stamps.** Four transitions reconstructed at the end of a phase share one second,
  validate cleanly, and have lost the durations the file exists to record.
- **The close is not bookkeeping you owe the file; it is the measurement.** A span with no close
  did not measure a long stage — it measured nothing, and invariant 1 exists because those two
  are indistinguishable afterwards.

**And assume this will fail again.** `run-derived.jsonl` beside this file is written from the
harness's own subagent transcripts by `tools/metrics/derive.py`, which needs no cooperation from
whoever is writing this one. When the two disagree, the derived file is right: it is an
observation, and this file is a claim.

**Take the timestamp from the clock, not from memory.** Every `at` comes from an actual
`date -u +%FT%TZ` at the instant of the transition. Reconstructing several stamps at the
end of a phase is how four transitions end up sharing one second — the file still validates,
still looks complete, and has silently lost the durations it existed to record.

Append with `>>`. Never rewrite, never compact, never delete a line — history is the point,
and both endpoints are needed for every duration.
