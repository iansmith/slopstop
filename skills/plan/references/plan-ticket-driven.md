# Plan: Ticket-Driven Profile (Profile selection detail)

Runs instead of Steps 0c–2 when `--ticket-driven` was passed or the ticket carries the
five sections of the leaf-ticket standard (`design/ticket-standard.md`). **Steps
0a–0b run first, unchanged** — the test command and the regression baseline are
artifacts Step 3a's commit gates consume; the profile replaces investigation and
plan-drafting, not the safety plumbing. The ticket IS the investigation — Stage 2's
medium tier already did the thinking; this profile is checklist execution, sized for
a small-model implementer.

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
2. **Run them and show them failing** with the Step 0a test command (base-process
   rule: tests must fail on current code). An expectation that passes vacuously
   before implementation is itself a mismatch — halt per TD-4 rather than "fixing"
   the test.
3. Write `task_plan.md`'s sections in the same places default Step 2 would, so
   downstream consumers (`:document`'s DoD assembly, Step 3's dispatch) find them:
   - `## Definition of Done` — verbatim from the ticket's Definition of done.
   - `## Plan` — work items from the behaviors, ordered by the file map, each with
     `Done-when:` (from the DoD) and `Depends-on:` fields; the Out of scope list
     recorded as constraints to honor.
   - `### Parallelism analysis` — normally one line: `serial — ticket-driven profile
     (single leaf-ticket contract)`. Fleet agents are always serial (`--inline`).
   - Append a short `findings.md` entry summarizing the territory as derived from
     the file map (Step 5's fanout briefs read findings.md if parallelism is ever
     chosen).
4. Commit the red tests using Step 0e's exact format — subject
   `[$TICKET] Phase 0: red tests for <summary>`, trailers `Refs: $TICKET` and the
   repo's Co-Authored-By convention.

Skip Step 0f (adversary gap finder) only if `--no-adversary` was passed; otherwise run
it inline (fleet agents always have `--inline` set) at your own tier — it is the cheap
first filter; the orchestrator's handoff adversary is the real net. Note: inline
execution necessarily runs at the effort the agent itself was launched with;
`[fleet.agents].adversary_effort` applies only where a subagent spawn is possible
(see `design/slopstop-process.md` §1).

## TD-4 — The TICKET UNDERSPECIFIED halt

When the ticket's file map, behaviors, or test expectations don't match reality:

1. **Commit nothing.** No implementation, no red tests, no plan content.
2. Post a ticket comment in this exact shape (the orchestrator's failure handling
   parses it alongside the marker):

   ```markdown
   **TICKET UNDERSPECIFIED** — <one-line mismatch summary>
   - Expected (ticket): <the quoted file-map entry / behavior / expectation>
   - Found: <what reality showed, with file:line where applicable>
   ```

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
