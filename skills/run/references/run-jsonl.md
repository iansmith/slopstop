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
the orchestrator stamps it. One writer means no interleaved-append races and no state the
orchestrator does not know about.

## Line shape

One JSON object per line. **Every line carries `at`** — ISO-8601 UTC, `date -u +%FT%TZ`.

```json
{"ticket":"BILL-501","stage":"red-tests","event":"started","at":"2026-08-06T14:02:11Z"}
{"ticket":"BILL-501","stage":"red-tests","event":"finished","at":"2026-08-06T14:07:48Z","result":"4 tests, all red"}
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

Previously wrong: a flatter `event: started|finished|note` shape existed before 2026-08-06. The two-field shape is the spec.

`ticket` is omitted for run-level spans (`:design`/`:tickets`). `stage` is the worker
skill's name for worker spans, or a short verb for orchestrator-inline work.

### The launch note — what a worker was actually given

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
| `model` | what `tier` resolved to, as passed on the `Agent()` call | this note; recoverable from transcript until deleted | **defect** |
| `effort` | the resolved effort — the tier's, or **lower** where a stage requires it | the hook record | advisory |
| `subagent_type` | the carrier requested | this note | advisory |
| `subagent_type_used` | the carrier that actually resolved | the hook record (`agent_type`) | advisory |
| `subagent_model_env` | the value of `CLAUDE_CODE_SUBAGENT_MODEL`, **only when it is set** | this note | see below |

**`tier` has no second source** — it is a slopstop concept the harness has never heard of.
**`model` is absent from all hook payloads** (verified across 413 events). Transcripts are
not durable (PLTF-2563's were deleted at archive for size). So: **`worker`, `tier` and
`model` are required on every launch note** (invariant 7).

`effort`, `subagent_type` and `subagent_type_used` stay advisory — the hook record owns them.

**`subagent_type` and `subagent_type_used` are separate fields on purpose.** A fallback to
`general-purpose` must be visible as a diff, not hidden in a single field.

### `CLAUDE_CODE_SUBAGENT_MODEL` — the one way this record is confidently wrong

That env var **outranks everything slopstop resolves**. If set, the `model` written is what
the orchestrator *asked for*, not what ran.

**Check it at intake and record it.** Write `subagent_model_env` **when and only when set** —
its presence is the alarm. Do not write `null` or `""` to mean unset: a missing value and a
zero value must not read alike.

**One note per launch, never per span.** A `gates` span covers two launches that need not
share a tier; span-level fields cannot express that.

## Which stages are spans, and which are notes

| use a **span** when | use a **note** when |
|---|---|
| a worker is launched | the act is a single atomic command or API call |
| a loop round runs (adversary, review) | the duration is noise and varies with nothing |
| a human is waited on | it is a point-in-time fact (a size, a verdict, a hold) |
| the work's duration varies with its input | |

**The test is whether the duration varies with the input.**

### Why an atomic act must not be a span

`git worktree add` and `git commit` finish instantly. Bracketing one forces either a
zero-second span (invariant 5 flags it) or a close-only line (invariant 2 rejects it).
Both void the run's timing. Use a note.

### A note may fail

A note carries `result` and **a note whose result is a failure stops the ticket** exactly as
a `failed` span would. It just needs no `started` line.

```json
{"ticket":"BILL-501","event":"note","stage":"branch","at":"…","result":"feat/BILL-501 from a1b2c3d"}
{"ticket":"BILL-502","event":"note","stage":"branch","at":"…","result":"failed: branch already exists"}
```

### `stage` comes from the table, never invented

Every `stage` value must be one the writer's own state machine lists. Why: an invented stage
name defeats single-pass reconstruction; see invariant 6.

## Human waits are spans too

Whenever the orchestrator blocks on a human, it brackets that wait:

```json
{"stage":"waiting_for_user","event":"started","at":"...","result":"grill Q7"}
{"stage":"waiting_for_user","event":"finished","at":"...","result":"grill Q7"}
```

Why: wall clock alone is meaningless — one interactive ticket clocked 550.9m wall against
45.5m agent work.

Also write a `session_resume` note on every resume. A session that dies and restarts days
later leaves a gap bracketed by nothing; that note bounds it.

## Record the change size, or the timing answers nothing

**Write the size signal as a `note` once the diff exists** — after `implement`, before the PR:

```json
{"ticket":"BILL-501","event":"note","stage":"size","at":"…",
 "lines_changed":622,"files_changed":33,
 "production_lines":203,"production_files":2,
 "test_lines":419,"test_files":31,
 "test_globs":["*_test.go","**/*_test.*","testdata/**","tests/**","spec/**","__tests__/**"],
 "files":[
   {"path":"linker.go","added":131,"removed":46,"kind":"production"},
   {"path":"weak_def_test.go","added":241,"removed":0,"kind":"test"}
 ],
 "tier":"standard","tier_basis":"production"}
```

### Take the numbers from `--numstat`, per file

```bash
git diff --numstat "$BASE"..HEAD
```

Three tab-separated columns: **added, removed, path**. Do not use `--stat`.

**Record one entry per file, not just aggregates.** Per-file data lets you re-classify a
past run retroactively under different `test_globs`. Why: GAST-8 moved two full tier bands
depending on whether `testdata/**` counted as test material.

`kind` is `production` or `test`, decided by `test_globs`. Aggregates must equal the sum of
per-file entries.

Two `--numstat` edge cases:

- **Binary files** give `-` for added/removed. Count in `files_changed`, contribute **0** to
  line counts.
- **Renames** appear as `old => new`. Record as written; do not split.

### Split production from tests, or the label is wrong every time

**`production_*` and `test_*` must be recorded separately.** Why: slopstop deliberately
produces far more test than implementation, so a classifier fed totals calls everything
`large`.

**`lines_changed` is added + removed, not net.**

**`test_globs` records the classification rule** in the note itself. A path matching no
test glob is production. When a language's convention is missing, add it and say so.

### The tier is a label on data, not a decision

Compute from **whatever the ticket's mode makes the deliverable**, put which in `tier_basis`.
Then **record it. Nothing reads it. Nothing skips.**

| mode | count | `tier_basis` |
|---|---|---|
| `normal` | production | `"production"` |
| `refactor` | production | `"production"` |
| `backfill` | **test** | `"test"` — production is frozen; test is the deliverable |

| | trivial | standard | large |
|---|---|---|---|
| lines changed | ≤ 20 | 21–300 | > 300 |
| files changed | ≤ 2 | 3–15 | > 15 |

`trivial` needs **both** bands; `large` needs **either** threshold crossed; everything else
is `standard`.

**Backfill uses test counts** — production changes are forbidden in backfill, so
`production_lines` is definitionally 0 and a production basis would score every backfill
`trivial`.

**`tier` is one of `trivial` / `standard` / `large` and nothing else.** No qualifier, no
sentence, no fourth value. `medium` belongs to the model-tier ladder; the two vocabularies
share words and are not the same thing. Reasoning goes in `result`.

**Record `production_lines`, `production_files`, `test_lines` and `test_files` as top-level
integers**, not nested or implied by re-adding per-file entries.

`derive.py --check` validates all of the above.

**These thresholds are a hypothesis, not a specification.** Recording the label next to real
durations is what will confirm or move them. Changing what is counted and changing where the
boundaries sit are two experiments; run them separately.

## One span per round — never one span per loop

Stage 7 `adversary` (cap 3), stage 9 `mutation-check` (cap 3), stage 10 `review` (cap 5)
and stage 10b `handoff` all run each round as a separate worker launch. **Bracket each
launch**: `started` when launched, `finished`/`failed` when its verdict returns, carrying
round number and verdict.

`round` goes on **both** endpoints — see invariant 1b. It is a label, not part of the
pairing key.

```json
{"ticket":"BILL-501","stage":"adversary","event":"span","state":"started","at":"…","round":2}
{"ticket":"BILL-501","stage":"adversary","event":"span","state":"finished","at":"…","round":2,"result":"FAIL: 3"}
```

Do **not** wrap one span around the whole loop. Why: GAST-8 recorded 1050s as a single lump
for 3 adversary rounds, making per-round cost invisible.

A round that is capped, escalated, or human-authorized past the cap is still its own span.

## What a review primitive found — a field, not a sentence

**Every close of a `review`, `adversary` or `handoff` span carries a `findings` object.**

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

**Severity and class are `adversary`'s vocabulary** — `blocker`/`major`/`minor` and
`behavioural`/`presentational`, defined in `skills/adversary/SKILL.md`. No second set of
names. `red`/`yellow`/`gray` is a rendering choice; neither is `slop-check`'s two-level gate
vocabulary. Never write either into this record.

**Copy numbers from the worker's verdict line; never re-derive from prose.**

**`applied` and `reported` are different findings and neither is the total.** Declining to
edit a frozen Phase 0 file is correct and must not read as a fix never made.

**Refuted and unconfirmed findings are in neither triple.** A wrong premise is not a defect.

### An absent `findings` and an all-zero `findings` are different facts

- **`findings` present, all zeros** — the worker ran and found nothing. A real measurement.
- **`findings` absent** — nothing was recorded. Says nothing about the code.

**Never write all-zero to stand in for missing**, and never default absent to zero.
`BLOCKED` closes carry **no** `findings` — correct, no marker needed.

### The artifact note

Written only when `[workflow].publish_artifacts` is `true` (default `false`). It is a
**note**, not a span.

```json
{"event":"note","ticket":"BILL-501","stage":"review","at":"…","artifact":{"kind":"review-basis","url":"https://claude.ai/public/artifacts/…"}}
{"event":"note","stage":"design","at":"…","artifact":{"kind":"prd","url":"https://claude.ai/public/artifacts/…"}}
```

- **`artifact.kind`** — `review-basis` | `prd` | `charter`. Distinguishes two artifacts at
  one stage.
- **`artifact.url`** — the deployed page.
- **`ticket`** follows the ordinary rule — present for `:run`, omitted for `:design` run-level
  work. Do not invent a placeholder.

**The URL is written before it is used.** Artifacts accumulate rounds and redeploy to the
same URL; a URL held only in context is lost on compaction. Reading it back: scan for the
last matching note on `(ticket, stage, artifact.kind)`. **Never rewrite or delete a
superseded note** — the file is append-only.

**When publication is unavailable and the key is `true`,** no note is written. The document
goes to the tracking dir and the run report names the path and says publication was
unavailable.

## Verification verdicts, the blessed SHA, and attempts

**Every verdict is a `result` spelled exactly as `handoff-verification.md` defines it** —
`TAMPER CLEAN`, `TAMPER FAIL: <file>:<line>`, `TAMPER BLOCKED: <guard>`, `FILEMAP CLEAN`,
`FILEMAP FAIL: <paths>`, `HANDOFF CORRECT: <sha>`, `HANDOFF SALVAGE: <n>`,
`HANDOFF DROP: <n>`. Do not paraphrase; later passes classify on these strings.

**`HANDOFF BLESSED` / `HANDOFF FAIL` are pre-BILL-535 spellings** in files before 2026-08-10.
A reader must accept both: `BLESSED` maps to `CORRECT`; old `FAIL` did not distinguish
repairable from unrepairable — do not infer. Do not rewrite history.

Worktree lifecycle: recorded on `branch` note (creation) and `merge` span (removal). A
stopped ticket records neither removal (per `failure-and-salvage.md`).

```json
{"ticket":"BILL-501","event":"span","stage":"tamper","state":"failed","at":"…","result":"TAMPER FAIL: tests/test_codec.py:41"}
```

**The blessing is a `note` carrying the SHA it binds to:**

```json
{"ticket":"BILL-501","event":"note","stage":"handoff","at":"…",
 "verdict":"BLESSED","blessed_sha":"3f9a1c…"}
```

Re-checked at merge. When tip has advanced past `blessed_sha`, write a fresh `handoff` span
— both blessings are the record.

**Attempts are counted from the file, not from memory.** An attempt is one `implement` or
`handoff` span that closed `failed`. Record the diagnosis at the second failure as a `note`
— `ticket-defect`, `capability-gap`, or `undiagnosed`.

**A preserved stop gets its own `note`** naming branch, both SHAs, worktree path, and
commit count. Per `failure-and-salvage.md`.

## A hold is a note, not a span

A held ticket has **not run** — no span. Record a `note` when held and when released:

```json
{"ticket":"BILL-502","event":"note","stage":"held","at":"…",
 "blocked_by":["BILL-501"],"unsatisfied":["BILL-501"],"reason":"not merged"}
{"ticket":"BILL-502","event":"note","stage":"released","at":"…","after":"BILL-501"}
```

The ticket's first real span opens **after** the release note. A held ticket contributes
nothing to agent-seconds and is not `waiting_for_user`. A ticket held at run end has a
`held` note and no spans — a complete, well-formed record, **not** an unclosed span.

## Computing time

**Do not compute by hand. Run the tool:**

```bash
python3 <slopstop>/tools/metrics/derive.py "$TICKET" --repo "$REPO_ROOT" --check
```

Two files, two jobs. **Worker spans come from `run-derived.jsonl`; only wall clock and human
wait come from `run.jsonl`.**

| quantity | source | computation |
|---|---|---|
| wall clock | `run.jsonl` | `last.at - first.at` |
| **worker time** | **`run-derived.jsonl`** | elapsed union of worker spans — merge overlaps |
| **human wait** | `run.jsonl` | `Sigma` `waiting_for_user` **spans** — or `unknown` |
| **orchestrator inline** | both | `wall - worker_time - human_wait` |
| agent-seconds | **`run-derived.jsonl`** | `Sigma` worker spans *unmerged* — exceeds worker time under parallelism |
| active time | `run.jsonl` | `wall - human_wait` |

### `run.jsonl` stage spans are not worker spans

A `run.jsonl` span records that a **stage was open** — it swallows sub-workers, orchestrator
thinking, and any human wait while open. The `wall - worker - human` subtraction assumes
disjoint slices; stage spans do not guarantee that. Why: AATK-86's `implement` round 2
stayed open across a `waiting_for_user` span and four sub-worker launches, making the
stage-span split go negative. The derived file's worker spans resolved it cleanly.

**A nested span is not a broken record.** It passes all invariants. Do not report it as
corrupt — derive the split from `run-derived.jsonl`.

### Why this is not "never nest a span"

A flat-span rule is a prompted rule, and prompted rules fail in long sessions (Anthropic's
guidance). Keep the discipline as advice but point the arithmetic at the deterministic
`run-derived.jsonl`.

### When `run-derived.jsonl` is absent

Fall back to `run.jsonl` stage spans and **say so**:

```
  worker time         4h31m20s   (94%)   — from run.jsonl STAGE spans; no run-derived.jsonl
                                           stage spans include sub-workers and any wait they
                                           enclose, so this is an upper bound
```

If the fallback produces a negative inline figure, report worker time and wall clock, name
the wrapping stage, and report inline as `unknown`.

**"Active" is active *elapsed*, not inference time.** Tool execution, model inference and
orchestrator overhead all sit inside it. Say "active", never "compute".

### Report the three-way split, always, as its own line

**Worker time, orchestrator inline time, human wait.** Name all three.

**The per-stage table does not have to reconcile with the split.** Stage durations come from
`run.jsonl`, worker time from `run-derived.jsonl`, and a wrapping stage inflates its own
row. Print both and let them disagree.

```
wall clock              56m28s
  worker time           38m08s   (68%)   — 12 spans, merged
  orchestrator inline   18m20s   (32%)   — see attribution below
  human wait                 0           — no waiting_for_user records of any kind
```

**Orchestrator inline time is the interval between one span closing and the next opening.**
It needs no new instruction.

### All unbracketed time counts

Every second between spans belongs to the total. **The 120s threshold decides which gaps get
listed individually, not which gaps get counted.**

| | |
|---|---|
| gaps **over** 120s | listed individually, with bounds and the preceding stage |
| gaps **at or under** 120s | summed into one line — never dropped |
| both | included in the orchestrator inline total |

**Attribute each interval to the stage boundary it follows:**

```
  after close          12m02s   13:15:40 -> 13:27:42
  after investigate     3m23s   12:39:23 -> 12:42:46
  under 120s            2m55s   (5 slices, not listed)
```

### Human wait: `unknown` is distinct from `0`

Only a `waiting_for_user` **span** measures a human wait.

| what the file contains | human wait |
|---|---|
| `waiting_for_user` spans | `Sigma` of them |
| **notes but no spans** | **`unknown`** — waits happened, none was measured |
| neither, anywhere | `0` — and say *that is why*; treat a large unbracketed interval where a human decision is known to have happened as reason to doubt it |

**Never report `0` for the middle row.** Notes without spans mean unmeasured waits; calling
that zero inflates the orchestrator figure by the unmeasured amount.

**When human wait is `unknown`, orchestrator inline is unknown too:**

```
wall clock              3h00m05s
  worker time           1h39m18s   (55%)   — 18 spans, merged
  orchestrator + human  1h20m47s   (45%)   — SPLIT UNKNOWN
                                             13 waiting_for_user notes, 0 spans
```

**Report unattributed time. Never redistribute it.**

## Validation — how an incomplete record announces itself

**The invariants:**

1. Every `started` is closed by exactly one `finished` or `failed` with the same
   `(ticket, stage)`. **Spans only.**

   **`(ticket, stage)` is the whole key. `round` is not part of it** — spans carrying
   `round` are sequential by construction, so stage alone pairs them unambiguously.

   **Reporting no numbers is the right response to a broken record.**

1b. **`round` appears on both endpoints of a span, or on neither.** A span with it on one
   side is a **split pair** — report by that name. The span still pairs and its duration is
   valid; it is a defect in the label, not in the timing.

2. No `finished`/`failed` without a preceding `started` for that `(ticket, stage)`.
   **Spans only.** Notes cannot be orphan closes by construction.

3. Every line parses as JSON and carries `at`.

4. A completed run's last line is `{"event":"note","stage":"run_closed",...}`. Absence means
   the orchestrator died mid-run — legitimate state, not corruption, but **not** a finished run.

5. **A non-`waiting_for_user` span of 0 seconds is reported as suspect.** Not an error, but
   almost certainly a stamp written from memory. Report suspect spans by name alongside timing.

6. Every `stage` value appears in the writer's own state-machine table. An unrecognised
   value is a failure — name it and the nearest legal value.

7. **Every worker launch has a launch note carrying `worker`, `tier` and `model`.** A `started`
   for a `W`-kind stage with no matching note is *"unattributed launch: `<stage>`"*. Scope to
   `W` stages only — `intake`, `branch`, `phase0-commit`, `pr`, `bot-read`, `merge` and `close`
   launch nothing.

8. **Every close of a `review`, `adversary` or `handoff` span carries `findings`** — except
   `BLOCKED` closes. A close missing it is *"uninstrumented review primitive: `<stage>` round
   `<n>`"*. This fails loudly on purpose: an unrecorded finding count reads as a clean review,
   flattering the cheaper tier.

**Validate at three points:** on resume, at run end, and **at every span open**.

### Invariant 1 is checked when a span OPENS, not only at run end

> **ADVISORY, as of BILL-496.** Durations now come from the hook record. Keep doing these:
> agreement with hooks is evidence the prose held; disagreement is the measurement.

Before writing any `started`, check no span is already open. If one is, the close just became
due — write it now. Mirror: before any `finished`/`failed`, check a matching span IS open;
if not, write the `started` at the time work began, then the close. Do not emit an orphan.

**Catches stages run twice on purpose** — `tamper` at 8a and 10b, and any 10b
re-verification after the blessing is voided. A second run is a second span; do not reopen
the first.

> **This check is prose, not a guarantee.** A `:run` is a long session, the documented
> failure condition for prompted rules. The deterministic form is a `PostToolUse` hook on
> `Agent` that writes the close in code.

### Unattributed gap time is named and summed

Defined in "Computing time" above (universal SS5 — not restated here). The part belonging to
this check: look at every span open, not only at run end.

**When validation fails, report no timing numbers at all.** Name what broke by invariant —
**unclosed spans** (1), **orphan closes** (2), **unknown stages** (6). Then stop. A broken
record must not produce a plausible-looking summary.

## Writing discipline

The `started` line is written **as part of the same step that launches the work**, and the
`finished` line **as part of the same step that receives the result** — never as a separate
thing to remember afterwards.

> A `:run` is a long session by construction. Anthropic's guidance: a model "can fail to
> follow a prompted rule" in a long session. So the practical rules:

- **Receiving a worker's result and writing its close are one act.** Write before you read
  the result closely enough to decide what comes next.
- **Never batch stamps.** Four transitions reconstructed at the end share one second,
  validate cleanly, and have lost the durations.
- **The close is the measurement**, not bookkeeping.

**`run-derived.jsonl`** beside this file is written from harness subagent transcripts by
`derive.py`. When the two disagree, the derived file is right.

**Take the timestamp from the clock, not from memory.** Every `at` comes from `date -u +%FT%TZ`
at the instant of the transition.

Append with `>>`. Never rewrite, never compact, never delete a line.
