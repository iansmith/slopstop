# Stages 4-7 — red tests, mutation-check, phase-0 commit, adversary

Read when the orchestrator enters stage 4 for a ticket. Everything before this
(intake, investigate, branch) is in SKILL.md itself.

## `$FROZEN` — capture it once, thread it everywhere

**At the moment you make the stage-6 commit**, `$FROZEN = git rev-parse HEAD`. That is the
only moment it is unambiguous. **Recovering it later by scanning history is forbidden.**

`$FROZEN` goes to `slop-check`, `review`, and `vacuity-check`. `$BASE` — the branch point, a
different value with a different name — goes to `vacuity-check`, `complexity-check`, and `duplication-check`. Two
concepts, two names, no synonyms, no swapping.

## Stage 7 — the adversary round

The `adversary` worker does **one round and returns**. It cannot write, commit, or prompt.
The gap-test machinery below is yours.

**Launch** with `--target <the phase-0 test files> --goals <the ticket body + its DoD>
--caliber <the families relevant to a test suite>`.

**`adversary` is a review primitive: every round's close carries `findings`.** Transcribe the severity/class split into the object `run-jsonl.md` defines.

**One round. The adversary runs once and the orchestrator acts on its verdict:**

- `ADVERSARY PASS` -> advance to stage 8.
- `ADVERSARY FAIL: n` -> work the findings: add gap tests, verify them RED, commit. Then advance to stage 8. **Do not launch round 2.** Review (stage 10) and handoff (10b) catch anything the single adversary round missed — verification of the gap tests is their job, not a second adversary round's.
- `ADVERSARY PRESENTATIONAL: n` -> apply them and advance to stage 8. **One behavioural finding among twenty presentational ones is `FAIL`.**
  This applies to **stage 7 only** — `:tickets` and `:design` run their own adversary loops over documents where wording findings are the substance.
- `ADVERSARY GOAL DEFECT` -> the ticket itself is wrong. Stop and take it to the human.

**One span for the one round.**

**You classify nothing.** Severity and class come from the adversary and are quoted; you record only *disposition* (applied, rebutted, outstanding). A finding with no severity is escalated, not re-derived.

**The add decision is yours.** Under `--interactive`: present findings and ask `add all / add selected / skip`. Autonomously: add all.

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
