# Fixture: a run interrupted with a worker in flight (BILL-582)

This reproduces the case that made `derive.py --check`'s launch cross-check misleading, and
that **no surviving run still reproduces** — closing AATK-81 out properly is what fixed it.

## What it is

Three launches from AATK-81's real run, with `run.jsonl` **truncated at the archive launch
note**, which is where the interrupt actually landed. Two run.jsonl variants share one set of
transcripts and differ by exactly one line:

| variant | last line | `--check` says |
|---|---|---|
| `tracking/` | the `archive` launch note, no `run_closed` | interrupted in flight — the launch **ran** |
| `tracking-phantom/` | the same, plus a `run_closed` at the same `at` | a claim with no record behind it |

That is the whole discrimination the check makes, isolated to one line of input. Before
BILL-582 both printed `launch notes in run.jsonl: 3; launches the harness recorded: 2`.

## Run it

```bash
python3 tools/metrics/derive.py AATK-81 \
  --tracking tools/metrics/fixtures/interrupted-in-flight/tracking \
  --transcripts tools/metrics/fixtures/interrupted-in-flight/transcripts --check
```

Swap `tracking` for `tracking-phantom` for the other variant. `--check` writes nothing, which
is what keeps the fixture re-runnable in place.

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
