# Node-ids — the one definition

A **node-id** is a string the test runner will accept to run exactly one test. Every stage
that names, threads, or compares tests uses these, and getting them wrong is silent: a set
that is too coarse reports "nothing changed" about a contract that lost most of its cases.

Read this instead of writing your own enumeration. It is deliberately short.

## The rule: ask the runner, never grep the source

**A declaration is not a node-id.** Test functions are the wrapper; the runnable units live
inside them — subtests, parametrized cases, table rows — and none of those has a `func` or
`def` line of its own.

Measured 2026-08-07:

| suite | the runner finds | `grep '^func Test'` / `grep '^def test'` finds |
|---|---|---|
| Go: one test with 3 `t.Run` subtests, plus one plain test | **5** | **2** |
| pytest: one `parametrize` of 2 cases, plus one class-nested test | **3** | **1** |

The pytest row is the sharper one. `TestGroup::test_inner` is indented, so `^def test`
misses it **entirely**, and both parametrize cases collapse into a single match. Delete the
nested test and one case and the grep count is unchanged — *"no shrink"*, reported with
confidence, on a suite that lost two thirds of its cases.

## Go cannot be enumerated statically. This is the constraint everything else bends around

```
go test -list '.*'   ->  TestOuter, TestPlain          # subtests INVISIBLE
go test -v           ->  === RUN   TestOuter/no_undiscovered_setter
                         === RUN   TestOuter/alpha
                         === RUN   TestOuter/beta
```

Go subtests are created **when the test body executes**. `-list` is not a cheaper `-v`; it
is answering a different question, and no static listing can reach a `t.Run` name. So for Go
the node-id set comes from parsing `=== RUN` lines out of a verbose run.

**Do not "simplify" this back to `-list`.** It looks like an obvious optimisation, it runs
faster, it produces a plausible shorter list, and it silently drops every subtest. That is
one command to re-verify (`go test -list '.*'` beside `go test -v`) and it is the
load-bearing fact of this file.

Go normalizes subtest names — spaces become underscores — so the parsed form
(`TestOuter/no_undiscovered_setter`) **is** the runnable form. Feed it straight back to
`-run`.

## Where the set comes from — never a new suite run

**Adding a suite execution to obtain node-ids is the wrong trade.** Every stage that needs a
set already has one available:

| stage | the run that already happens |
|---|---|
| `red-tests` Steps 3 and 6 | the baseline and the post-write run |
| `implement` Step 1.3 | the regression baseline |
| `mutation-check` Step 1 / B1 | every node-id, together and alone |

Capture the set from that output and report it. If a stage needs node-ids and no run has
happened there yet, that is a **threading** problem — carry the set forward from the stage
that ran — not a licence to run the suite again.

## Per-runner commands

Only two are measured. Others must be established the same way — run it, read the output,
record what you saw — and **not** assumed from the shape of these.

| runner | command | notes |
|---|---|---|
| Go | `go test -v ./...`, parse `^=== RUN\s+(\S+)` | the only route; `-list` cannot see subtests |
| pytest | `pytest --collect-only -q` | enumerates without executing; ids include `[param]` and `Class::test` |
| anything else | **establish it and record it here** | do not guess from the two above |

## `could-not-enumerate` is an outcome, not a zero

If the runner is unknown, the suite will not start, or the parse yields **zero** ids from a
suite that is not empty, the answer is `could-not-enumerate`. **Any check depending on the
set does not clear.**

Never report "no shrink" from a set you could not build. Every lethal failure of a gate in
this repo has had one shape: something measured zero, and zero read as fine.

## Comparing two sets

A **shrink** is any node-id present in the earlier set and absent from the later one. That
is a stop on its own, independent of any other verdict — a test that no longer exists cannot
fail a mutation probe or turn a suite red, so no downstream check will notice it for you.

Additions are not a shrink. Report them; they are usually the point.

Compare the **sets**, never the counts. Equal counts with different members is a
substitution, and it reads as clean to anything counting.
