# The slopstop workflow — a feature, end to end

> **This is the whole process.** As of v4.0.0 there is no separate "single-ticket loop" and no
> separate "fleet" — the same three commands cover one ticket and twenty. The chain of
> user-invoked stages (`:start` → `:plan` → `:pr` → `:merge`) is gone, and so is the headless
> `claude -p` fleet mechanism that used to sit beside it.

slopstop is a Claude Code plugin for **autonomous agents that write code without slop**. You
hand it work and it drives that work to merged, keeping the anti-slop guarantees the whole way:
tests written before implementation, scope fixed before code, and a set of checks that a
motivated agent cannot argue its way past.

Three commands. Eleven workers they launch. One launch mechanism for all of it.

---

## The three orchestrators

```
   /slopstop:design <topic>
            │   grill the human to shared understanding, classify every decision
            │   against the spec, write prd.md + charter.md into scratch/runs/<run-id>/
            │   ── gate G-design ──
            ▼
   /slopstop:tickets <run-id>
            │   cut the umbrella/leaf ticket tree from the PRD, five sections per leaf,
            │   drive an adversary over the DRAFT (≤3 rounds) — the ticket system never
            │   sees an unapproved tree — then create it
            │   ── gate G-tickets ──
            ▼
   /slopstop:run <TICKET> [TICKET...]
            │   the entire implementation lifecycle for 1..N tickets, interleaved:
            │   investigate → red tests → adversary → implement → gates → review
            │   → PR → merge → close → archive, per ticket
            ▼
          merged
```

`:design` and `:tickets` are for work that starts as an idea. If you already have tickets, start
at `:run` — it takes a bare list of keys and needs no run-id.

Three side modes on `:tickets`:

- **`--retrofit <TICKET>`** — bring one hand-written ticket up to the five-section standard,
  including its Definition of Done, before `:run` is allowed near it.
- **`--rewrite <TICKET>`** — re-author a ticket that failed implementation twice, citing the
  specific failure. A mandatory `scope-subtraction` check runs before the ticket system sees
  anything: if the rewrite quietly shrank the DoD until the existing code would satisfy it,
  that is rejected and the scope restored.
- **`--refactor <fn> [<fn>…]`** — cut a ticket whose DoD is *nothing broke*, from the
  function names `complexity-check` printed under its exempt heading. Its guard is the whole
  existing suite: green before, the same green after, no test file modified. This is what
  keeps a behaviour-preserving refactor out of a feature branch.

---

## What `:run` does, per ticket

Fifteen stages. **W** = a worker launched as an agent; **I** = the orchestrator's own inline work.

| # | stage | | what happens |
|---|---|---|---|
| 1 | `intake` | I | fetch the ticket, its five sections and its Definition of Done; seed the tracking dir; open `run.jsonl` |
| 2 | `investigate` | W | read-only map of the codebase for this ticket, plus a **predicted file map** |
| 3 | `branch` | I | ticket → in progress; cut `<type>/<TICKET>` from the integration branch |
| 4 | `red-tests` | W | write the failing tests for what the *ticket* requires — not for what the code does |
| 5 | `mutation-check` | W | prove each test is red for the **right reason**, not an import error or a typo |
| 6 | `phase0-commit` | I | commit the red tests and stubs. This commit is the frozen baseline |
| 7 | `adversary` | W+I | attack the test suite for gaps; gap tests are added, re-verified red, and committed |
| 8 | `implement` | W | make the tests pass. It may not touch the tests |
| 9 | `gates` | W×3 | `slop-check`, `vacuity-check`, `complexity-check` — launched together |
| 10 | `review` | W | clean-context review of the diff, looping until clean, capped at 5 rounds |
| 10a | `size` | I | record lines/files changed and a provisional tier — recorded only, nothing reads it yet |
| 11 | `pr` | I | commit, push, open the PR |
| 12 | `bot-read` | I | read whatever bot review already exists, **once**. Never poll for one |
| 13 | `merge` | I | real merge commit, branch deleted. Serial across tickets |
| 14 | `close` | I | score the DoD, advance the ticket to its terminal state, write the confirmation |
| 15 | `archive` | W+I | push the tracking files back onto the ticket, then move the dir to the archive |

The one legitimate short path: a prose-only change reports `PHASE 0: none`, and stages 5–7 are
skipped — explicitly, and every downstream consumer is told the frozen baseline is absent rather
than handed a guess.

### Gates 9 and 10 in one line each

- **`slop-check`** — reads the diff for tests rewritten to pass, inverted expectations,
  tautological assertions, swallowed errors, and scope creep.
- **`vacuity-check`** — re-runs each new test against the code that predates the branch. A test
  that was already green pins nothing, however well it is named.
- **`complexity-check`** — measures cyclomatic complexity of every changed function against the
  project's configured thresholds. Purely mechanical.
- **`review`** — a fresh, clean-context reader that verifies each finding against the real code
  and applies what survives. The session that wrote the code never reviews it.

`vacuity-check` runs *after* implementation on purpose. The stage-7 adversary cannot see tests
written later; this is what covers them.

---

## Driving N tickets at once

`:run` takes a list, and drives the list. The concurrency comes out of stage 2:

1. **Fan out `investigate` for every ticket first.** It is read-only, so it is always safe to run
   in parallel, and it is what produces each ticket's predicted file map.
2. **Schedule by overlap.** Tickets whose predicted file maps are disjoint run their lifecycles
   concurrently. Overlapping ones run serially, later ones starting from the updated tip.
   Prediction is never perfect — this buys efficiency, not correctness, which is why step 3 does
   not depend on it.
3. **Merge serially, always**, whatever the overlap said. One PR at a time. On conflict:
   `git merge master` into the losing branch, resolve, re-run that ticket's tests, push, merge.
   **Never rebase** — a rebase of a pushed branch needs a force push.

One ticket, one branch, one PR. Never two tickets on a branch; never a branch cut from another
ticket's branch.

---

## Properties that matter

**`:run` is autonomous by default.** There is one switch — `--interactive` — and it stops at
every judgment gate to ask. Without it, `:run` decides and keeps going, because driving N tickets
unattended is the thing it exists for. There is no `[autonomous]` block and no per-gate
`on_*` config; those seven knobs were deleted, because one orchestrator has one decision point.

**Mechanical gates never soften — in any mode, at any change size.** A *judgment* gate can be
waved past by a human who has read it. Red-test tamper, vacuity, and slop findings cannot, and
have no permissive setting to find. This is not strictness for its own sake: any knob whose
permissive value is the only one an unattended run can use has silently disabled that gate for
exactly the agents it exists to police. A gate that waves through for those cases is worse than
no gate at all, because it reports clean.

**A failing gate stops that ticket, not the run.** Its span in `run.jsonl` closes `failed`, its
branch and tracking directory are preserved exactly as they were, and every other ticket keeps
going. The stopped set is reported together at the end, with what each one needs. A stalled
autonomous run is the failure mode the default exists to avoid.

**Never resolve a stop by weakening what raised it.** No deleted test, no narrowed assertion, no
`Skip()`, no edited frozen expectation. If the *ticket's* own expectation is wrong, that is a
goal defect for a human — and a ticket that fails implementation twice is more likely a ticket
defect than a code defect, which is what `:tickets --rewrite` is for.

**Every step is recorded.** Each orchestrator appends its stage transitions to an append-only
`run.jsonl` — for `:run`, one file per ticket, living in that ticket's tracking dir and travelling
with it into the archive. That single file is three things at once: the state machine, the resume
point after a long run gets compacted, and the timing record. There is no second artifact and no
derivation step.

**Human waits are bracketed.** Whenever an orchestrator blocks on a person it writes a
`waiting_for_user` span — opened in the step that asks, closed in the step that reads the answer.
The orchestrator is the thing doing the blocking, so it is the only thing that can record it.
This is what separates machine-active time from a human who walked away for a weekend, and it is
deliberate groundwork: skipping stages on small changes is the next feature, and it is blocked
until the timing is trustworthy. That is also why stage 10a records the change size next to the
durations and nothing reads it yet.

**An incomplete record refuses to produce numbers.** `run.jsonl` is validated on resume and again
at run end — every `started` closed exactly once, every line parsing, every line timestamped. On
failure the unclosed spans are named and **no timing at all** is reported. A broken record must
not be able to emit a plausible-looking summary.

**Per-ticket isolation.** Each ticket owns its tracking directory — task plan, findings,
`run.jsonl` — so a session working `MAZ-26` loads `MAZ-26`'s notes and nothing else, and parallel
work in different repos never collides.

**A durable record goes back to the ticket.** At stage 15 the tracking files are pushed onto the
ticket as comments, so the ticket ends up a record of what was actually done rather than a title
and a merged diff.

---

## Where the contracts live

The skills are the specification; these documents describe them.

- **`skills/run/SKILL.md`** — the fifteen stages and the mode table, in full.
- **`skills/run/references/worker-launch.md`** — the single launch form, stage → tier → model
  resolution, and the eleven-worker roster with each worker's arguments and return.
- **`skills/run/references/run-jsonl.md`** — the timing/state file: line shape, sole-writer rule,
  human-wait bracketing, validation invariants.
- **`skills/design/SKILL.md`**, **`skills/tickets/SKILL.md`** — stages 1 and 2.
- **[CONFIG.md](CONFIG.md)** — every setting in `.project-conf.toml`.
- **[walkthrough/](walkthrough/)** — one real multi-agent run, read minute by minute.
