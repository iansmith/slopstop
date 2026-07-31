# PR Size Classifier — Signals, Tiers, and the Gated Set

`:pr` classifies every change into one of three tiers — **trivial**, **standard**, or
**large** — and uses that tier to skip **exactly three** expensive gates on the
least-risky changes. This file is the one definition of the classifier: its signals, its tier
table, the gated set, the override flag, and the two independent applications of
sha-gating (C3) that keep a stale classification from silently skipping work on an
unclassified diff.

## Announce before skip (C14)

The classifier **prints one line naming the tier and the signals that produced it
before any gate is skipped.** This is not optional ceremony: a classifier that skips
without announcing is indistinguishable from a broken one. The announcement happens
immediately after classification, ahead of Step 0b, so even a `trivial` run that skips
every gated step still leaves a visible record of what ran the classification and why.

```
PR size: standard (signals: 42 lines changed across 3 files; no path-pattern match for trivial/large)
```

## Signals and thresholds

Two signals drive classification, read from the branch diff (`git diff --stat
"$(git merge-base "$ORIGIN_REMOTE/$BASE" HEAD)"..HEAD`):

| Signal | trivial | standard | large |
|---|---|---|---|
| Lines changed (added + removed) | ≤ 20 | 21–300 | > 300 |
| Files changed | ≤ 2 | 3–15 | > 15 |

A change is **trivial** only when **both** signals are within the trivial band. A
change is **large** when **either** signal crosses the large threshold. Everything
else is **standard** — the default when no threshold is decisively crossed.

**Path-pattern override, independent of line/file counts:** a diff touching only
`docs/`, `*.md` outside `skills/`, or `.gitignore`-adjacent config files never counts
above `standard`, even past the line/file thresholds — but a diff touching any file
under `skills/*/SKILL.md` or `skills/*/references/` is never classified below
`standard`, regardless of the line/file counts — process-defining prose earns at
least the default level of scrutiny.

## The gated set — exactly three things (C13)

The tier gates **exactly Step 0b's full-suite run, Step 2e (slop agent), and Step 6
(code review)**. Nothing else. In particular, Step 0c (the cyclomatic-complexity gate)
is **never tier-gated** — it is a separate `gates.json` key from Step 0b precisely so
that skipping the full suite can never skip the CC gate as a side effect. Step 1
(simplify), Step 2's targeted test run, Step 2d (red-test tamper), and Step 2f
(vacuity) all run at **every tier, without exception** — no flag and no tier ever
skips them (C4, universal §1's "No exceptions on size").

| Tier | Step 0b (full suite) | Step 2e (slop agent) | Step 6 (review) |
|---|---|---|---|
| `trivial` | skip (if sha-matched evidence exists) | skip (if sha-matched evidence exists) | skip (if sha-matched evidence exists) |
| `standard` | run | run | run |
| `large` | run | run | run |

## The override flag

`--pr-tier <standard|large>` forces the classifier's output to **at least** the named
tier. The override can only force a **higher tier** — it can never downgrade
a `standard` or `large` classification to `trivial`, and a `trivial` computation with
`--pr-tier standard` becomes `standard`. This makes a misclassification always
recoverable by the operator: if the automatic signals under-classify a change, `--pr-tier`
is the escape hatch; there is no flag that forces a weaker-review tier
than the signals computed, because that would let an agent disable the gates that police
it.

## C3 sha-gating — applied twice, independently

The skip path checks `sha == current HEAD` in **two places**, and the two checks are
**independent of each other** — a stale `meta.tier` forces reclassification even if a
sibling `gates.json` gate entry still matches HEAD, and a stale gate entry is treated
as absent even if `meta.tier` is current. Neither check ever substitutes for the other.

1. **Gate entries.** Before skipping Step 0b, Step 2e, or Step 6, the classifier reads
   the matching `gates.json` entry (`step_0b`, `step_2e`, `step_6`). The skip path fires
   only when that entry's `sha` field equals the current HEAD sha. A non-matching sha is
   treated as absent — the gate runs.
2. **The persisted tier itself.** The classified tier is stored in `gates.json`'s
   reserved `meta` object as `meta.tier`. Reading a previously persisted tier is also
   gated on sha: a `meta.tier` whose `sha` does not match current HEAD is stale, and a
   stale tier means **reclassify, never reuse**. Reusing a tier across a sha it was
   never computed for would skip Step 0b/2e/6 on a diff the classifier never actually
   looked at — exactly the C2/C3 violation the sha rule exists to prevent.

There is no time-based invalidation for either check — sha equality is the only
signal, with no age-based fallback.

## `meta.tier` persistence

The classifier writes its result into `gates.json`'s reserved `meta` object (schema:
`~/.claude/commands/slopstop-start-refs/gates-json.md`), using the same generic
`{"value": <any>, "sha": "<40-hex head sha>"}` shape every `meta` sub-key already
carries:

```json
"meta": {
  "tier": {"value": "standard", "sha": "<40-hex head sha>"}
}
```

The tier is **never** an additional top-level `gates.json` key — it does not sit
alongside `step_0b`/`step_2e`/etc. as its own sibling entry — and **never** persisted
as a bare string value. Always the `{"value": ..., "sha": ...}` object, exactly like every
other `meta` sub-key.

## C2 — `gates.json` decides skips, never verdicts

The classifier reads `gates.json` **only to decide whether a gate can be skipped** —
never to decide whether a gate passed or failed. A missing `gates.json`, a stale entry
(sha mismatch), an unparseable file, or a partially-written file all degrade to exactly
one outcome: **run the gate.** None of these conditions is ever read as "the gate
passed" — a classifier that cannot establish a valid, current-sha entry must treat the
corresponding gate as not-yet-run and execute it. Missing/unparseable/corrupt
`gates.json` is not evidence of anything; it is only ever a reason to run the gate
directly, never a reason to skip.
