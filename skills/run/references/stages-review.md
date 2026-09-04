# Stages 10-12 — review, handoff, bot-read

Read when the orchestrator enters stage 10 for a ticket.

## Stage 10 — review

```
$ROUND = 1
loop:
  Agent(... prompt: invoke slopstop:review with
        "--scope <PR-or-ref-range> --mode $MODE --frozen $FROZEN")

  # Branch on the LEADING TOKEN: everything from REVIEW up to the first `|`.

  REVIEW CLEAN         -> converged. Advance to stage 10b immediately.
                          Do not launch another round — the code is clean.
  REVIEW APPLIED: <n>  -> inspect the `class` field of the findings object.
                          If `behavioural == 0` (all findings presentational):
                            commit and push, then advance to stage 10b.
                            Do not launch another round — prose/naming fixes
                            cannot break behaviour.
                          Otherwise: commit and push this round's fixes, then continue.
  REVIEW BLOCKED: <r>  -> stop this ticket, surface <r>, do not retry
  anything else        -> stop, surface the raw verdict verbatim; never assume it applied

  if $ROUND >= 5       -> capped: re-derive over the findings still STANDING (below)
  $ROUND += 1
```

**At the cap, decide on the residue — the same rule as stage 7:**

- any standing `blocker`/`major` that is `behavioural` -> **stop the ticket**, human, findings quoted
- all standing findings `presentational` -> apply and advance — same as the presentational exit above
- nothing standing -> advance to stage 11

**`REVIEW BLOCKED` and `anything else` are unaffected** — they are not verdicts about findings.

**You assign no severity here either** (stage 7's rule, one definition): quote the worker's, record only disposition.

**Branch on the token, record the whole line.** `review` returns lines with `|`-separated sections; split on the first `|` and match the left side. A bare `REVIEW CLEAN` without counts is a valid older-format verdict.

**Put the verdict line verbatim into the span's `result`:**

```json
{"ticket":"BILL-544","event":"span","stage":"review","state":"finished","round":1,
 "result":"REVIEW CLEAN | reported 3 (blocker 0, major 1, minor 2)"}
```

**Transcribe the same numbers into a `findings` object** — schema in `run-jsonl.md`. Copy from the verdict line; never re-derive. `result` stays beside `findings` so the transcription is auditable. **An absent `findings` and an all-zero one are different facts.**

**A `REVIEW CLEAN` carrying a reported `blocker` is a contract violation, not a pass.** Take the `anything else` exit.

**Commit before the cap check.** The worker applies with `Edit` and hands nothing back; a cap that fires first strands round 5's fixes uncommitted.

## Stage 10b — handoff verification

Full contract:
-> Read `skills/run/references/handoff-verification.md`

Summary for sequencing: **launched SERIALLY — never in parallel** (both mutate production and contaminate each other). Fed artifacts only. Produces a blessing bound to the **branch tip SHA**. W x 1 for an invariant ticket: requirements adversary only under `$BACKFILL`, code reviewer only under `$REFACTOR`.

Three-way verdict branching, SALVAGE/DROP handling, and attempt cap are in:
-> Read `skills/run/references/stages-implement.md` (the 8a/10b section)

## Stage 12 — bot reviews are read once, never polled

Universal S9. Read the PR's existing bot comments once, inline, and sort three ways:

- **A real review** — verify each finding against the actual code, apply survivors, state refutations.
- **A non-review notice** (`Review limit reached`, `auto reviews are disabled`) — **not a clean pass**.
- **Silence.** Same action as the notice: proceed on the `review` worker's verdict.

Never post `@coderabbitai review` to force one. `$PR_BACKEND` selects whose comments to look for, nothing more.
