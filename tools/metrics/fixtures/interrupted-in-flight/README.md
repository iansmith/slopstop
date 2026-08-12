# Fixture: a run interrupted with a worker in flight (BILL-582)

This reproduces the case that made `derive.py --check`'s launch cross-check misleading, and
that **no surviving run still reproduces** — closing AATK-81 out properly is what fixed it.

## What it is

Three launches from AATK-81's real run, with `run.jsonl` **truncated at the archive launch
note**, which is where the interrupt actually landed. Three run.jsonl variants share one set of
transcripts and differ only in where a `run_closed` line sits:

| variant | `run_closed` | `--check` says |
|---|---|---|
| `tracking/` | none | interrupted in flight — the launch **ran** |
| `tracking-phantom/` | last line | a claim with no record behind it |
| `tracking-resumed/` | mid-file, after `review` | interrupted in flight — closure is about the LAST line (invariant 4) |

That is the whole discrimination the check makes, isolated to the placement of one line. Before
BILL-582 all three printed `launch notes in run.jsonl: 3; launches the harness recorded: 2`.

`tracking-resumed/` exists because `run_closed` appearing *anywhere* is not closure: the close
stage is re-enterable on resume (see the idempotence note in `derive.py`), so a run that was
closed, resumed and then interrupted carries one mid-file. Reading that as closed suppressed
the in-flight diagnosis on exactly the run that needed it.

## Run it

```bash
python3 tools/metrics/derive.py AATK-81 \
  --tracking tools/metrics/fixtures/interrupted-in-flight/tracking \
  --transcripts tools/metrics/fixtures/interrupted-in-flight/transcripts --check
```

Swap `tracking` for either other variant. `--check` writes nothing, which is what keeps the
fixture re-runnable in place.

## The dropped-launch cases — asserted, not just demonstrated

```bash
python3 tools/metrics/fixtures/interrupted-in-flight/check-dropped-cases.py
```

`attribute()` drops launches the harness recorded but could not place on any ticket, because
they precede the first label carrying a ticket key. That makes this ticket's launch count a
**range**, and three review rounds in a row found a branch of `launch_note_check` ignoring it —
the third one printing *"the two records agree"* over an unaccounted launch. **None of the nine
real runs reaches these branches**: every one has `dropped == 0` where it would matter, which is
why a nine-run sweep passed each time. This script is the only thing that stops the next change
regressing them.

It builds all three branches from the committed files — varying only how many launch notes
survive — and **asserts the verdict** rather than printing it:

| notes vs attributed launches | branch | must report |
|---|---|---|
| 1 vs 2 | shortfall + dropped | `tier` unrecoverable for **1–2**, not a flat 1 |
| 2 vs 2 | equal counts + dropped | **undecidable** — not agreement |
| 3 vs 2 | excess covered by dropped | **undecidable** — not a phantom claim |

Built rather than committed because the trigger is one label in the *session* transcript:
variants would duplicate every subagent file three times to change one string. Every mutation
it makes is asserted on both sides, so fixture drift **aborts** — the script it replaced could
silently run a different case and report it as this one.

## The unclosed-span cases

```bash
python3 tools/metrics/fixtures/interrupted-in-flight/check-unclosed-spans.py
```

`harness says it ended unknown` was one word for three situations (BILL-586), and on the
`tracking/` variant it contradicted the launch diagnosis two lines below it — the same `archive`
worker reported as ending `unknown` and as running `11:20:44 -> 11:24:35`. **Two of the five
states below occur in no archived run at all**, and only two runs have an unclosed span:

| span stage | state | must report |
|---|---|---|
| `pr` | on `run-jsonl.md:708`'s no-launch list | launches no worker — **absent, not missing** |
| `review` | worker ran, inside the window | its real end time (wording unchanged) |
| `archive` | worker ran, outside the window | its real end time **and** why it is outside |
| `salvage` | no label contains it | **not found** — never "did not run" |
| `aatk` | matches three labels | **AMBIGUOUS** — refuses to pick one |

`aatk` is synthetic: no slopstop stage is named that, and it is the only string here matching
more than one label. The rule it pins is not synthetic — `pr` is two characters, which is why
the no-launch list is consulted *before* any label is matched.

`--transcripts` exists because the default root is `~/.claude/projects/<slug of --repo>` and
that slug is an absolute path — it changes with the checkout, so it cannot be committed.

## Why the numbers are what they are

`window()` spans run.jsonl's first `at` to its last, so here it ends at `11:20:30Z`. The
archive worker started at `11:20:44.527Z` — **14 seconds later**, and outside. In a healthy run
that is impossible: `run_closed` is written after the worker returns, so the window covers it.
It is specific to an interruption, and widening the window is not the fix (see `attribute()`'s
docstring for the regression that produced).

## Provenance, and what was stripped

Derived once from AATK-81's archived run in `~/sophie/aatoolkit` and its session transcript
`89a00856-79b4-4d75-b28e-64a487f69f4e`. The generator is not committed because it cannot be
re-run: it reads `~/.claude/projects`, and transcripts are deleted for size — which is the same
reason `derive.py`'s header says to derive early.

Kept verbatim: timestamps, `agentId`, `model`, `effort`, and every `usage` block, so per-launch
bounds and compute are the run's real numbers. Stripped: all message content, worker prompts,
and the `result`/`findings` prose on the run.jsonl spans — none of it is read by the deriver,
and it is another repo's working material.

`tracking-phantom/`'s `run_closed` line is **synthetic** — it is the one thing here that no run
produced. It is stamped at the same `at` as the line before it deliberately: a later stamp would
widen the window over the archive worker and the file would simply agree.
