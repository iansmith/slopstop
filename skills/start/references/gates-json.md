# Gate evidence: `gates.json` — the one definition

`$TRACKING_DIR/$TICKET/gates.json`, the durable record of every gate `:pr` has run for the
current ticket. It lives under `start/references/` for the same reason
`tracking-dir-resolution.md` does: `:start` owns the tracking dir's lifecycle, and every
skill that writes or reads gate evidence points here instead of restating the schema.

**This file is evidence, not control flow.** `:pr` writes an entry after each gate it runs,
and **nothing in it may cause a gate to be skipped** — that is the invariant, stated
precisely in the C4 section below, and Steps 2d and 2f are permanently excluded from any
future skip path.

Gates do read the `meta` baseline keys: Step 2d and `:run`'s tamper check resolve the frozen
set from `meta.red_sha`/`meta.frozen` rather than grepping commit subjects, and Step 2f
resolves `meta.stubs` to rebuild the Phase 0 sentinel. Those reads recover facts the writer
recorded about a historical commit; they change how thoroughly a gate can run, never
*whether* it runs. Earlier revisions of this paragraph said Steps 2d and 2f gain "no read
path" at all, which stopped being true when the baseline keys were introduced. The
distinction that carries the safety property is skip-versus-inform, not read-versus-write.

## Schema

```json
{
  "step_0b": {"sha": "<40-hex head sha>", "result": "pass", "at": "<ISO-8601 Z>", "detail": "<filename>"},
  "step_0c": {"sha": "<40-hex head sha>", "result": "pass", "at": "<ISO-8601 Z>", "detail": "<filename>"},
  "step_2":  {"sha": "<40-hex head sha>", "result": "fail", "at": "<ISO-8601 Z>", "detail": "<filename>"},
  "step_2d": {"sha": "<40-hex head sha>", "result": "pass", "at": "<ISO-8601 Z>", "detail": "<filename>"},
  "step_2e": {"sha": "<40-hex head sha>", "result": "pass", "at": "<ISO-8601 Z>"},
  "step_2f": {"sha": "<40-hex head sha>", "result": "pass", "at": "<ISO-8601 Z>", "detail": "<filename>"},
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

- **`sha`** — the 40-character hex HEAD sha at the moment the gate ran. See "Stale entries"
  below for how a reader uses it.
- **`result`** — `"pass"` or `"fail"`.
- **`at`** — ISO-8601 UTC timestamp with a literal `Z` suffix, the moment the gate produced
  its result.
- **`detail`** — **optional**, present only when the gate produced an output file worth
  pointing at (a report, a log). **Omitted** entirely when no such file exists — a reader
  must never treat a missing `detail` as an error; it is the normal, expected shape for a
  gate with nothing to attach. `#354` populates this field for `step_0b`, `step_2`,
  `step_2d`, and `step_2f`, which now redirect their full output to a tracking-dir file
  and record its name here — `step_2e` and `step_6`'s CodeRabbit/Greptile backends still
  omit it, since they are out of scope for that redirect.

### Gate keys — at least these seven

`step_0b`, `step_0c`, `step_2`, `step_2d`, `step_2e`, `step_2f`, `step_6`. This set is a
floor, not a ceiling: a reader must check for **containment**, never an exact key set —
future tickets are expected to add keys (e.g. per-backend Step 6 variants) without this
reference needing to renegotiate the schema each time.

**`step_0b` and `step_0c` are always separate keys — never conflated into one.**
`:pr`'s Step 0 has three sub-steps: `0a` resolves the test command (produces no gate
result, nothing to write), `0b` runs the full suite and classifies failures, `0c` runs the
cyclomatic-complexity gate. Only `0b` is ever tier-gated (a `trivial` tier — computed from
the branch diff, never from config; C9 forbids a config key here — skips the full-suite
run); **`step_0c` is never tier-gateable** and must always run and
record its own entry independently of whatever `step_0b` did. Collapsing them into one key
would let a future consumer skip `0c` merely as a side effect of skipping `0b` — the two
gates measure unrelated things (test health vs. code complexity) and must never share a
fate.

### The reserved `meta` key

`meta` is a **single reserved, non-gate, top-level key** — an object holding cross-gate
state that later tooling needs to persist alongside gate evidence (for example, a
classified execution tier). It exists so that future tickets have an open-ended place to
add state without violating a schema this reference pins closed.

**Every `meta` sub-key carries its own `sha`, shape `{"value": <any>, "sha": "<40-hex head
sha>"}`, and is subject to the identical staleness rule as a gate entry** — see "Stale
entries" below. This is not "ignored when its sibling gate entries are stale" — that
question has no single answer (which siblings? what if the seven gate entries disagree with
each other?). Each `meta` sub-key's own `sha` field is the only test of its own validity,
independent of every other key in the file.

**Three reserved `meta` keys carry the Phase 0 baseline**, written by `:plan` Step 0e:

- **`meta.red_sha`** — the sha of the Phase 0 red-test commit.
- **`meta.frozen`** — the list of **test file paths** Step 0e staged, and nothing else.
- **`meta.stubs`** — the list of **stub file paths** Step 0e staged in that same commit,
  and nothing else. `[]` when the ticket needed no stub, written explicitly so a reader
  can tell "no stubs" from "not recorded" — the two call for different behavior in
  Step 2f, and an absent key must never be read as an empty list.

`frozen` and `stubs` are **disjoint by construction** and stay separately named: `frozen`
is what the tamper gates may not let change, `stubs` is ordinary production surface the
implementer is expected to replace. Recording them separately is what lets a stub share
the red-test commit without becoming frozen.

The tamper gates and Step 2f read these instead of re-discovering them. That matters for
three reasons. Grepping commit subjects for `Phase 0: red tests` is an unanchored
substring match that can select the wrong commit; deriving the frozen set from the
commit's file list makes *everything* in that commit frozen, which is why stubs used to
need a commit of their own; and deriving the stub set as "the non-test files in that
commit" would sweep in anything that rode along, which is the same hole from the other
side. Step 0e knows exactly what it staged — recording it removes all three. A reader
that finds none of these keys falls back to the old derivation, so an old `gates.json`
still works.

Worked example of the baseline block, for transcription:

```json
{
  "meta": {
    "red_sha": {"value": "4f2aaa3f0e02261e215ec5b4ac75aa3ba094cddf", "sha": "4f2aaa3f0e02261e215ec5b4ac75aa3ba094cddf"},
    "frozen":  {"value": ["tests/test_bill999_behaviors.py"], "sha": "4f2aaa3f0e02261e215ec5b4ac75aa3ba094cddf"},
    "stubs":   {"value": ["internal/vacuity/collector.go"], "sha": "4f2aaa3f0e02261e215ec5b4ac75aa3ba094cddf"}
  }
}
```

Unlike other `meta` sub-keys these three are **not** sha-gated against current HEAD: they
describe a fixed historical commit, so they stay valid as the branch advances. They
carry `{"value": ..., "sha": "<the red-test commit sha>"}` where `sha` is that commit,
not HEAD.

**Concrete consumer:** `:pr`'s size classifier persists its result as `meta.tier`
(`{"value": "trivial"|"standard"|"large", "sha": "<40-hex head sha>"}`) so a resumed
session doesn't reclassify a diff it already looked at. This is a plain instance of the
shape above, not a schema extension — see
`~/.claude/commands/slopstop-pr-refs/pr-size-classifier.md`.

## Read rules

### Stale entries — sha is the whole staleness test, never time

A reader compares an entry's `sha` field against the current HEAD sha. **Equal → current.**
**Not equal → stale, and a stale entry is ignored** exactly as if it were absent — the gate
it describes must be treated as not-yet-run. This applies identically to gate entries and to
`meta` sub-keys.

**Current is not the same as passing.** Sha decides whether an entry describes *this* commit;
whether a current entry licenses **skipping** the gate's re-run is a separate question, and
`result` answers it — see Degrade-to-run below. Reading this section as "sha is the whole
test" for skips is what once let a gate that ran and **failed** at the current sha license
skipping its own re-run.

There is no time-based invalidation. An entry from ten minutes ago on the current commit is just
as valid as one from ten seconds ago; an entry from the current commit's *previous* sha is
invalid regardless of how recently it was written. Do not add, or read this file as
implying, any age-based invalidation — sha equality is the only signal.

### Degrade-to-run — never assume pass

**Five conditions** degrade to exactly one outcome — **run the gate**:

1. a missing `gates.json`;
2. a stale entry (sha mismatch);
3. an unparseable file (invalid JSON);
4. a partially-written file (e.g. truncated mid-write);
5. **a current-sha entry whose `result` is `"fail"`.**

None may ever be read as "the gate passed" — a reader that cannot establish a valid,
current-sha, **passing** entry for a gate must treat that gate as not-yet-run and execute it.
Assuming pass on a bad read would let a corrupted or missing file silently skip real
verification; degrading to "run it" costs time, never correctness.

**The fifth is the only one you will meet on a healthy run.** The other four are corruption
or absence; a sha-matched `"fail"` is what a normal, working pipeline produces. Skipping on
it is precisely backwards — a gate that ran and failed at this exact commit is the one that
most needs re-running. The live path: `pr-cr-polling.md` and `pr-greptile-polling.md` both
record `"fail"` on **timeout**, while `pr/SKILL.md` treats a bot-review timeout as non-fatal
and continues. A timed-out review therefore leaves a sha-matched `"fail"` on `step_6` of a PR
that is otherwise proceeding.

So a **skip requires `sha == HEAD` AND `result == "pass"`.** Both, always.

**This governs skips that read an entry — never a skip that reads nothing.** The rule is
about failing to read persisted evidence, so it has no purchase on a decision taken without
consulting this file at all. `:pr`'s size classifier is the live example: its **tier** skip
is computed from the branch diff and reads no entry, while its **resume** skip reads one and
is governed here (`~/.claude/commands/slopstop-pr-refs/pr-size-classifier.md`). Applied
unscoped, this rule would read as "no `gates.json` → run every gate", which cancels every
tier skip on a first invocation — a cold `:pr` has no `gates.json` by definition. That was a
real defect, fixed in BILL-361; do not reintroduce it by generalizing this paragraph.

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
