# Plan: Ticket-Driven Profile (Profile selection detail)

Runs instead of Steps 0–2 when `--ticket-driven` was passed or the ticket carries the
five sections of the leaf-ticket standard (`design/ticket-standard.md`). The ticket IS
the investigation — Stage 2's medium tier already did the thinking; this profile is
checklist execution, sized for a small-model implementer.

## TD-1 — Parse the five sections

From `task_plan.md`'s original-description snapshot, extract: Observable behaviors,
File map, Definition of done, Out of scope, Test expectations. Any section missing or
empty → this is not a conforming ticket: if `--ticket-driven` was explicitly passed,
halt per TD-4 (the ticket claims a contract it doesn't carry); if auto-detected,
fall back to the default Steps 0–2.

## TD-2 — Verify the territory

The **file map is the territory — no free investigation.** For each file-map entry,
confirm it exists (or is an explicitly new path) and skim only what the map names.
Directory-granular entries (e.g. `tests/`) cover their subtree.

If reality contradicts the map or the behaviors — a named file doesn't exist, the
described seam isn't where the ticket says, a behavior is impossible as specified —
do NOT explore your way around it. That's a Stage-2 defect: halt per TD-4.

## TD-3 — Red tests transcribed, then the plan

1. **Transcribe** the ticket's **Test expectations** into red tests: each named
   expectation becomes test code pinning the observable behavior it describes. Do not
   invent test intent beyond the ticket — transcription, not authorship.
2. **Run them and show them failing** (base-process rule: tests must fail on current
   code). An expectation that passes vacuously before implementation is itself a
   mismatch — halt per TD-4 rather than "fixing" the test.
3. Write the `## Plan` section of `task_plan.md`: the DoD comes verbatim from the
   ticket's Definition of done; work items come from the behaviors, ordered by the
   file map. Record the Out of scope list as constraints to honor.
4. Commit the red tests (`[$TICKET] Phase 0 red tests`, `Refs: $TICKET`).

Skip Step 0f (adversary gap finder) only if `--no-adversary` was passed; otherwise run
it inline (fleet agents always have `--inline` set) at your own tier — it is the cheap
first filter; the orchestrator's handoff adversary is the real net.

## TD-4 — The TICKET UNDERSPECIFIED halt

When the ticket's file map, behaviors, or test expectations don't match reality:

1. **Commit nothing.** No implementation, no red tests, no plan content.
2. Post a ticket comment naming the **specific** mismatch — the file-map entry, quoted
   behavior, or expectation that failed, and what was actually found (file:line where
   applicable).
3. Stop, with this exact final line (the orchestrator greps for it):

   ```
   TICKET UNDERSPECIFIED: <one-line mismatch summary>
   ```

This halt is not a failure of yours: it routes the ticket back to a Stage-2-style
rewrite **without consuming any implementation attempts** — bad tickets are Stage 2
defects, not Stage 3 failures (`design/slopstop-process.md` §7a/§7e). Never improvise
past a wrong ticket; the fix belongs in the ticket, not the worktree.

## What the profile does NOT change

- Steps 3+ of the spine (serial/parallel decision, agent fanout, monitoring) resume
  as normal once the plan is written — though fleet agents' `--inline` forces serial.
- All base-process rules bind: commit anchoring, no force-push, tests before pauses.
- `:pr`, `:update`, `:start` behavior is untouched by this profile.
