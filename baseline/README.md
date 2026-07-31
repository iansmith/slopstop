# baseline/

Frozen **before** dataset for the cost-tracker Stop hook (BILL-351), preserved so the
Tier 1 25–30% cost-reduction claim (D8, C16) is falsifiable against a fixed before/after
comparison rather than a moving target.

## Contents

- `sessions.json` — the frozen before-baseline per-session rollup (847 K), produced by
  `analyze.py` walking `~/.claude/projects/**/*.jsonl`.
- `analyze.py` — parses `~/.claude/projects/**/*.jsonl` into `sessions.json`.
- `report.py` — global figures, model split, theory 1–4 tables, read from `sessions.json`.
- `deep.py` — baseline, growth curve, tool_result volume, wall-clock analysis.
- `cost-time-audit-2026-07-30.md` — the sha-anchored audit spec/write-up. Moved byte-for-byte;
  **never edit this file** — its integrity is pinned by the sha256 below, which the PRD cites
  as its traceability anchor.

## Capture date

2026-07-30.

## Spec integrity

```
sha256(cost-time-audit-2026-07-30.md) = 722373b0dc8a8ca3293dcb1d77f454c93fc02864d3d40be49eb214b51a46ffa4
```

Verify with `shasum -a 256 baseline/cost-time-audit-2026-07-30.md`.

## Historical paths inside the spec — do not "fix"

`cost-time-audit-2026-07-30.md` was written when these scripts lived at
`scratch/cost-audit-2026-07-30/`, and its own text still says so: the summary line near the
top references `scratch/cost-audit-2026-07-30/`, and its "Reproducing" section says
"Scripts in `scratch/cost-audit-2026-07-30/`" with `cd scratch/cost-audit-2026-07-30`. That
directory no longer exists after this move — the scripts now live directly in `baseline/`.

The spec file is **not** edited to correct this, because the sha256 above is a byte-exact
integrity check and any edit breaks it. Treat every `scratch/cost-audit-2026-07-30/` path
inside the spec as historical, and read it as `baseline/` instead. The same applies to the
originating PRD's header line, `SPEC: scratch/cost-time-audit-2026-07-30.md` — that PRD
predates this move too and is not amended here.

## Regenerating the *after* measurement

Run the same three scripts from `baseline/` (not the old `scratch/` path) against a fresh
session pull, to compare against this frozen before-baseline:

```bash
cd baseline
python3 analyze.py sessions.json   # WARNING: overwrites sessions.json in place — copy the
                                    # frozen file aside first if you want to diff before/after
python3 report.py                  # global figures, model split, theory 1/2/3/4 tables
python3 deep.py                    # baseline, growth curve, tool_result volume, wall clock
```

`analyze.py` walks every `*.jsonl` under `~/.claude/projects`, so re-running it captures
whatever sessions have landed there since 2026-07-30 — that is the point: the *after*
measurement is captured the same way, against the same tree, so the two are comparable.
`report.py` reads `sessions.json` from the current directory by default, or from
`SESSIONS=/path/to.json` if set — point it at a copy of the *after* rollup to compare against
this frozen *before* one.
