# What slopstop produces

> **Claude Desktop users:** commands in this document use the Claude Code form
> (`/slopstop:run`, `/slopstop:design`, etc.). If you installed via the Desktop
> installer, use the hyphenated form instead: `/slopstop-run`, `/slopstop-design`,
> and so on.

Measured 2026-08-06 to 2026-08-18. Thirty-six tickets, five repositories, one operator.

---

## Executive summary

Slopstop wrote **12,564 lines of production code** over thirteen days. It also wrote **31,192 lines
of tests** for them — a ratio of 2.5 to 1.

The rate was **134 production lines per agent-hour**. On an eight-hour day, one track running
continuously produces **1,075 production lines**.

A strong engineer produces about 250. That figure is explained below, and it is deliberately
generous.

**So one slopstop track is worth about 4.3 strong engineers.**

That is the worst case. It assumes one thing runs at a time. Slopstop does not work that way — it
launches every independent ticket at once, and the author runs several projects side by side.

Measured across the window, **total concurrency averaged 1.45x** — ticket concurrency of 1.35 and
project concurrency of 1.22. At measured concurrency: **1,555 production lines per day, or 6.2x
compared to a strong engineer.**

Slopstop rarely needs a human. Across thirty-six runs it stopped to ask a question **46 times —
1.3 times per run.** Twenty-two of the thirty-six never stopped at all. So the operator is not
watching it. The author runs four projects this way at once.

**1,555 production lines a day at 6.2x a strong engineer — and it is a measurement, not a
projection.**

---

## Two kinds of concurrency

These come up constantly below. They are different things, they have different limits, and they
are limited by different people.

**Ticket concurrency** — how many disjoint tickets run at once *inside one project*. Slopstop sets
this itself. It compares the predicted file map of every ticket it was given and launches
everything that does not collide. The ceiling is how many independent tickets the project actually
has. Nobody has to do anything for this to happen.

**Project concurrency** — how many projects are running at once. Slopstop does not set this. The
operator does, by starting runs in different repositories and answering each one when it asks a
question. The ceiling is how many notifications a person can keep up with.

**Total concurrency** is the two multiplied.

```
total = ticket concurrency x project concurrency
```

Both were measured over the window. Both are reported below. They came out very differently, and
the gap between them is the most actionable finding in this report.

---

## The baseline: what an engineer actually produces

The number to beat is lines of production code per working day. Published figures cluster low.

| Source | Lines per day |
|---|---|
| Fred Brooks, *The Mythical Man-Month* (OS/360) | ~10 |
| Capers Jones, across many projects | 16–38 |
| Steve McConnell, small projects (~10k LOC) | 20–125 |
| Steve McConnell, large projects (~10M LOC) | 1.5–25 |
| Andy Brice, solo, twelve years of his own data | ~50 |

The commonly cited range is 10 to 50. The middle is about 25.

We assume our engineer is a 10x engineer. So **250 production lines per day**.

Be clear about how generous that is. 250 is ten times the middle of the range — and **five times
the top of it.** The most productive case in the table is Brice at ~50 a day, self-measured over
twelve years. We are positing someone who sustains five times that, every working day. It is
possible this person does not exist.

**Tests are excluded from both sides.** Slopstop's 31,192 test lines are not counted in its
12,564. The engineer's tests are not counted in their 250. Production code against production
code.

We do assume the engineer writes tests — at minimum 2.5 lines per production line. That is 625
lines a day on top of the 250. Measured across these thirty-six tickets, the average ratio of
tests to production code is **2.5x** for slopstop — the same as the floor we grant the engineer.

One wrinkle is worth naming, because it cuts our way. The published figures do not say whether
they include tests.[^tests] **If they do, then 250 is not 250 lines of production code.** It is
production plus tests, and the production half is much smaller.

Solve for it. Let `x` be the real production rate, and inflate it by the same 2.5 test ratio we
just granted:

```
250 = x + 2.5x
250 = 3.5x
  x = 250 / 3.5
  x = 71.43 production lines/day
```

So our 10x engineer writes **71 production lines a day**, not 250. Every comparison in this report
gets better:

| | vs 250 | vs 71.43 |
|---|---|---|
| Slopstop, one track (1,075/day) | 4.3x | **15.1x** |
| Slopstop, at measured total concurrency (1,555/day) | 6.2x | **21.8x** |

**We do not use any of this.** We compare against the 250 engineer, not the 71 engineer. The rest
of this report holds 250 as production-only and reports 4.3x and 6.2x. Being generous is the
point. A number nobody can argue with is worth more than a bigger one.

---

## What we measured, and how

**Production lines.** Added lines in the branch diff, excluding test files and generated files.
Generated code — gqlgen output, protobuf, mocks, database codegen — is thrown out entirely. So is
every `_test.go`, `.test.tsx`, `test_*.py`, and everything under `testdata/`.

**Agent-hours.** Wall time each subagent spent working, summed across every launch in the run,
ignoring the time spent waiting on a human to respond. Read from the harness transcript, not
self-reported by the agent. A few workers inside a run overlap — the three mechanical gates launch
together — so the sum is slightly higher than the elapsed time it covers. We use the sum. It is
the conservative choice.

**What is excluded: `:design` and `:tickets`.** Neither stage is instrumented, so neither is in any
number here. This report measures the implementation pipeline only. What we know about them
without measurement:

- **`/slopstop:design` is almost entirely human wait.** It is an interview. The compute is small;
  the clock time is the operator thinking about and answering design questions. Counting it as
  slopstop cost would be counting the operator's own design work.
- **`/slopstop:tickets` is automated.** It cuts the ticket tree and runs the adversary loop over
  it with no human input. Real compute, no attention.

So the excluded work is one stage that costs attention and no compute, and one that costs compute
and no attention. Neither is measured today. [A ticket is open to instrument both into
`run.jsonl`.](https://github.com/iansmith/slopstop/issues/619)

### Measuring the two concurrencies

Slopstop needs a human 1.3 times per run. That is what makes project concurrency possible at all.
It is not a side effect. **It is the reason the thirty-six tickets in this report were spread
across five repositories rather than done one after another.** That was the operating method for
the window, not an accident of scheduling.

**Total concurrency.** Every subagent launch carries a start and a finish timestamp. Sum them:
87.7 hours of agent time. Take the union — wall-clock time during which *any* agent anywhere was
working: 60.7 hours. The ratio is **1.45x**.

**Project concurrency.** Same union, but counting distinct repositories rather than agents. Mean
**1.22**. Put another way, 20% of active time had two or more projects live; 80% had exactly one.

**Ticket concurrency was 1.35.** Sophie ran tickets in parallel — three batches of two to three
tickets launched at once — giving it a within-repo ticket concurrency of 1.33. The other
repositories ran tickets serially.

| | Measured | Set by |
|---|---|---|
| Ticket concurrency | **1.35** | slopstop — scheduling launched disjoint tickets in parallel |
| Project concurrency | **1.22** | the operator |
| **Total** | **1.45** | |

The 1.45 does not decompose cleanly into 1.35 × 1.22 (= 1.65), and the gap is worth naming
rather than hiding. It is **worker** overlap, not ticket overlap: the three mechanical gates launch
together inside a single ticket's run, and one ticket's closing stages sometimes overlap the next
ticket's opening ones. The product counts both kinds; total concurrency is the real measure — the
ratio of agent time to wall-clock time, and it already includes everything.

| Agents running at once | Share of active time |
|---|---|
| 1 | 66% |
| 2 | 25% |
| 3 | 8% |
| 4+ | 1% |

**Both multipliers are now in play, and both are well below their ceiling.**

Project concurrency of 1.22 against a target of four is about a third of what was being
attempted. Ticket concurrency of 1.35 reflects one repository (sophie) using the scheduling
feature, while the other four ran tickets one at a time.

The gap is not slopstop waiting on compute. It is the operator missing notifications. A run
finishes a stage, asks its one question, and sits there until somebody notices. Four projects only
pay off if you answer all four promptly, and over this window that did not happen.

**Every number in this report is reduced by both shortfalls.** They describe a system where only
one repository ran tickets in parallel, and the operator reached a third of the intended project
concurrency. That is the honest reading, and it is the conservative one.

---

## The numbers

Thirty-six tickets. Thirty-one have timing records reliable enough for rate calculations.

| | Value |
|---|---|
| Production lines written | 12,564 |
| Test lines written | 31,192 |
| Test-to-production ratio | 2.5 : 1 |
| Agent time (31 tickets with reliable data) | 87.7 hours |
| **Production lines per agent-hour** | **134** |
| **Production lines per 8-hour day, one track** | **1,075** |
| **Production lines per 8-hour day, at measured concurrency** | **1,555** |
| Mean agent time per ticket | 2h 50m |
| Agent launches | 761 |

Per-ticket rate ranged from 15 to 1,420 production lines per agent-hour. The median was 95.

---

## Human input

Human time is not the interesting measurement. It is small, and it is not what limits throughput.

Across thirty-six runs, slopstop stopped to ask a question **46 times**. That is **1.3 stops per
run**. Twenty-two runs never stopped.

Total bracketed wait was 25.7 hours. That number is misleading and should not be quoted. A "wait"
runs from the moment slopstop asks until the moment somebody answers, so it absorbs lunch,
errands, and sleep. It measures the operator's day, not the process.

Split the waits and the real cost appears. **Forty-four of the forty-six were under thirty
minutes.** The two that were not ran 7.0 and 13.4 hours — runs that asked their question in the
evening and got answers the next morning.

| | |
|---|---|
| Waits under 30 min | **44 of 46** (96%) |
| Their total | **5.3 hours** |
| Their mean | 7.2 min |
| **Their median** | **5.2 min** |
| Waits over 30 min | 2 (7.0h and 13.4h, overnight) |

**Thirty-six tickets and 12,564 production lines cost 5.3 hours of human attention.** About nine
minutes per ticket, answered in a median of five minutes.

The measurement that matters is compute consumed. That is the thing that multiplies. Human time is
worth measuring only to show how little of it there is.

### Slopstop does need humans, and the places it does are the valuable ones

This is not a system you point at a repository. It stops, and where it stops is the point.

**Design is human work.** `/slopstop:design` interviews you. It argues. It produces a PRD only
when it has a shared understanding. This is the highest-leverage input in the whole process,
because the PRD shapes every ticket cut from it and every implementation cut from those. A wrong
assumption fixed here costs a sentence. Fixed at stage 10 it costs a run.

**A gate failure stops the run.** The common cases:

- An adversary finds a gap and the fix requires a decision, not a test.
- A complexity gate blocks and the honest fix is a refactor outside the ticket's scope.
- The Definition of Done cannot be met as written, because the ticket was wrong.
- Two tickets disagree about the same behaviour.
- A rule has to be broken, and only a human can authorise it.

That last one is the most common. Slopstop's gates have no permissive setting, deliberately.
There is no flag that softens a gate because the change looked small. When the right answer is
genuinely "ship it anyway", a human says so, and the log records who decided and why.

These stops are worth the interruption. They are the moments where judgment is actually required
— preferences, tradeoffs, and business context the model does not have. Everything else runs
unattended.

---

## The economic argument

Compare like with like. Production lines per eight-hour day.

| | Production LOC/day |
|---|---|
| 10x engineer (generous) | 250 |
| Slopstop, one thing at a time | 1,075 |
| Slopstop, at measured total concurrency | 1,555 |

**Sequential is 4.3x. At the total concurrency actually observed it is 6.2x.**

The 6.2x rests on a measured total concurrency of 1.45x, explained above — ticket concurrency of
1.35 and project concurrency of 1.22, both well below their ceiling.

Slopstop's *total* output is higher still, because the 2.5:1 test ratio is not counted above. At
134 production lines per agent-hour it writes roughly 335 more lines of tests. Those tests are
mutation-proven and vacuity-checked. They are not filler.

### The bigger win: the operator is free

Speed is the smaller half of this.

Slopstop consumes 2h50m of compute per run and asks for nine minutes of attention to get it.
Discount the two overnight gaps — that is sleep, not process — and the ratio is roughly **one
five-minute question per two hours of unattended work.**

That changes what a person can do. You are not supervising a run. You are starting one, going
somewhere else, and coming back when it asks.

The author runs **four slopstop projects concurrently.** That is not a stunt. It follows directly
from the interruption rate. Four projects at 1.3 stops each is about five decisions spread across
several hours of elapsed time.

That was the method over this window: thirty-six tickets across five repositories, worked in
parallel, not in sequence.

**Project concurrency only reached 1.22.** The bottleneck was not slopstop and it was not compute
— it was noticing that a run had stopped and was waiting. Missed notifications.

That is a fixable problem, and it is the single largest lever in this document. **The 6.2x was
achieved at about a third of the intended project parallelism.**

---

## What would make this wrong

Stated plainly, because the argument above is only as good as these.

**Lines of code is a bad metric.** It always has been. The defence here is that both sides are
measured the same way, on added production lines, with generated code excluded from ours and
tests excluded from both. It is not a defence of the metric.

**The comparison is not like for like, and this is the biggest weakness.** The 10–50 range is a
*whole-job* number. It includes meetings, design, code review, debugging, on-call, and rework. Our
134 lines per agent-hour covers the implementation pipeline only. Design and ticket-writing are
excluded. If you loaded slopstop with the same overhead the engineer carries, the gap narrows. By
how much, we have not measured.

**The sample is small.** Thirty-six tickets, thirteen days, one operator, five repositories,
mostly Go and TypeScript. It is a working record, not a study. Nobody built these tickets twice.

**Generated code was excluded by pattern matching.** Filenames matching `generated`, `_gen.go`,
`.pb.go`, `gqlgen`, and `mock_` were dropped. A miss would inflate our number.

**Verbosity is unmeasured.** If slopstop writes more lines to do the same work, a per-line
comparison flatters it. We did not check.

---

## Conclusion

On the measured window, delivering into five real repositories:

- **134 production lines per agent-hour.**
- **1,075 per eight-hour day, single track.** That is **4.3x** a very generous engineer.
- **1,555 per day at measured total concurrency of 1.45x** — ticket concurrency 1.35, project
  concurrency 1.22. That is **6.2x compared to a strong engineer.**
- **1.3 human interruptions per run**, which is what makes four concurrent projects possible.

The multiplier that matters is not the one on the code. It is the one on the person. Slopstop's
claim is not that it types faster. It is that it does not need watching — and an engineer who is
not watching can be somewhere else.

---

## Buried lede

Everything above is what slopstop did with **both concurrency multipliers well below their
ceiling** — ticket concurrency of 1.35 against a demonstrated three-at-once, project concurrency
of 1.22 against a target of four — and its tests thrown away before counting. Here is the same
machine at its intended operating point.

Count tests on both sides. Give the engineer 250 production lines and the 2.5x test suite we
already granted them: **875 lines a day.** Give slopstop its measured 2.5x ratio: **469 lines per
agent-hour, 3,752 a day.**

Now let both concurrencies reach their target. **Ticket concurrency of 2** — slopstop given a
batch of independent tickets rather than one at a time. **Project concurrency of 2.5** — well
short of the four attempted, and about double the 1.22 achieved. Multiply: **5x total
concurrency**.

```
slopstop  3,752 x 5   = 18,760 lines/day
engineer  250 + 625   =    875 lines/day
                        --------
                          21.4x
```

# One engineer, four projects, twenty-one times the output

Not twenty-one times faster at typing. Twenty-one times the delivered, tested, reviewed code —
from one person who is mostly not in the room.

The gap between 6.2x and 21.4x is not a better model. It is answering the notification.

---

[^tests]: **What we actually know about test inclusion.** No source states a counting rule. That
    is the honest answer, and we went looking.

    The evidence leans toward tests being excluded. The phrase the sources use is "debugged,
    tested code." That describes the state of the production code. It does not say test lines
    were counted. Nobody writes it the other way round.

    Three things point the same direction. Brooks measured OS/360 in the 1960s, before large
    committed test suites were normal practice. McConnell's figures are whole-project SLOC by
    project size, and SLOC counts conventionally mean shipped source. Brice measured his own
    product's code, solo, and separately noted he spends under half his day coding at all.

    Against that: none of it is a stated rule, and Capers Jones' figures span many projects with
    counting conventions he does not publish here.

    So we assume the figures are production-only. That is the assumption that makes 250 a
    production number, and it is the one that makes slopstop look worse. If it is wrong, every
    multiple in this report is understated by roughly 3.5.

**Sources for the baseline figures:**
[Successful Software — How much code can a coder code?](https://successfulsoftware.net/2017/02/10/how-much-code-can-a-coder-code/) ·
[Mythical Man-Month — 10 lines per developer day](https://seniordba.wordpress.com/2014/12/19/mythical-man-month-10-lines-per-developer-day/) ·
[Productivity in the Software World — Extentia](https://www.extentia.com/productivity-in-the-software-world/)
