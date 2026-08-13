# Fixture: one session, three orchestrations of one ticket (BILL-599)

Reproduces the deriver emitting **one row per launch request instead of one per subagent run**,
which doubled every token and agent-hour total in the derived file while leaving that file
perfectly well-formed.

Observed live on `aatoolkit` AATK-87: one harness session held attempt 1, a `--rewrite`, then
attempt 2. `derive()` emitted 14 rows for 7 real runs — 440,182 output tokens where the truth
was 220,091 — with attempt 1's runs absent entirely and attempt 2's counted twice, once under
their own label and once under a label belonging to an earlier orchestration.

## What it is

One session transcript with **7 launches** against **6 subagent transcripts**, and a
`run.jsonl` whose window covers only the last orchestration:

| launch | requested | in window? | its run |
|---|---|---|---|
| `investigate AATK-99` | 08:34 | no | `a1111…`, 08:34 |
| `red-tests AATK-99` | 08:44 | no | `a2222…`, 08:44 |
| `scope-subtraction delta check AATK-99 V2` | 09:55 | no | `a3333…`, 09:55 (**opus**) |
| `investigate AATK-99 V2` | 10:55 | yes | `a4444…`, 10:55 |
| `red-tests AATK-99 V2 new DoD items` | 11:03 | yes | `a5555…`, 11:03 |
| `implement AATK-99` | 11:58 | yes | `a6666…`, 11:58 |
| `close AATK-99` | 12:41 | yes | **none** — sync launch, no agentId, no child |

The window from `tracking/run.jsonl` is `10:54:48 .. 12:42:07`. Every launch carries its real
`agentId`, and every run starts 1.5–2.6 s after the launch that owns it, so the correct pairing
is unambiguous from the data.

## The three shapes it discriminates

1. **Three rows, correctly labelled.** Only the runs inside the window, each under the launch
   that actually made it.
2. **Out-of-window launches are scoped out silently.** They belong to a different
   orchestration. They must produce no row *and* no complaint — announcing them would bury the
   one case that matters under a wall of noise on any session driving several tickets.
3. **An in-window launch matching nothing is reported.** `close AATK-99` is in scope, so its
   missing run is a fact about the record, not noise.

The `opus` delta-check is deliberate. Before the fix it stole `a6666…`, a sonnet run, and was
written out as `claude-sonnet-5` — so the fixture pins model fidelity, not just row count. A
model column that lies is worse than one that is absent.

## Run it

```bash
python3 tools/metrics/fixtures/two-orchestrations/check-doubling.py
```

Exits non-zero on any assertion. Copies the fixture to a temp dir and writes only there.

Against the pre-BILL-599 deriver it fails **9** ways; the count matters less than the spread —
row count, `agent_id` uniqueness, three stolen labels, the unreported drop, and three
out-of-window launches producing rows. Any one of those alone would have been fixable in a way
that left the others.

## Why the count assertion is not enough on its own

Adding only the missing `used` check to the exact-id path yields **the right number of rows
with every one mislabelled** — attempt 1's labels attached to attempt 2's runs, totals correct,
attribution entirely wrong. That passes a row-count sanity check and reads clean. A file that
is wrong *and* looks right is worse than one that is visibly doubled, which is why
`check-doubling.py` asserts labels and models per `agent_id` rather than counting.
