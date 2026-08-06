---
layout: article
title: Prevention, Not Recovery
subtitle: What I learned building a tool to restrain AI coding agents
---

Got AI-generated bugs? Slop in your diffs? You are not alone.
[slopstop](https://github.com/iansmith/slopstop) is a Claude Code plugin for
**autonomous agents that build code without slop**. You hand it a ticket — or
twenty — and it drives them to merged without a human in the loop: tests written
before any implementation exists, scope fixed up front, and several independent
passes trying to find slop in the result before it merges. The bet: prevention is
cheaper than recovery, and it does not stop being true when nobody is watching.

## The problem with reviewing slop out

Most of the tooling around AI-written code is recovery tooling. It looks at a diff
that already exists and hunts for what is wrong with it. That is useful, and
slopstop uses these types of tools, but in conjunction with various other
analysis and adversarial agents. By the time slopstop invokes a code-review
tool, we should have prevented the really expensive mistakes like adding
new abstractions, out-of-scope implementations, or vacuous testing.
The review tools can, and are, victimized by code-writing agents because the
agent leaves a working program (with tests?) but the shape is the one the
agent chose. Put another way: Have you ever seen a code review agent say, "Throw
this whole thing away and do something simpler"?

Tests that pass are the interesting case. The common, sad failure mode of
AI-generated tests is that they are reverse-engineered from the implementation:
the agent reads the code it just wrote and writes assertions describing it. Those
tests pin the current behaviour, bugs included, and pass vacuously forever. A
review pass will not catch that. The tests are green. The diff is clean. The code
is wrong.

## What slopstop does instead

The effort moves earlier — before the implementation exists.

**Failing tests for what the ticket requires.** A dedicated pass writes the tests
first, from the ticket's stated behaviour rather than from any code. Then a second,
separate pass checks that each one is red for the *right* reason — not because a
symbol is missing or a fixture is absent, which looks identical at a glance and
certifies nothing. Only then are the tests committed and frozen, before a line of
implementation exists. The agent that writes the implementation may not touch them.

**A written Definition of Done and scope boundary.** Also drafted up front, in
plain language, on the ticket. You can see it is working when the agent stops
and asks *"would you like me to spin out a new ticket for this out-of-scope
task?"* instead of quietly widening the diff. The Definition of Done is the only
way a ticket's implementation can be merged: every item is scored against evidence
before the ticket closes, and "unverifiable" does not count as met.

**A clean-context review before it becomes someone else's problem.** A fresh
reader — no memory of writing the code, nothing to defend — reviews the diff for
over-engineering, dead code, and needless abstraction, verifies each finding
against the real code, and applies what survives. The session that wrote the code
never reviews it. That is the whole reason it works.

**A complexity gate that catches what simplification misses.** slopstop computes
cyclomatic complexity for every function in the diff, using
[lizard](http://www.lizard.ws) — and installs it for you if it isn't already
there. Functions in the elevated band are flagged; anything at or above the reject
threshold stops the ticket. This catches a specific AI failure mode: instead of
factoring a problem into small pieces, the agent stuffs everything into one
function with a dozen branches. A human reviewer might wave that through because
the tests pass. The complexity gate will not.

**A vacuity check that settles the argument by running it.** Every new test is
re-run against the code that predates the branch. A test that was *already* green
pins nothing — it is the most dangerous kind of slop precisely because it looks
like coverage. This is not a judgment call anybody can talk their way out of; it
is an exit status.

## It scales past one ticket — and past you

Preventing slop does not mean working alone, and it does not mean supervising.

`/slopstop:design` interviews you about an idea, or just some random thoughts,
until things are sufficiently clear about what you want and how you want it done
that we can write a Product Requirements Document and a Charter for it.

`/slopstop:tickets` cuts a ticket tree from that and hands the tree to an
adversary that tries to break it — against the PRD and Charter, before a single
ticket is created. If anything doesn't match up, the tree is rejected with a
reason and redrafted. Three rounds, then a human.

`/slopstop:run` takes it from there, and takes as many tickets as you give it. It
drives each one through the same fifteen-stage lifecycle — investigate, write the
failing tests, adversary, implement, gates, review, PR, merge, close, archive —
interleaving them so one ticket can be in review while another is still writing
tests. It works out which tickets can run together by predicting which files each
one will touch, and merges strictly one at a time regardless. It is **autonomous
by default**: there is a single `--interactive` flag if you want to be asked, and
without it the run decides and keeps going.

Every stage runs on a model tier you choose, and the checking work runs one tier
above the work it checks. Weaker models cost less but trigger more rounds of
correction — the usual money-for-time trade.

## Three things that hold when nobody is watching

**The mechanical gates never soften.** Red-test tampering, vacuity, and slop
findings stop a ticket in any mode and at any size of change, and there is no
permissive setting to find. This is deliberate and it was the hardest thing to
give up: any switch whose permissive value is the only one an unattended run can
use has quietly disabled that gate for exactly the agents it exists to police. A
gate that waves through for those cases is worse than no gate, because it reports
clean.

**A failing gate stops that ticket, not the run.** The ticket's branch and its
working notes are preserved exactly as they were, everything else keeps going, and
the whole stopped set is reported at the end with what each one needs from you. A
run that parks itself on the first problem is the failure mode autonomy has to
avoid.

**Every step is recorded, as it happens.** Each ticket keeps an append-only log of
every stage transition — the state machine, the resume point, and the timing
record in one file, timestamped by construction rather than derived afterwards.
Time spent waiting on a human is bracketed explicitly, so "this took nine hours"
can be separated from "…of which eight was me at dinner." An incomplete log
refuses to report numbers at all rather than emit a plausible-looking summary.
That last part is groundwork: skipping stages on genuinely trivial changes is the
obvious next feature, and it stays blocked until the timing is trustworthy enough
to say which stages are worth skipping.

## What it looks like when it catches something

Claims about adversarial verification are cheap, so there is a
[transcript](walkthrough/index.md). One
real run: a five-sentence feature description turned into seven merged PRs by a
fleet of deliberately underpowered agents, read in time order, quoting the
transcript at every point where the process caught something. (It predates the
current architecture — the walkthrough says where — but the catches are the point,
and the checks that made them are all still there.)

Among the catches: a design interview that finds a contradiction between two of the
human answers seventy seconds apart. An adversary that rejects a ticket tree because
the lock it specified would not actually have locked — and proves it with a
forty-trial experiment. An implementing agent that reported success, exited
cleanly with a green tree, and had done nothing at all. And a final adversary that
re-ran the suite, confirmed the code was correct, and then found that the
orchestrator's own report had fabricated a violation against one of its own
agents — followed by a public retraction on the ticket.

That last one is the one to sit with. The process caught its own supervisor lying.

## Try it

The walkthrough shows numerous examples of slopstop catching code errors, catching
ticket problems, and most importantly, _human design errors_. It is worth reading
in full.

Install slopstop:
```
/plugin marketplace add iansmith/slopstop
/plugin install slopstop@slopstop
```

Then point it at work you already have:
[`/slopstop:run <ticket> [ticket...]`](https://github.com/iansmith/slopstop/blob/master/WORKFLOW.md).
Or start from an idea with `/slopstop:design`.
