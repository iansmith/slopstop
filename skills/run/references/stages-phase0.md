# Stages 4-7 — red tests, mutation-check, phase-0 commit, adversary

Read when the orchestrator enters stage 4 for a ticket. Everything before this
(intake, investigate, branch) is in SKILL.md itself.

## `$FROZEN` — capture it once, thread it everywhere

**At the moment you make the stage-6 commit**, `$FROZEN = git rev-parse HEAD`. That is the
only moment it is unambiguous. **Recovering it later by scanning history is forbidden.**

`$FROZEN` goes to `slop-check`, `review`, and `vacuity-check`. `$BASE` — the branch point, a
different value with a different name — goes to `vacuity-check`, `complexity-check`, and `duplication-check`. Two
concepts, two names, no synonyms, no swapping.

## Stage 7 — the adversary loop, and everything around it

The `adversary` worker does **one round and returns**. It cannot write, commit, or prompt.
The loop and all machinery below are yours.

**Launch** with `--target <the phase-0 test files> --goals <the ticket body + its DoD>
--caliber <the families relevant to a test suite> --round <n>` and, from round 2,
`--prior <the previous round's findings>`.

**`adversary` is a review primitive: every round's close carries `findings`.** Transcribe the severity/class split into the object `run-jsonl.md` defines.

**Branch on its verdict line:**

- `ADVERSARY PASS` -> advance to stage 8.
- `ADVERSARY FAIL: n` -> work the findings, then run another round.
- `ADVERSARY PRESENTATIONAL: n` -> every finding is naming/comments/wording with no behavioural consequence. **Fix them, then run one `--verify-only` round.** `PASS` from that round advances to stage 8. **One behavioural finding among twenty presentational ones is `FAIL`.**
  This applies to **stage 7 only** — `:tickets` and `:design` run their own adversary loops over documents where wording findings are the substance.
- `ADVERSARY GOAL DEFECT` -> the ticket itself is wrong. Stop and take it to the human.

**Bracket every round separately** — `started`/`finished`/`failed` each carrying its `round` number.

**Cap at 3 rounds. At the cap, decide on the findings still STANDING — not on the verdict.**
Re-derive over the residue, using the worker's **own** `severity` and `class`, quoted:

| residue | exit |
|---|---|
| nothing standing | advance to stage 8 |
| all standing findings `presentational` | the `PRESENTATIONAL` path: apply, one `--verify-only` round, advance |
| any standing finding `blocker`/`major` **and** `behavioural` | human — `waiting_for_user`, round-3 findings quoted |
| **anything else** (e.g. `minor` + `behavioural`) | human |

**The last row is deliberate.** `minor` + `behavioural` matches neither presentational nor blocker/major — it escalates.

**You classify nothing.** Severity and class come from the adversary and are quoted; you record only *disposition* (applied, rebutted, outstanding). A finding with no severity is escalated, not re-derived.

**At the cap, apply a standing `presentational` finding rather than rebut it a third time.** Why: arguing costs more than complying, and a disagreement the loop has failed twice to settle will not be settled by the run.

> **Stage 10b already works this way and is the model** — see `handoff-verification.md`.

**The add decision is yours.** Under `--interactive`: present findings and ask `add all / add selected / skip`. Autonomously: add all.

**Argue, don't ignore.** A finding you disagree with is rebutted in the correction note sent into the next round. Silently dropping a finding looks identical to fixing it.

**A gap test naming surface that does not exist yet gets a stub.** Stubs are not frozen.

**A gap test carries a category tag** — `red-tests` Step 4a, same three categories, same required clauses. **A gap test you cannot categorize** is the same signal it is at Phase 0.

**Re-verify RED after adding gap tests.** Run the stage-4 test command. Every added gap test
must fail on current code. One that passes goes to the human as `revise / continue / abort`.

**Then commit, explicitly by path:**

```
git commit -m "[$TICKET] Phase 0: adversary gap tests — <N> cases added" \
           -m "Gap tests identified by adversary review. Fail on current code." \
           -m "Co-Authored-By: Claude <model> using slopstop <noreply@anthropic.com>"
```

Stage only the gap-test files and their stubs. Never `git add -A` here.

**If the worker is unavailable**, work the attack families yourself inline and say in the report that it was inline.
