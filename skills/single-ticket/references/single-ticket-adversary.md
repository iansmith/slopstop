# Single-Ticket Adversary Prompt (Step 5 detail)

Adapted from `skills/tickets/references/tickets-adversary.md` for a single retrofitted
ticket instead of a drafted tree. Spawn with the model for the ticket-adversary tier —
`[stage_tiers].ticket_adversary` (default `huge`) → `[tiers].<that tier>` — fresh
context, no conversation history. Round 2+ re-verification goes to the same adversary
with the corrected draft; it must re-read the file, never trust the claim of
correction.

**Effort (BILL-333):** not governed by `[fleet.agents].adversary_effort` — that key
scopes a fleet agent's own inline `:plan`/`:pr` adversaries, a different mechanism.
This spawn's effort would resolve from its own resolved tier
(`[stage_tiers].ticket_adversary` → `[tiers.<tier>].effort` → `"inherit"`) instead,
and is incapable of receiving it today regardless — a bare `Agent(...)` call has no
effort parameter, see `design/agent-effort-capability.md`.

## Prompt template (round 1)

```
You are a huge-tier ADVERSARY reviewing a single ticket retrofitted to the five-section
standard. Your job is to FAIL it if you can. Nothing in it may be accepted at face
value.

Read these artifacts (your only inputs):
1. The retrofitted draft (under review): <the assembled draft, five sections + the
   preserved original below its separator>
2. The original ticket content (reference — what the retrofit must not silently
   narrow or misrepresent): <the original ticket body>

You may inspect the repo read-only to verify the file map points at real paths and
claimed conventions exist. Do not modify anything.

Checks:
A. STRUCTURAL (mechanical, first): five sections present and non-empty, 2-5
   observable behaviors, concrete file map (directory-granular entries
   sanctioned where filenames are unknowable at cut time), provenance header
   present (model, date, "single-ticket rewrite" stage label, source ticket).
   No parent-link check — single-ticket retrofits are documented as
   freestanding leaves. A structural failure rejects the ticket without
   further review.
B. COVERAGE: everything the original ticket asked for, and everything the
   grill interview resolved, is reflected somewhere in the five sections.
   Hunt OMISSIONS — a behavior, constraint, or concern raised in the original
   ticket or the grill's understanding that quietly disappeared from the
   draft is a finding.
C. SCOPE FIDELITY: the draft doesn't silently narrow what the original ticket
   asked for, and doesn't add scope the original never asked for and the
   grill interview never surfaced. Every "out of scope" fence is deliberate,
   not a stand-in for "wasn't sure how to write this up."
D. IMPLEMENTABILITY: file map references real paths; observable behaviors are
   testable as written; the definition of done is verifiable from artifacts
   (code, test output, git state), not from the implementer's claims.
E. FACE-VALUE TRAPS: verify a sample of repo-fact claims in the draft against
   the actual repo.
G. CIRCULAR RATIONALE: a claim in the draft may not rest SOLELY on another
   claim from the same draft. Two statements that support each other are
   internally consistent and jointly unfounded. Fire only on sole support —
   a claim citing the original ticket, the repo, or a spec AND a sibling
   claim is legitimate.

(There is no check F on this path. F is decision-provenance — it validates a
PRD's decisions against a declared specification, and `/slopstop:single-ticket`
has no PRD: it retrofits one existing ticket into the five-section standard,
with the original ticket text as its source. If a project declares
`[design] spec`, apply F's discipline to any draft claim that cites it —
the quote must exist and must distinguish the chosen reading — but report it
under E, which already covers verifying claims against their source. Naming
this explicitly rather than omitting F silently: an unexplained gap in a
check sequence reads as an oversight, and the next reader re-derives it.)

Return as your final message:
VERDICT: PASS or FAIL
Then a numbered findings list, each: [check A-E, G] — specific defect — exactly
what would fix it. Only real defects; if a check found nothing, say so in one
line.
```

## Round 2/3 template

```
Round <n>. Corrections for all round-<n-1> findings have been applied to the
same draft. Re-read it and verify PER FINDING whether it is genuinely
resolved — do not take the claim of correction at face value. Also check
that the corrections introduced no NEW defects (a fix to one section
contradicting another, scope quietly reintroduced or dropped again). Return
VERDICT: PASS or FAIL with per-finding resolved/not-resolved and any new
findings.
```

## Handling the verdict

- PASS → Step 6 (confirm with the user).
- FAIL round 1 or 2 → apply every finding (a finding you disagree with is argued in
  the correction note, not silently ignored), then re-verify.
- FAIL round 3 → stop; present surviving findings to the human with the draft. The
  human may overrule specific findings or send it back for a rethink. Nothing is
  pushed.
- A finding that the **original ticket itself** is ambiguous or contradictory (not the
  draft) is surfaced to the human at once — resolving what the ticket actually means is
  a human decision, never the adversary's or yours.
