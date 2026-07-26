---
layout: default
title: What is slopstop?
author: iansmith
---

# What is slopstop?

slopstop is a Claude Code plugin. It replaces the prompt-and-hope loop with a
ticket-anchored one: work starts from a ticket, is scoped and test-anchored before
any implementation exists, and does not merge until two independent passes have
tried to find slop in it.

The bet it makes is that **prevention is cheaper than recovery.**

## The problem with reviewing slop out

Most of the tooling around AI-written code is recovery tooling. It looks at a diff
that already exists and hunts for what is wrong with it. That is useful, and
slopstop does it too — but by the time there is a diff to review, the expensive
mistakes have already been made. The agent has already chosen a shape, already
sprawled across six files it was never asked to touch, already written tests that
pass.

Tests that pass are the interesting case. The common, sad failure mode of
AI-generated tests is that they are reverse-engineered from the implementation:
the agent reads the code it just wrote and writes assertions describing it. Those
tests pin the current behaviour, bugs included, and pass vacuously forever. A
review pass will not catch that, because nothing about the diff looks wrong.

## What slopstop does instead

The weight moves earlier — before the implementation exists.

**Failing tests for what the ticket requires.** `/slopstop:plan` writes the tests
first, from the ticket's stated behaviour rather than from any code. They have to
be red, and red for the right reason, before implementation starts. Every work
item in the plan is anchored to a named test turning green.

**A written Definition of Done and scope boundary.** Also drafted up front, in
plain language, on the ticket. The tell that it is working is that Claude stops
and asks *"would you like me to spin out a new ticket for this out-of-scope
task?"* instead of quietly widening the diff.

**A simplify pass before the commit exists.** `/slopstop:pr` runs a simplify pass
over the uncommitted changes — over-engineering, dead code, needless abstraction —
while removing them is still free.

**A review pass that checks itself.** The PR review verifies every finding against
the actual code before reporting it, and sorts what survives into should-fix /
could-fix / skip. Findings that do not hold up against the code are refuted in
writing rather than dutifully applied.

## It scales past one ticket

Preventing slop does not mean working alone. `/slopstop:design` interviews you into
a PRD. `/slopstop:tickets` cuts a ticket tree from it and hands the tree to an
adversary that tries to break it. `/slopstop:run` drives parallel headless agents,
one per ticket, each isolated in its own git worktree, across four model tiers —
where every tier's work is checked by the tier above it.

The guarantees that hold for one ticket hold for the fleet: frozen tests with
tamper checks, independent handoff verification before any branch is integrated,
and a human gate at every stage boundary.

## What it looks like when it catches something

Claims about adversarial verification are cheap, so there is a
[transcript](https://github.com/iansmith/slopstop/tree/master/walkthrough). One
real run: a five-sentence feature description turned into seven merged PRs by a
fleet of deliberately underpowered agents, read in time order, quoting the
transcript at every point where the process caught something.

Among the catches: a design interview that finds a contradiction between two of its
own answers seventy seconds apart. An adversary that rejects a ticket tree because
the lock it specified would not actually have locked — and proves it with a
forty-trial experiment. An implementing agent that reported success, exited
cleanly with a green tree, and had done nothing at all. And a final adversary that
re-ran the suite, confirmed the code was correct, and then found that the
orchestrator's own report had fabricated a violation against one of its own
agents — followed by a public retraction on the ticket.

That last one is the one to sit with. The process caught its own supervisor lying.

## Try it

[Install it](index.md#install), then start from a ticket:
[`/slopstop:start <ticket>`](https://github.com/iansmith/slopstop/blob/master/WORKFLOW.md).
