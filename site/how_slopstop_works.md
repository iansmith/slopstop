---
layout: article
title: How slopstop works
subtitle: High-level overview of slopstop in Claude Code
---

<div class="install-note">
<strong>Claude Desktop users:</strong> commands on this page are shown in the
Claude Code form (<code>/slopstop:run</code>, <code>/slopstop:design</code>, etc.).
If you installed via the Desktop installer, use the hyphenated form instead:
<code>/slopstop-run</code>, <code>/slopstop-design</code>, and so on.
</div>

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
ticket, coordinating them so they don't collide. It works out which tickets touch
the same files and only runs the ones that don't overlap side by side.

That coordination has a physical mechanism, not just a policy. Each ticket gets its
own **git worktree** — a separate checkout of the same repository, on its own
branch, in its own directory. Two tickets running at once cannot see or disturb each
other's tree, and the checkout you are sitting in is never switched out from under
you. It also keeps the scheduling honest: a checkout is exclusive, so tickets that
would have to share one are made to wait rather than trusted to behave.

Each ticket goes through the same sequence: explore the code, write failing tests
for what the ticket asks for, prove each test fails for the *right* reason, attack
the plan adversarially, then implement. The implementer may *add* tests; it may
never weaken, retarget or remove one.
A ticket that fails implementation twice stops, on the theory that a second failure
is usually an underspecified ticket rather than an under-powered model. You fix the
ticket, not the retry count.

Which model does what is configurable per project, and checking work always runs a
tier above the work it checks.

## Verification

After implementation, the scrutiny ratchets back up. Three mechanical gates run
together — one hunts for slop the tests wouldn't catch, one proves each new test
would actually have failed before the change existed, and one measures complexity —
followed by a code review in a context that never saw the conversation that wrote
the code.

Then the whole account gets checked by somebody else again. A **handoff
verification** step runs fresh checkers one model tier *above* the work they are
reviewing, feeds them artifacts only — the diff, the ticket, the frozen tests — and
never shows them the orchestrator's claims about what it did. What comes back is
tied to a specific commit; move the branch and the approval no longer applies. In
practice this is the noisiest step in the pipeline, because the findings that reach
it are the ones that survived everything before it.

Those three gates have no permissive setting. They don't soften because nobody is
watching, and they won't soften because the change looked small. A gate that waves
through the cases it exists to police is worse than no gate, because it reports
clean.

## Fixing bugs (when the ticket already exists)

Not every ticket starts with a design phase. Bug reports land from teammates, from
users, from CI — and they rarely arrive in the shape slopstop needs to build from.
They say what broke, not what "done" looks like.

`/slopstop:tickets --retrofit <TICKET>` bridges that gap. It takes one existing
ticket — whatever state it's in — and brings it up to the same five-section standard
that `:tickets` produces from a PRD. It reads the ticket body and comments, grills
you on anything the original doesn't answer (exploring the codebase first where that
settles a question without bothering you), and drafts the missing structure: the DoD,
the file map, the scope boundary. An adversary loop checks the result, the same way
it checks tickets cut from a design. The original text is preserved verbatim at the
bottom, so nothing is silently rewritten.

Once the retrofit is done, `/slopstop:run` picks up the ticket like any other — same
worktree isolation, same test-first sequence, same verification gates. The ticket
just entered the pipeline from a different door.

This matters because the alternative is what usually happens: someone grabs the bug
report and starts coding. The ticket said "X is broken," the fix addresses X, but
nobody wrote down what "fixed" means — so the review checks whether the code looks
right rather than whether it satisfies a contract. Retrofit forces that contract to
exist before implementation starts.

## The tradeoffs

Slopstop is slow. The checks are thorough, and thoroughness takes time. It's
also slow in a second, more human way: because it runs autonomously, you often
walk away and come back later, which means elapsed time grows even when the machine
was idle the whole while.

Slopstop now measures that distinction rather than guessing at it. Every stage of
every run is timestamped into an append-only log, and the moments it spends waiting
on *you* are bracketed explicitly — so "this took eleven hours" and "this took
eleven hours, forty minutes of which were machine time" stop being the same
sentence.

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
