---
layout: article
title: The Gates
subtitle: Every place slopstop's pipeline refuses to continue, and what an agent is given instead of an override
---

slopstop's pipeline is not a straight line from ticket to merge. It's a chain of
checkpoints, and at several of them the process simply stops — not "warns and
moves on," stops — until something specific resolves it. Some of those
checkpoints an agent can talk its way through with a logged reason. A couple of
them, deliberately, it cannot talk its way through at all.

This page is the list. Fourteen gates, grouped by where in the pipeline they
sit, each with what it blocks and what an agent gets instead of a bypass.

## Design & tickets — before any code exists

**Tier gate.** `/slopstop:design`, `/slopstop:tickets`, and `/slopstop:run` each
open by checking that the session's model actually matches the tier the stage
requires. If it doesn't, that's fatal — switch and retry, no mitigation
softens a genuine mismatch. But a session's self-reported model name is not
always trustworthy (a mid-session `/model` switch can leave the environment
still reporting the old family), so when the check can't verify itself, a human
can attest the real model instead of the gate blocking forever on a false
negative.

**Ticket-tree adversary.** Before a single ticket is created, a fresh, huge-tier
model reads the drafted tree against the PRD and charter with one job: fail it
if it can. It checks structure, PRD coverage, scope fidelity, whether file maps
point at real paths, and spot-checks factual claims against the actual repo.
Findings get applied and the same adversary re-reads the corrected draft — up to
three rounds. Still failing on round three doesn't get silently shipped; it
goes to a human with the surviving findings attached.

## Inside an agent's own session

These run *inside* the implementing agent's own `/slopstop:plan` and
`/slopstop:pr` invocations — the agent polices itself before anything reaches
the orchestrator.

**Adversary gap finder.** Before Phase 0 freezes, a fresh adversary attacks the
just-written test suite across six angles — boundary omissions, uncovered error
paths, untested state interactions, spec drift, false negatives, coverage
asymmetry. Gaps become new failing tests, verified red, before the freeze. This
one doesn't block so much as strengthen: it's the last chance to add coverage
before the tests become untouchable.

**Pre-PR health gate.** The full suite has to be green — or only failing on the
ticket's own not-yet-implemented Phase 0 tests — before a PR opens. A real
regression is a hard stop by default. A benchmark-mode config value lets it
proceed anyway, but only with a permanent, logged override record and a
warning baked into the PR body.

**Cyclomatic-complexity gate.** Any function touched in the diff that crosses
the complexity threshold is rejected the same way — hard stop by default, same
logged-override escape hatch in benchmark mode.

**Red-test tamper gate.** This is the one with no escape hatch. Every file
that entered the Phase 0 commit is diffed against HEAD, mechanically — no
judgment call, just a diff. A deleted test, a skipped test, or an assertion
whose expected value quietly changed all trip it, and **there is no override
value for this gate.** What the agent gets instead isn't a bypass — it's a
different exit entirely: if it genuinely believes the *ticket's* stated
expectation is wrong, it can halt with `TICKET UNDERSPECIFIED`, cite its
evidence, and stop clean. That costs nothing — no attempt spent — and sends the
ticket back for a rewrite. What it can never do is edit the test itself and
keep going.

**Slop-detection gate.** A separate pass scans for the softer test-writing
anti-patterns — rewriting a test to pass, inverting an expectation, tautological
assertions, scope creep, swallowed exceptions. These get an interactive
override with a reason, logged to a record kept deliberately distinct from the
tamper gate's — so anyone reading the audit trail later can tell "someone
overrode a style warning" apart from "someone unfroze a test," which is a much
bigger deal.

## Fleet-level, across the whole run

`/slopstop:run` launches a fleet of these agents in parallel and layers its own
gates on top, checking their work from *outside* the session that produced it.

**Branch-type resolution.** If a ticket carries no label or title pattern
indicating what kind of branch it needs, and no config default exists, the
orchestrator refuses to guess. A human adds a label or sets the config; a
ticket that stays unresolvable is marked `unrun` — no attempt spent, and it
doesn't block anything that doesn't depend on it.

**Handoff verification.** When an agent reports a ticket done, nothing it
claims is trusted. Two fresh subagents — a requirements adversary and a code
reviewer — independently re-read the actual diff from scratch. Both have to
pass before the ticket is blessed. A failure relaunches the same agent in the
same preserved worktree with the specific findings quoted back at it — a
fix-forward retry, one attempt spent, not a restart from zero.

**Rewrite delta check.** When a ticket needs its contract rewritten — most often
because its implementing agent hit the tamper gate for a legitimate reason — a
huge-tier check compares the old and new ticket text against the PRD and
charter before any relaunch is allowed. It has to say the rewrite added
specificity. If it instead subtracted scope — quietly made the ticket easier
to pass — that's rejected outright, and the scope gets restored or taken to a
human. Amending the PRD itself is never something the pipeline does on its
own authority.

**Budget exhaustion.** Two failed attempts on a ticket trigger an automatic
diagnosis before anything reaches a human: was this a defect in the ticket
(rewrite it) or a capability gap (try a stronger model)? Most stuck tickets get
resolved right there. Only once attempts, rewrite versions, and model
escalations are all exhausted does it become a human decision — and even then,
every ticket that doesn't depend on the stuck one keeps running while it waits.

**Drift check.** When every leaf under an umbrella ticket has individually
passed its own handoff verification, a large-tier check looks at the *landed
whole* against the PRD and charter — because leaves can each be individually
correct and still not add up to what was asked for. Findings become
fix-forward tickets run through the identical pipeline, not a full re-run.

**Final-report adversary.** Before a human ever sees the run's own summary of
itself, a huge-tier adversary tries to prove that summary wrong or incomplete —
working from ground truth (re-running the suite, reading actual ticket and PR
state), never from the report's own claims. Up to three rounds of fix-and-
reverify. Still failing after three, the report reaches the human with the
surviving findings attached — never a version cleaned up to look better than
it is.

**G-final.** The last gate has no mitigation, by design. A human has to
explicitly accept the run before any cleanup happens. Nothing an agent does
gets it past this one.

## The pattern underneath

Look across all fourteen and a shape falls out: the gates guarding *test
integrity* specifically — the tamper gate, and to a lesser extent the slop
gate — give an agent a legitimate way to stop, but never a legitimate way to
edit past them. Every other gate has an override, and every override leaves a
permanent, machine-readable record of who authorized what and why. The
pipeline doesn't trust an agent's judgment about whether *its own* tests are
still honest. It trusts a fresh adversary's judgment, or a human's, or a
mechanical diff that can't be argued with — and it writes down which one made
the call, every time.
