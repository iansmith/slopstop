---
layout: article
title: The Gates
subtitle: Every place slopstop's pipeline refuses to continue, and what an agent is given instead of an override
---
<div class="gates-layout wide-layout">
<div class="gates-prose">

<p>slopstop's pipeline is not a straight line from ticket to merge. It's a chain
of checkpoints, and at several of them the process simply stops — not "warns
and moves on," stops — until something specific resolves it. Some of those
checkpoints an agent can talk its way through with a logged reason. A couple
of them, deliberately, it cannot talk its way through at all.</p>

<p>This page is the list. Fourteen gates, grouped by where in the pipeline
they sit, each with what it blocks and what an agent gets instead of a
bypass. Terms a newcomer to slopstop might not know are marked in bold, with
a short note on the side explaining them.</p>

<h2>Design &amp; tickets — before any code exists</h2>

<p><strong>Tier gate.</strong> <code>/slopstop:design</code>,
<code>/slopstop:tickets</code>, and <code>/slopstop:run</code> each open by
checking that the session's model actually matches the <strong>tier</strong><span class="sidenote" role="note"><span class="sidenote-entry"><strong>tier</strong> — a fixed mapping in the project's config from a role (huge / large / medium / small) to a specific model. Higher tiers do adversarial review; lower tiers do the bulk implementation work.</span></span> the
stage requires. If it doesn't, that's fatal — switch and retry, no
mitigation softens a genuine mismatch. But a session's self-reported model
name is not always trustworthy (a mid-session <code>/model</code> switch can
leave the environment still reporting the old family), so when the check
can't verify itself, a human can attest the real model instead of the gate
blocking forever on a false negative.</p>

<p><strong>Ticket-tree adversary.</strong> Before a single ticket is created,
a fresh, huge-tier model reads the drafted tree against the
<strong>PRD</strong> and <strong>charter</strong> with one job: fail it if
it can. It checks structure, PRD coverage, scope fidelity, whether
<strong>file maps</strong><span class="sidenote" role="note"><span class="sidenote-entry"><strong>PRD</strong> — Product Requirements Document, the reference spec every ticket in the tree is checked against.</span><span class="sidenote-entry"><strong>charter</strong> — a short list of binding implementation rules for this particular piece of work, layered on top of the PRD (e.g. "never import this library," "this behavior must stay unchanged").</span><span class="sidenote-entry"><strong>file map</strong> — the specific files a ticket declares it's allowed to touch, agreed before any code is written.</span></span> point at real paths, and spot-checks factual claims against
the actual repo. Findings get applied and the same adversary re-reads the
corrected draft — up to three rounds. Still failing on round three doesn't
get silently shipped; it goes to a human with the surviving findings
attached.</p>

<h2>Inside an agent's own session</h2>

<p>These run <em>inside</em> the implementing agent's own
<code>/slopstop:plan</code> and <code>/slopstop:pr</code> invocations — the
agent polices itself before anything reaches the
<strong>orchestrator</strong><span class="sidenote" role="note"><span class="sidenote-entry"><strong>orchestrator</strong> — the top-level agent running <code>/slopstop:run</code>. It launches, monitors, and integrates the fleet, but by its own rules, never implements a ticket itself.</span></span>.</p>

<p><strong>Adversary gap finder.</strong> Before <strong>Phase 0</strong><span class="sidenote" role="note"><span class="sidenote-entry"><strong>Phase 0</strong> — the required first commit on any ticket's branch: the tests the ticket needs, committed and shown failing, before a single line of implementation exists.</span></span> freezes, a
fresh adversary attacks the just-written test suite across six angles —
boundary omissions, uncovered error paths, untested state interactions,
spec drift, false negatives, coverage asymmetry. Gaps become new failing
tests, verified red, before the freeze. This one doesn't block so much as
strengthen: it's the last chance to add coverage before the tests become
untouchable.</p>

<p><strong>Pre-PR health gate.</strong> The full suite has to be green — or
only failing on the ticket's own not-yet-implemented Phase 0 tests — before
a PR opens. A real regression is a hard stop by default. A
<strong>benchmark-mode</strong><span class="sidenote" role="note"><span class="sidenote-entry"><strong>benchmark-mode</strong> — a config setting (<code>benchmark-continue</code>) used for evaluation runs. It lets a soft gate proceed past a failure instead of blocking, but only by writing a permanent, logged override record.</span></span> config value lets it proceed anyway, but only with a
permanent, logged override record and a warning baked into the PR body.</p>

<p><strong>Cyclomatic-complexity gate.</strong> Any function touched in the
diff that crosses the <strong>cyclomatic complexity</strong><span class="sidenote" role="note"><span class="sidenote-entry"><strong>cyclomatic complexity</strong> — a standard metric counting the independent paths through a function. Higher numbers mean more branching, and usually harder-to-test code.</span></span> threshold is
rejected the same way — hard stop by default, same logged-override escape
hatch in benchmark mode.</p>

<p><strong>Red-test tamper gate.</strong> This is the one with no escape
hatch. Every file that entered the Phase 0 commit is diffed against
<strong>HEAD</strong>, mechanically — no judgment call, just a diff. A
deleted test, a skipped test, or an assertion whose expected value quietly
changed all trip it, and <strong>there is no override value for this
gate.</strong> What the agent gets instead isn't a bypass — it's a different
exit entirely: if it genuinely believes the <em>ticket's</em> stated
expectation is wrong, it can halt with
<code>TICKET UNDERSPECIFIED</code><span class="sidenote" role="note"><span class="sidenote-entry"><strong>HEAD</strong> — git's name for the current tip of the branch being worked on.</span><span class="sidenote-entry"><strong><code>TICKET UNDERSPECIFIED</code></strong> — the one sanctioned way to stop at the tamper gate: a clean halt an agent can take when it believes the ticket's own stated expectation is wrong, not the code. Costs no attempt.</span></span>, cite its evidence, and stop clean. That
costs nothing — no attempt spent — and sends the ticket back for a rewrite.
What it can never do is edit the test itself and keep going.</p>

<p><strong>Slop-detection gate.</strong> A separate pass scans for the
softer test-writing anti-patterns — rewriting a test to pass, inverting an
expectation, tautological assertions, scope creep, swallowed exceptions.
These get an interactive override with a reason, logged to a record kept
deliberately distinct from the tamper gate's — so anyone reading the audit
trail later can tell "someone overrode a style warning" apart from "someone
unfroze a test," which is a much bigger deal.</p>

<h2>Fleet-level, across the whole run</h2>

<p><code>/slopstop:run</code> launches a <strong>fleet</strong><span class="sidenote" role="note"><span class="sidenote-entry"><strong>fleet</strong> — the set of agents <code>/slopstop:run</code> launches in parallel, one per ticket, each working its own isolated branch.</span></span> of these
agents in parallel and layers its own gates on top, checking their work from
<em>outside</em> the session that produced it.</p>

<p><strong>Branch-type resolution.</strong> If a ticket carries no label or
title pattern indicating what kind of <strong>branch-type</strong><span class="sidenote" role="note"><span class="sidenote-entry"><strong>branch-type</strong> — the prefix on a ticket's branch name (<code>feat/</code>, <code>fix/</code>, <code>chore/</code>, …), inferred from the ticket's label or title. slopstop refuses to guess this rather than risk cutting the wrong kind of branch.</span></span> it needs, and no
config default exists, the orchestrator refuses to guess. A human adds a
label or sets the config; a ticket that stays unresolvable is marked
<code>unrun</code> — no attempt spent, and it doesn't block anything that
doesn't depend on it.</p>

<p><strong>Handoff verification.</strong> When an agent reports a ticket
done, nothing it claims is trusted. Two fresh subagents — a
<strong>requirements adversary</strong> and a <strong>code
reviewer</strong><span class="sidenote" role="note"><span class="sidenote-entry"><strong>requirements adversary</strong> — a fresh subagent whose only job is checking a finished ticket against its stated Definition of Done and behaviors — hunting for gaps, not code quality.</span><span class="sidenote-entry"><strong>code reviewer</strong> — a second fresh subagent judging the same diff for implementation quality: correctness, style, dead code, removed safeguards.</span></span> — independently re-read the actual diff from
scratch. Both have to pass before the ticket is blessed. A failure relaunches
the same agent in the same preserved <strong>worktree</strong><span class="sidenote" role="note"><span class="sidenote-entry"><strong>worktree</strong> — an isolated git checkout, one per fleet agent, so parallel agents never share a working directory or step on each other's uncommitted changes.</span></span> with the
specific findings quoted back at it — a fix-forward retry, one attempt
spent, not a restart from zero.</p>

<p><strong>Rewrite delta check.</strong> When a ticket needs its contract
rewritten — most often because its implementing agent hit the tamper gate
for a legitimate reason — a huge-tier check compares the old and new ticket
text against the PRD and charter before any relaunch is allowed. It has to
say the rewrite added specificity. If it instead subtracted scope — quietly
made the ticket easier to pass — that's rejected outright, and the scope
gets restored or taken to a human. Amending the PRD itself is never
something the pipeline does on its own authority.</p>

<p><strong>Budget exhaustion.</strong> Two failed <strong>attempts</strong>
on a ticket trigger an automatic diagnosis before anything reaches a human:
was this a defect in the ticket (rewrite it, a new
<strong>version</strong>) or a capability gap (try a stronger model, an
<strong>escalation</strong>)?<span class="sidenote" role="note"><span class="sidenote-entry"><strong>attempts</strong> — how many times a single ticket version has been (re)launched after a kill or a failed review.</span><span class="sidenote-entry"><strong>version</strong> — a full rewrite of a ticket's contract, tried when the problem turns out to be the ticket itself, not the implementation.</span><span class="sidenote-entry"><strong>escalation</strong> — the one attempt per ticket allowed to run on a stronger model, tried when the problem looks like a capability gap rather than a bad ticket.</span></span> Most stuck tickets get resolved right there. Only
once attempts, rewrite versions, and model escalations are all exhausted
does it become a human decision — and even then, every ticket that doesn't
depend on the stuck one keeps running while it waits.</p>

<p><strong>Drift check.</strong> When every <strong>leaf</strong> under an
<strong>umbrella ticket</strong><span class="sidenote" role="note"><span class="sidenote-entry"><strong>umbrella ticket</strong> — a parent ticket describing a whole feature. It's never implemented directly — it exists to group and track the leaves under it.</span><span class="sidenote-entry"><strong>leaf</strong> — one of the actual implementable, single-branch, single-PR tickets under an umbrella. This is the unit a fleet agent works.</span></span> has individually passed its own handoff
verification, a large-tier check looks at the <em>landed whole</em> against
the PRD and charter — because leaves can each be individually correct and
still not add up to what was asked for. Findings become fix-forward tickets
run through the identical pipeline, not a full re-run.</p>

<p><strong>Final-report adversary.</strong> Before a human ever sees the
run's own summary of itself, a huge-tier adversary tries to prove that
summary wrong or incomplete — working from ground truth (re-running the
suite, reading actual ticket and PR state), never from the report's own
claims. Up to three rounds of fix-and-reverify. Still failing after three,
the report reaches the human with the surviving findings attached — never a
version cleaned up to look better than it is.</p>

<p><strong>G-final.</strong> The last gate has no mitigation, by design. A
human has to explicitly accept the run before any cleanup happens. Nothing
an agent does gets it past this one.</p>

<h2>The pattern underneath</h2>

<p>Look across all fourteen and a shape falls out: the gates guarding
<em>test integrity</em> specifically — the tamper gate, and to a lesser
extent the slop gate — give an agent a legitimate way to stop, but never a
legitimate way to edit past them. Every other gate has an override, and
every override leaves a permanent, machine-readable record of who authorized
what and why. The pipeline doesn't trust an agent's judgment about whether
<em>its own</em> tests are still honest. It trusts a fresh adversary's
judgment, or a human's, or a mechanical diff that can't be argued with — and
it writes down which one made the call, every time.</p>

</div>
</div>
