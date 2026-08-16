# Six things the checks caught

This is a short reading of what slopstop's verification actually *does*, drawn from real runs
against a real codebase in August 2026. It is not a tour of the pipeline — [COMMANDS.md](https://github.com/iansmith/slopstop/blob/master/COMMANDS.md)
is the reference for that. It is six defects, each caught by a **different** mechanism, each
quoted from the run log that recorded it at the time.

The point of picking six different checks is that they fail differently. A code reviewer and a
complexity gate and a mutation prober are not three flavours of "look at the code harder" — they
catch disjoint classes of wrong, and five of the six findings below would have survived a fully
green test suite.

---

## What you need to know before reading

**The unit of work is a ticket, not a prompt.** Every run starts from a ticket that already
carries a description, a scope fence, a file map and a Definition of Done. If those are missing
or wrong, the run stops at intake before a branch exists.

**Tests come first, and then they are frozen.** Stage 4 writes tests that fail against current
code. Stage 6 commits them and records that commit as `$FROZEN`. From then on, the agent whose
code has to satisfy those tests cannot edit them — and a gate checks, at every subsequent stage,
that it didn't.

**Nothing is taken at face value, including a passing test.** "The suite is green" is the
beginning of the checking, not the end of it. Three mechanical gates and two independent
reviewers run *after* the tests pass, and they ask different questions: would this test have
passed before the change existed? is it pinned to the behaviour it names? did this function get
more complex? does the diff do what the ticket said?

**Every check runs with no memory of the conversation that produced the work.** Workers are
launched as subagents with their own context. A session that has spent an hour justifying a
design will justify it again if you ask it to review that design; the isolation is the whole
mechanism, and it exists because a slopstop PR once recorded a clean review that the authoring
session had performed on its own code.

**Where these came from.** All six are from [`iansmith/aatoolkit`](https://github.com/iansmith/aatoolkit),
a Go library for bridging telephony audio to realtime model APIs — tickets AATK-82, AATK-85,
AATK-87 and AATK-93, run between 2026-08-13 and 2026-08-15. Together those four tickets consumed
93 agent launches and about 12 hours of machine time. The excerpts are copied verbatim from each
run's `run.jsonl`, which is written as the run happens and is append-only.

---

## The six

| | Check | Stage | What it caught |
|---|---|---|---|
| 1 | **mutation-check** | 5, before any implementation | The obvious implementation of a frozen contract would have shipped broken — proven by building it and watching it fail |
| 2 | **adversary** | 7 | Two production bugs that *only* the adversary's demanded gap tests could detect — measured, not asserted |
| 3 | **vacuity-check** | 9 | A gate that refused to report a pass on an incomplete measurement, and named the orchestrator's own bad arguments as the cause |
| 4 | **complexity-check** | 9 | A function that got worse — separated from 170 pre-existing violations it deliberately ignored |
| 5 | **tamper gate** | 8a / 10b | Removed lines in a frozen test file, attributed commit by commit to prove who removed them |
| 6 | **review loop** | 10 | A concurrency bug, then the same bug one layer beneath its own fix, then the fact that neither fix had any test coverage |

---

## Reading order

- **[Before any code exists](01-before-the-code.md)** — findings 1 and 2. The two checks that run
  while the implementation is still a stub, and what they buy you.
- **[The mechanical gates](02-the-mechanical-gates.md)** — findings 3 and 4. Measurement, not
  judgment: gates that execute something and report a number.
- **[Integrity and review](03-integrity-and-review.md)** — findings 5 and 6. Proving the tests
  weren't gamed, and what a reviewer finds when it is allowed to keep going.

---

## How to read the excerpts

Each block is the `result` field of one record in `run.jsonl`, written by the orchestrator or
quoted from the worker that returned it, at the moment it happened. They are unedited except for
truncation, marked `[…]`. They are terse and they use the vocabulary in COMMANDS.md — `PINNED`,
`VACUOUS`, `SALVAGE`, `$FROZEN`, `probe A/B/C`. Each section explains what the check was doing
before it shows you what the check said.

They are also, deliberately, not success stories. Finding 3 is a check catching the
orchestrator's mistake. Finding 5 is the tamper gate reporting removed lines from a frozen file
and then having to prove they were legitimate. A log that only recorded wins would not be worth
publishing.
