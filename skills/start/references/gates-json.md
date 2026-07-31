# Gate evidence: `gates.json` — the one definition

`$TRACKING_DIR/$TICKET/gates.json`, the durable record of every gate `:pr` has run for the
current ticket. It lives under `start/references/` for the same reason
`tracking-dir-resolution.md` does: `:start` owns the tracking dir's lifecycle, and every
skill that writes or reads gate evidence points here instead of restating the schema.

**This file is evidence, not control flow.** It records what happened; nothing here changes
what `:pr` decides. As of this ticket, `gates.json` has exactly one writer path (`:pr`
writes an entry after each gate it runs) and no reader that changes any gate's verdict.
Steps 2d and 2f in particular gain **no** read path — see the C4 section below.

## Schema

```json
{
  "step_0b": {"sha": "<40-hex head sha>", "result": "pass", "at": "<ISO-8601 Z>"},
  "step_0c": {"sha": "<40-hex head sha>", "result": "pass", "at": "<ISO-8601 Z>", "detail": "<filename>"},
  "step_2":  {"sha": "<40-hex head sha>", "result": "fail", "at": "<ISO-8601 Z>"},
  "step_2d": {"sha": "<40-hex head sha>", "result": "pass", "at": "<ISO-8601 Z>"},
  "step_2e": {"sha": "<40-hex head sha>", "result": "pass", "at": "<ISO-8601 Z>"},
  "step_2f": {"sha": "<40-hex head sha>", "result": "pass", "at": "<ISO-8601 Z>"},
  "step_6":  {"sha": "<40-hex head sha>", "result": "pass", "at": "<ISO-8601 Z>", "detail": "<filename>"},
  "meta": {
    "<key>": {"value": "<any>", "sha": "<40-hex head sha>"}
  }
}
```

Every entry (gate or `meta` sub-key) carries exactly four fields for gates — `sha`,
`result`, `at`, and the optional `detail` — and every `meta` sub-key carries exactly two —
`value` and `sha`. No other top-level keys exist besides the seven gate keys below and the
single reserved `meta` object.

### Field definitions

- **`sha`** — the 40-character hex HEAD sha at the moment the gate ran. The entire validity
  test (see "Stale entries" below) — there is no other freshness signal.
- **`result`** — `"pass"` or `"fail"`.
- **`at`** — ISO-8601 UTC timestamp with a literal `Z` suffix, the moment the gate produced
  its result.
- **`detail`** — **optional**, present only when the gate produced an output file worth
  pointing at (a report, a log). **Omitted** entirely when no such file exists — a reader
  must never treat a missing `detail` as an error; it is the normal, expected shape for a
  gate with nothing to attach. (`#354` is what starts populating this field in practice;
  between this ticket and `#354`, every entry legitimately omits it.)

### Gate keys — at least these seven

`step_0b`, `step_0c`, `step_2`, `step_2d`, `step_2e`, `step_2f`, `step_6`. This set is a
floor, not a ceiling: a reader must check for **containment**, never an exact key set —
future tickets are expected to add keys (e.g. per-backend Step 6 variants) without this
reference needing to renegotiate the schema each time.

**`step_0b` and `step_0c` are always separate keys — never conflated into one.**
`:pr`'s Step 0 has three sub-steps: `0a` resolves the test command (produces no gate
result, nothing to write), `0b` runs the full suite and classifies failures, `0c` runs the
cyclomatic-complexity gate. Only `0b` is ever tier-gated (a cheaper tier may skip the
full-suite run under config); **`step_0c` is never tier-gateable** and must always run and
record its own entry independently of whatever `step_0b` did. Collapsing them into one key
would let a future consumer skip `0c` merely as a side effect of skipping `0b` — the two
gates measure unrelated things (test health vs. code complexity) and must never share a
fate.

### The reserved `meta` key

`meta` is a **single reserved, non-gate, top-level key** — an object holding cross-gate
state that later tooling needs to persist alongside gate evidence (for example, a
classified execution tier). It exists so that future tickets have an open-ended place to
add state without violating a schema this reference pins closed.

**Every `meta` sub-key carries its own `sha` and is ignored under the same rule as gate
entries** — a sub-key whose sha does not match current HEAD is stale and must be ignored,
exactly as a stale gate entry is. The shape is `{"value": <any>, "sha": "<40-hex head
sha>"}` per sub-key. This is not "ignored when its sibling gate entries are stale" — that
question has no single answer (which siblings? what if the seven gate entries disagree with
each other?) and is not what the sha check means. Each `meta` sub-key's own `sha` field is
the only test of its own validity, independent of every other key in the file.

## Read rules

### Stale entries — sha is the whole test, never time

A reader compares an entry's `sha` field against the current HEAD sha. **Equal → valid.**
**Not equal → stale, and a stale entry is ignored** exactly as if it were absent — the gate
it describes must be treated as not-yet-run. This applies identically to gate entries and to
`meta` sub-keys.

There is no time-based invalidation. An entry from ten minutes ago on the current commit is just
as valid as one from ten seconds ago; an entry from the current commit's *previous* sha is
invalid regardless of how recently it was written. Do not add, or read this file as
implying, any age-based invalidation — sha equality is the only signal.

### Degrade-to-run — never assume pass

A missing `gates.json`, a stale entry (sha mismatch), an unparseable file (invalid JSON), or
a partially-written file (e.g. truncated mid-write) all degrade to exactly one outcome:
**run the gate.** None of these conditions may ever be read as "the gate passed" — a reader
that cannot establish a valid, current-sha entry for a gate must treat that gate as
not-yet-run and execute it. Assuming pass on a bad read would let a corrupted or missing
file silently skip real verification; degrading to "run it" costs time, never correctness.

### Steps 2d and 2f gain no read path (C4)

**Steps 2d (red-test tamper gate) and 2f (vacuity gate) never read `gates.json` for a skip
decision, and no future change to either step may introduce one via this file's schema.**
Both are cheap, mechanical, unconditional gates (`git log` / `git diff`, no test suite
dependency) that run on every path reaching their point in `:pr`, including a clean working
tree — and both exist specifically to police an agent that might otherwise look clean. A
`gates.json` hit that let either step skip would let the exact party the gate polices
short-circuit its own policing by presenting a stale-but-matching entry. This ticket only
makes gate evidence durable; nothing in this schema or these read rules authorizes any gate
— mechanical or otherwise — to skip on a `gates.json` hit. A future ticket may add a skip
path for other gates; Steps 2d and 2f are permanently excluded from it.

## Write rules

- **Unconditional.** `:pr` writes an entry after each gate it runs (Steps 0b, 0c, 2, 2d,
  2e, 2f, 6) — no config key, no enable flag gates this. There is no `[gates]` table and no
  `gates_json` path override anywhere in `.project-conf.toml` or
  `.project-conf.toml.example`.
- **Merge, never clobber.** A write updates only the entry for the gate that just ran;
  every other key already present in the file — other gates' entries, `meta` sub-keys —
  is preserved untouched. A new entry never drops entries for other gates.
- **Narrative content stays in `task_plan.md` / `findings.md` / `progress.md`.** This file
  holds structured gate evidence only; it is not a place to migrate the prose those three
  files already carry.
