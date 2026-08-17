# User output — what `:run` prints and when

## The rule

**Default to quiet.** The only text output the user sees during a run is:

1. One **phase line** at the start of each stage (see format below).
2. **Gate stops** — when a gate halts the run, the finding that caused it.
3. **Errors** — when something fails and the ticket stops or the run aborts.
4. **The final report** — the per-ticket summary table at the end of the run.

Everything else — worker launch details, intermediate findings, config
resolution, scheduling decisions, internal reasoning — is silent. It still
goes into `run.jsonl`; it does not go to the user.

**`--verbose` restores full output.** When the flag is present, print
freely — stage details, worker briefs, finding text, scheduling rationale,
whatever is useful. The quiet default exists because most runs are
unattended; `--verbose` is for when someone is watching and wants to see
the machinery.

Set `$VERBOSE` from the flag at the top, alongside `$MODE`.

## Phase lines

At the **start** of each stage, emit exactly one line in this format:

```
[ Stage N: <one-sentence description of what this stage does for this ticket> ]
```

Rules:
- `N` is the stage number from the state machine table (1–15).
- The description is **specific to the ticket and stage**, not a generic
  label. Name the ticket, name what is being checked or built.
- One line. Two short sentences at most. No blank lines before or after.
- No phase line for sub-stages (8a, 10a, 10b) — they are part of their
  parent stage's work.

Examples:

```
[ Stage 1: Reading BILL-412 and parsing its DoD ]
[ Stage 2: Investigating the codebase for BILL-412's file map ]
[ Stage 4: Writing failing tests for BILL-412 ]
[ Stage 7: Adversary round 1 for BILL-412 ]
[ Stage 8: Implementing BILL-412 ]
[ Stage 9: Running slop-check, vacuity-check, and complexity-check for BILL-412 ]
[ Stage 10: Review round 1 for BILL-412 ]
[ Stage 11: Opening PR for BILL-412 ]
[ Stage 13: Merging BILL-412 ]
[ Stage 14: Scoring DoD and closing BILL-412 ]
[ Stage 15: Archiving BILL-412 ]
```

For stages that loop (7, 9's mutation-check, 10, 10b), emit a new phase
line at the start of each round, with the round number.

## What quiet does NOT suppress

- Gate findings that stop the run — the user must see why it stopped.
- Errors and ticket-stop reasons — same.
- The consult prompt in `--interactive` mode — obviously.
- The final summary — ticket, outcome, PR URL, elapsed time.

## What --verbose adds

Everything the orchestrator would normally think or log:
- Worker launch parameters and tier resolution.
- Scheduling decisions (which tickets run next and why).
- Config resolution trace.
- Intermediate worker results and finding text.
- Adversary round details.
- Review round details.
- Timing breakdowns per stage.
