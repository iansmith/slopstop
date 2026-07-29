---
layout: article
title: How slopstop works
subtitle: High-level overview of slopstop in Claude Code
---

Slopstop is a pipeline that turns a feature idea into working code by putting
human judgment exactly where it matters — and automating everything else.

## Design

It starts with design. `/slopstop:design` uses an adversarial interview process
(via `/slopstop:grill`) to force both you and Claude to build a shared
understanding of what you're building and why. This isn't fast — it's a real
conversation — but it produces a PRD and a charter that actually reflect what you
want, not what the model assumed you wanted.

## Tickets

From there, `/slopstop:tickets` breaks the design into a tree of implementable
tickets. This should run hands-free, but adversaries are watching: they check
whether the tickets actually cover everything in the PRD, and they flag tickets
that go beyond the PRD's scope — no gold-plating, no silently dropped
requirements. If the system can't resolve a gap or a scope violation on its own,
it stops and asks you.

## Implementation

Once the ticket tree is solid, `/slopstop:run` launches agents to implement each
ticket, coordinating them so they don't collide. The agents try to work
autonomously — two attempts with a lighter model (Haiku by default), escalating
to a heavier one (Sonnet) if both fail. You can configure this tradeoff: cheaper
models mean more failed attempts but lower cost; stronger models mean fewer
retries but higher spend.

## Verification

After implementation, the scrutiny ratchets back up. Adversaries check whether
the code actually does what the PRD specified. A final report is generated and
verified for accuracy across three attempts. At each of these checkpoints, if the
system can't satisfy itself, it asks for human help rather than shipping
something wrong.

## The tradeoffs

Slopstop is slow. The checks are thorough, and thoroughness takes time. It's
also slow in a second, more human way: because it runs autonomously, you often
walk away and come back later, which means elapsed time grows even when compute
time doesn't.

It's prescriptive. You follow its workflow — design, then tickets, then
implementation, then verification. If you want to skip the design phase and just
hack, slopstop is the wrong tool.

But the bet is simple: the time you spend upfront in design and the time the
system spends on verification is less than the time you'd spend debugging slop,
unwinding bad assumptions, and recovering from an agent that confidently built
the wrong thing.

In the best case, you spend 20 minutes in the design interview and everything
else is automated. In practice, you'll get pulled back in at checkpoints — but
only at moments where your input actually changes the outcome.
