---
layout: article
title: The Gates
subtitle: Every place slopstop's pipeline refuses to continue, and what an agent is given instead of an override
---
<div class="gates-layout wide-layout">
<div class="gates-prose">

<p>slopstop runs autonomously. You hand it tickets and it drives them to merged
without a human in the loop — which is exactly why the places it refuses to
continue matter more than they would in a tool someone is watching. The pipeline
is not a straight line from ticket to merge. It's a chain of checkpoints, and at
several of them the process simply stops — not "warns and moves on," stops —
until something specific resolves it. Some of those checkpoints a human who has
read the finding can wave past. A few of them, deliberately, <em>nobody</em> can:
not the agent, not a config setting, not you.</p>

<p>This page is the list. Sixteen gates, grouped by where in the pipeline they
sit, each with what it blocks and what an agent gets instead of a bypass. Terms a
newcomer to slopstop might not know are marked in bold, with a short note on the
side explaining them.</p>

<p>Two things to know before the list, because they shape all of it. First, the
gates are not code baked into one big program — each is a
<strong>worker</strong><span class="sidenote" role="note"><span class="sidenote-entry"><strong>worker</strong> — a single-purpose agent launched with no memory of the conversation that produced the work it is checking. There are eleven of them; five do gate work.</span></span> launched
fresh at a defined stage, handed file paths and commit ids rather than anybody's
summary of what happened. A worker that is missing an argument it needs reports
that it is blocked; it never guesses one and proceeds. Second, every gate a run
passes or fails is written to an append-only log as it happens, so "which gate
stopped this, and when" is a fact on disk rather than a reconstruction.</p>

<h2>Before any code exists</h2>

<p><strong>1. Tier gate.</strong> <code>/slopstop:design</code> and
<code>/slopstop:tickets</code> each open by checking that the session's model
actually matches the <strong>tier</strong><span class="sidenote" role="note"><span class="sidenote-entry"><strong>tier</strong> — a mapping in the project's config from a role (huge / large / medium / small) to a specific model. Higher tiers do adversarial and checking work; lower tiers do the bulk implementation.</span></span> the stage
requires. If it doesn't, that's fatal — switch and retry, no mitigation softens a
genuine mismatch. But a session's self-reported model name is not always
trustworthy (a mid-session <code>/model</code> switch can leave the environment
still reporting the old family), so when the check can't verify itself, a human
can attest the real model instead of the gate blocking forever on a false
negative. The reason it matters: everything downstream — every threshold, every
worker's model — is resolved once, here, and passed onward explicitly. A
wrong-tier start misconfigures the whole run quietly.</p>

<p><strong>2. Spec integrity.</strong> If you name an authoritative
specification for a run, it has to exist. A declared spec that isn't there is a
hard stop, not a warning, and its content hash is recorded in the
<strong>PRD</strong><span class="sidenote" role="note"><span class="sidenote-entry"><strong>PRD</strong> — the Product Requirements Document the design stage writes; the reference every ticket is later checked against.</span><span class="sidenote-entry"><strong>charter</strong> — binding implementation rules for this particular piece of work, layered on top of the PRD.</span></span> header.
Running with no spec at all is fine and normal — it's recorded as such. Running
against a spec you <em>think</em> is loaded and isn't would poison every
downstream check with confident citations of a document nobody read.</p>

<p><strong>3. Ticket-tree adversary.</strong> Before a single ticket is created,
a fresh, huge-tier model reads the drafted tree against the PRD and charter with
one job: fail it if it can. It checks structure, PRD coverage, scope fidelity,
whether <strong>file maps</strong><span class="sidenote" role="note"><span class="sidenote-entry"><strong>file map</strong> — the specific files a ticket is expected to touch, agreed up front.</span></span> point at real
paths, and spot-checks factual claims against the actual repo. Findings get
applied and the same adversary re-reads the corrected draft — up to three rounds.
A finding the drafter disagrees with must be <em>argued</em> in the correction
note that goes into the next round, never silently dropped: a dropped finding and
a fixed one look identical afterwards, which is the whole reason for the rule.
Still failing on round three doesn't get quietly shipped; it goes to a human with
the surviving findings attached.</p>

<p><strong>4. Partial-creation stop.</strong> Creating a tree is many API calls,
and they can fail halfway. If they do, the run stops and hands you the map of what
exists — it does not retry the draft, because retrying would double-create
everything that already succeeded, and the tickets that exist may already
reference the ones that don't.</p>

<p><strong>5. Rewrite delta check.</strong> When a ticket needs its contract
rewritten — most often because implementation failed twice and the ticket, not
the code, looks like the problem — a huge-tier check compares the old and new
ticket text against the PRD and charter before the ticket system sees anything.
It has to say the rewrite added specificity. If it instead <em>subtracted</em>
scope — quietly shrank the Definition of Done until the code that already exists
would satisfy it — that's rejected outright, and the scope gets restored.
Amending the PRD itself is never something the pipeline does on its own
authority.</p>

<h2>Inside a ticket's lifecycle</h2>

<p>These sit at fixed stages of <code>/slopstop:run</code>, which drives each
ticket through the same fifteen-stage sequence. The
<strong>orchestrator</strong><span class="sidenote" role="note"><span class="sidenote-entry"><strong>orchestrator</strong> — the single top-level session running <code>/slopstop:run</code>. It launches every worker and does the mechanical git and ticket work itself, but never implements a ticket.</span></span> launches the
checking workers; it does not do their judging, and the worker that writes code
is never the worker that checks it.</p>

<p><strong>6. Mutation check.</strong> The tests are written before the
implementation and have to be failing. This gate asks the harder question: are
they failing for the <em>right reason</em>? A test that's red because a symbol is
missing, a fixture is absent, or it asserts something no implementation could
satisfy looks exactly like a good red test — both print FAIL — and certifies
nothing. Each test gets its own verdict, with evidence.</p>

<p><strong>7. Adversary gap finder.</strong> Before <strong>Phase 0</strong><span class="sidenote" role="note"><span class="sidenote-entry"><strong>Phase 0</strong> — the required first commit on a ticket's branch: the tests the ticket needs, committed and shown failing, before a single line of implementation exists.</span></span> freezes, a
fresh adversary attacks the just-written test suite — boundary omissions,
uncovered error paths, untested state interactions, drift from the ticket,
false negatives, coverage asymmetry. Gaps become new failing tests, verified red,
before the freeze. Two ways it stops rather than strengthens: if a gap test comes
up <em>green</em>, that is not evidence of a covered case and the ticket halts
until someone says otherwise; and if the adversary concludes the <em>ticket</em>
is wrong rather than the tests, that goes to a human untouched. You do not fix a
wrong ticket by editing a test.</p>

<p><strong>8. Red-test tamper gate.</strong> This is one of the three with no
escape hatch anywhere. Every file that entered the Phase 0 commit is compared
against the branch tip. A deleted test, a skipped test, an assertion whose
expected value quietly changed, a shadowing redefinition, or an expected value
moved into an edited helper all trip it — and <strong>there is no override for
this gate in any mode.</strong> What an agent gets instead isn't a bypass, it's a
different exit: if it genuinely believes the <em>ticket's</em> stated expectation
is wrong, it can stop clean and say so, citing evidence, which sends the ticket
back to be rewritten under gate 5. What it can never do is edit the test and keep
going.</p>

<p><strong>9. Slop detection.</strong> A separate reading pass over the whole
diff for the softer anti-patterns — a test rewritten to accommodate the
implementation, an inverted expectation, tautological assertions, swallowed
errors, scope creep past what the ticket asked for. It reports; it fixes nothing,
deliberately, because a finding quietly "cleaned up" by the same pass is a finding
nobody ever saw. A serious finding stops the ticket, in every mode.</p>

<p><strong>10. Vacuity gate.</strong> The mechanical counterpart to gate 9, and
the one that settles the argument by running it. Every new test is re-executed
against the code that predates the branch. A test that was <em>already</em> green
pins nothing — it is the most dangerous kind of slop precisely because it looks
like coverage: green, named after the behaviour, and it will stay green when that
behaviour is deleted next year. The verdict is an exit status, not an opinion.
This runs <em>after</em> implementation on purpose: the gate-7 adversary can't see
tests written later, and this is what covers them.</p>

<p><strong>11. Complexity gate.</strong> Every function touched in the diff is
measured for <strong>cyclomatic complexity</strong><span class="sidenote" role="note"><span class="sidenote-entry"><strong>cyclomatic complexity</strong> — a standard metric counting the independent paths through a function. Higher numbers mean more branching, and usually harder-to-test code.</span></span> against the
project's configured thresholds. Functions in the elevated band are reported and
the run proceeds; anything at or above the reject threshold stops the ticket. The
thresholds are per-project config, and the gate refuses to run without being told
them — it carries no defaults of its own, because a gate measuring against a
number nobody configured names the wrong bound with total confidence. Also
mechanical: it's a number from a tool compared to a number from a file.</p>

<p><strong>12. Clean-context review.</strong> A fresh reader with no memory of
writing the code reviews the diff, verifies each finding against what's actually
there, and applies the ones that survive. It loops — each round a new reader, so
round four can't rationalise round three's edits — until it comes back clean, up
to five rounds. Hitting the cap is not a pass: the run reports the last round's
surviving findings and stops that ticket.</p>

<p><strong>13. Definition-of-Done gate.</strong> After the merge lands and
before the ticket is allowed to close, every item in its Definition of Done is
scored against evidence — the diff, the recorded test run, the frozen red tests.
Items come back <code>met</code>, <code>not-met</code>, or
<code>unverifiable</code>, and <code>unverifiable</code> is not a polite
<code>met</code>: it blocks exactly as <code>not-met</code> does. The honest
answer when evidence is missing has to be loud, because a scorer reaching for the
wrong evidence returns <code>unverifiable</code> for <em>everything</em>, and that
must be impossible to mistake for success.</p>

<h2>Across the whole run</h2>

<p><strong>14. Two failures is a ticket defect.</strong> A ticket whose
implementation fails twice is stopped rather than retried a third time, with a
specific diagnosis: the code may not be the problem. The recommendation is a
rewrite of the ticket itself, which then has to clear gate 5. Note what this
refuses to do — it does not keep throwing attempts at a contract that can't be
satisfied, and it does not let the contract be quietly reduced until it can.</p>

<p><strong>15. Record validation.</strong> The run's own log is validated before
any timing or summary is reported — every started stage closed exactly once,
every line parsing, every line timestamped. If it doesn't validate, the unclosed
stages are named and <strong>no numbers are reported at all.</strong> This gate
exists because of a specific past failure: a predecessor system wrote a partial
record that looked exactly like a complete one, passed every check that existed,
and fed its numbers downstream as though whole. A broken record must not be able
to produce a plausible-looking summary.</p>

<p><strong>16. The human gates.</strong> Two stage boundaries end in a report and
a question rather than a handoff: <strong>G-design</strong> (here is the PRD and
charter — proceed to ticket breakdown?) and <strong>G-tickets</strong> (here is
the adversary-approved tree — proceed?). Nothing an agent does gets past these;
they're where a person decides that what was understood is what was meant. Once
tickets exist, <code>/slopstop:run</code> is autonomous by default — a single
<code>--interactive</code> flag turns every judgment gate below into a question if
you'd rather be asked.</p>

<h2>What happens when one fires</h2>

<p>A gate stops <em>that ticket</em>, not the run. Its branch and its working
notes are preserved exactly as they were, every other ticket keeps going, and the
whole stopped set is reported together at the end with what each one needs from
you. This matters more than it sounds: a run that parks itself on the first
problem is the failure mode autonomy has to avoid, and a run that reports twelve
successes while silently abandoning the thirteenth is worse.</p>

<p>And nothing is ever resolved by weakening the thing that raised it. No deleted
test, no narrowed assertion, no skip, no edited frozen expectation. If the
ticket's own expectation turns out to be wrong, that's a decision for a person
and a rewrite under gate 5 — not an edit.</p>

<h2>The pattern underneath</h2>

<p>Look across all sixteen and a shape falls out. The gates guarding
<em>test integrity</em> specifically — tamper, slop, vacuity — are mechanical,
and they have no permissive setting at all: not in autonomous mode, not in
interactive mode, not for a two-line change. That was the hardest thing to give
up, and the argument for giving it up is simple: any switch whose permissive value
is the only one an unattended run can use has disabled that gate for exactly the
agents it exists to police, and then reports clean. A gate that waves through for
its own subject matter is worse than no gate, because it manufactures
confidence.</p>

<p>Every other gate can be overruled by a person who has read the finding, and
the decision is written down where it happened. The pipeline does not trust an
agent's judgment about whether <em>its own</em> tests are still honest. It trusts
a fresh reader's judgment, or a human's, or an exit status that can't be argued
with — and it records which one made the call, every time.</p>

</div>
</div>
