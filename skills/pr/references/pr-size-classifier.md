# PR Size Classifier — Signals, Tiers, and the Gated Set

`:pr` classifies every change into one of three tiers — **trivial**, **standard**, or
**large** — and uses that tier to skip **exactly three** expensive gates on the
least-risky changes. This file is the one definition of the classifier: its signals, its
tier table, the gated set, the override flag, the **two distinct skip paths** (tier vs.
resume — they have different preconditions and must not be conflated), and the two
independent applications of sha-gating (C3) that keep a stale classification from silently
skipping work on an unclassified diff.

## Announce before skip (C14)

The classifier **prints one line naming the tier and the signals that produced it
before any gate is skipped.** This is not optional ceremony: a classifier that skips
without announcing is indistinguishable from a broken one. The announcement happens
immediately after classification, ahead of Step 0b, so even a `trivial` run that skips
every gated step still leaves a visible record of what ran the classification and why.

Name both inputs the rules actually use — whether the path rule fired, and the counts:

```
PR size: standard (signals: 42 lines changed across 3 files; all paths on the inert surface)
PR size: large (signals: 8 lines changed across 1 file; hooks/cost-tracker.py is off the inert surface)
```

## Signals and thresholds

Classification is **computed fresh from the branch diff on every invocation** (`git diff
--stat "$(git merge-base "$ORIGIN_REMOTE/$BASE" HEAD)"..HEAD`). It depends on the diff and
nothing else — no `gates.json` entry, no prior run, no config key. A first `:pr` at a sha
nobody has visited classifies exactly as well as a resumed one; see C3 below for why that
sentence has to be said out loud.

One path rule and two count rules decide the tier. **The path rule is evaluated first and
wins outright** — when it says `large`, the counts are not consulted.

### The path rule — an inert-surface whitelist

The **inert surface** is exactly:

- `skills/**`
- `tests/**`
- `design/**`
- `site/**`
- `walkthrough/**`
- root-level `*.md` **except `CLAUDE.md`**

A diff touching **any** file outside that list is **`large`, regardless of counts** —
`hooks/**`, `router/**`, `bin/**`, `tools/**`, `.github/**`, `.claude-plugin/**`,
`.claude/**`, `docs/**`, `baseline/**`, `*.sh`, `.project-conf.toml`, `.mcp.json`, or
anything else.

**This is a whitelist, and the default is `large`.** A top-level path not named above
classifies `large` even when it is in fact inert. That is the intended direction of
failure: a newly added directory fails toward scrutiny, never away from it. Adding a path
to the inert surface is a deliberate edit to this file, not something a new directory
earns by existing.

**`CLAUDE.md` is not inert — it classifies `large`.** No special-case tier rule implements
this: excluding it from the root-`*.md` term is sufficient, and the path rule's
"regardless of counts" clause then applies to it unmodified. A deliberate ruling
(2026-07-31). Its universal block is mirrored byte-identically into five other
repositories (`CLAUDE.md` §10), and the only mechanical guard on that mirror is
`tests/test_structural_invariants.py::TestUniversalRulesMirror`, which runs in **Step 0b's
full suite**. Letting a one-line `CLAUDE.md` edit classify `trivial` would skip Step 0b and
take the mirror guard with it — the exact silent-corruption failure §10's documented trap
describes. `CLAUDE.md` edits are rare, so the throughput cost is ~zero.

**`site/**` and `walkthrough/**` are trivial-eligible by deliberate ruling (2026-07-31),
not by oversight.** Both auto-deploy to the public landing page at
<https://iansmith.github.io/slopstop/> on any push to master touching them
(`.github/workflows/pages.yml`), so a `trivial` edit there ships to the public web having
skipped Step 0b, 2e, and 6. That consequence was raised explicitly and accepted: they are
a docs site, and throughput on landing-page edits was judged worth more than gating them.
Recorded so a later reader does not "fix" it as an accident.

### The count rules

Applied only when the path rule has not already forced `large`:

| Signal | trivial | standard | large |
|---|---|---|---|
| Lines changed (added + removed) | ≤ 20 | 21–300 | > 300 |
| Files changed | ≤ 2 | 3–15 | > 15 |

A change is **trivial** only when **both** signals are within the trivial band. A change
is **large** when **either** signal crosses the large threshold. Everything else is
**standard** — the default when no threshold is decisively crossed.

These thresholds are unchanged from the classifier as originally shipped. A tightening to
150 lines / 8 files was considered and **rejected**; re-proposing it needs its own ticket.

### What this replaced, and why (do not restore it)

An earlier path-pattern override guaranteed that a diff touching `skills/*/SKILL.md` or
`skills/*/references/` was **never classified below `standard`**. **That floor is
deliberately gone.** This repo is almost entirely skill markdown, so the floor made the
classifier a no-op on nearly every PR here — and throughput was the entire point of
having a classifier. A ≤20-line, ≤2-file edit to a `SKILL.md` now classifies `trivial` and
skips Step 0b, 2e, and 6.

The same override's other half — a *ceiling* holding `docs/` and adjacent config at
`standard` — is gone too. `docs/` is gitignored working material with a single tracked
exception (`docs/invite.md`), so it is deliberately left **off** the inert surface and
classifies `large` by the fails-safe default. The inert-surface rule subsumes the rest.

Both removals are intentional. A later reader must not mistake either for drift and
restore it.

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
| `trivial` | **skip** | **skip** | **skip** |
| `standard` | run | skip **only when the diff touches zero test files**, else run | run |
| `large` | run | run | run |

**The `trivial` skips are unconditional** — they need no `gates.json` entry, no prior run,
and no evidence of any kind beyond the tier the classifier just computed. This is the
correction that matters: these three cells used to read *"skip (if sha-matched evidence
exists)"*, which made the skip depend on an entry that only the gate itself writes, after
it runs. On a fresh invocation no such entry exists, so nothing was ever skipped. See C3
below.

`standard`'s Step 2e condition is not a tier rule but a scope one: Step 2e scans **changed
test files** for slop patterns, so a diff that changes no test file gives it nothing to
scan. Step 0b and Step 6 still run at `standard`.

## The override flag

`--pr-tier <standard|large>` forces the classifier's output to **at least** the named
tier. The override can only force a **higher tier** — it can never downgrade
a `standard` or `large` classification to `trivial`, and a `trivial` computation with
`--pr-tier standard` becomes `standard`. This makes a misclassification always
recoverable by the operator: if the automatic signals under-classify a change, `--pr-tier`
is the escape hatch; there is no flag that forces a weaker-review tier
than the signals computed, because that would let an agent disable the gates that police
it.

## Two distinct skip paths — do not conflate them

A gate can be skipped for **two unrelated reasons**, and they have different
preconditions. Conflating them is what broke the classifier originally, so they are named
separately here and everywhere downstream.

- **The tier skip.** The tier the classifier just computed says this gate does not apply
  to this diff (the table above). It reads **no `gates.json` entry at all** — not
  `step_0b`, not `step_2e`, not `step_6`, not `meta`. It cannot be blocked by a missing
  entry, and it cannot be enabled by a present one. This is the skip that delivers the
  classifier's purpose, and it must work on a completely cold invocation with no
  `gates.json` on disk.

- **The resume skip.** `:pr` is being re-run at a sha it already visited, and this gate
  already ran there. This one **does** read a `gates.json` gate entry, and is sha-gated
  per C3 item 1 below. It is an efficiency on repeat invocations only — never the thing
  that makes a tier skip possible.

The failure this separation fixes: the tier skip used to carry the resume skip's
gate-entry precondition. Since a gate entry is written **by the gate itself, after it
runs**, a fresh `:pr` at an unvisited sha never had one — so Step 0b, 2e, and 6 all ran in
full at every tier, on every first run. The only thing that ever got skipped was a
same-sha re-run, which is the resume skip doing its own job.

## C3 sha-gating — applied twice, independently

Both applications below govern reads of **persisted state**. Neither touches the tier
skip, which reads no persisted state at all.

The skip path checks `sha == current HEAD` in **two places**, and the two checks are
**independent of each other** — a stale `meta.tier` forces reclassification even if a
sibling `gates.json` gate entry still matches HEAD, and a stale gate entry is treated
as absent even if `meta.tier` is current. Neither check ever substitutes for the other.

1. **Gate entries — the resume skip only.** Before taking the *resume* skip on Step 0b,
   Step 2e, or Step 6, the classifier reads the matching `gates.json` entry (`step_0b`,
   `step_2e`, `step_6`). The resume skip fires only when **both** hold: that entry's `sha`
   equals the current HEAD sha, **and** its `result` is `"pass"`. A non-matching sha is
   treated as absent — the gate runs. So is a sha-matched `"fail"`: a gate that ran and
   failed at this commit is the one that most needs re-running, so its own entry can never
   license skipping it. (Both bot-review backends record `"fail"` on timeout while `:pr`
   continues, so this is a shape a healthy run actually produces —
   `~/.claude/commands/slopstop-start-refs/gates-json.md` § Degrade-to-run, condition 5.)

   **This precondition belongs to the resume skip and to nothing else.** A tier skip never
   consults these entries, so neither their absence nor their `result` can affect one.

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

**Scope: this governs the resume skip, not the tier skip.** Degrade-to-run is about
failing to *read* persisted evidence, and the tier skip reads none — so there is nothing
for it to degrade. Read unscoped, this rule would say "no `gates.json` → run the gate",
which on a cold invocation is exactly the circular defect above: a first `:pr` has no
`gates.json` by definition, and every tier skip would be cancelled by its absence. A
`trivial` diff skips Step 0b, 2e and 6 **whether or not `gates.json` exists, parses, or is
current.**
