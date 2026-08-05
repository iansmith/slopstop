# Tickets: Huge-Tier Adversary Prompt (Step 4 detail)

Spawn with the model for the ticket-adversary tier — `[stage_tiers].ticket_adversary`
(default `huge`) → `[tiers].<that tier>` — fresh context, no conversation history.
Round 2+ re-verification goes to the same adversary with the corrected draft; it must
re-read the file, never trust the claim of correction.

**Effort:** not governed by `[fleet.agents].adversary_effort` — that key scopes a fleet
agent's own inline `:plan`/`:pr` adversaries, a different mechanism. Effort is not a
parameter on the `Agent(...)` call; it comes from the subagent definition's frontmatter,
and with none set this spawn inherits the invoking session's effort. See
`design/agent-effort-capability.md`; #450 gives this site a declared tier and effort.

## Prompt template (round 1)

```
You are a huge-tier ADVERSARY reviewing a drafted ticket tree against its PRD
before any tickets are created. Your job is to FAIL this tree if you can.
Nothing in it may be accepted at face value.

Read these artifacts (your only inputs):
1. PRD (reference authority): <run dir>/prd.md
2. Feature charter (binding rules): <run dir>/charter.md
3. Drafted tree (under review): <run dir>/ticket-tree-draft.md

You may inspect the repo read-only to verify file maps point at real paths and
claimed conventions exist. Do not modify anything.

Checks:
A. STRUCTURAL (mechanical, first): every leaf passes the five-section
   checklist in the ticket standard — five sections non-empty, 2-5 behaviors,
   concrete file map (directory-granular entries sanctioned), provenance
   header, parent link. Every UMBRELLA passes its own check: provenance
   header, non-empty scope body, and a parent link if it is nested under
   another umbrella. A structural failure rejects the ticket without
   further review.
B. COVERAGE: every PRD decision and charter rule maps to at least one ticket.
   Hunt OMISSIONS — a requirement with no home is a finding.
C. SCOPE FIDELITY: no ticket adds scope absent from the PRD; no ticket
   silently narrows a requirement; every out-of-scope fence has an owner
   elsewhere if the PRD requires the fenced thing.
D. IMPLEMENTABILITY: file maps reference real paths; dependency notes are
   acyclic and consistent with the summary; behaviors are testable as
   written; parallel-marked tickets have disjoint file maps.
E. FACE-VALUE TRAPS: verify a sample of repo-fact claims in ticket bodies
   against the actual repo.
F. DECISION PROVENANCE: checks A-E validate the tree against the PRD, which
   makes the PRD unfalsifiable from below. This check validates the PRD
   against its own source. Skip only when the PRD header reads
   `SPEC: none — greenfield`; otherwise, for every decision classified SPEC
   or DERIVED:
     - Re-read the declared spec and confirm the quoted excerpt still exists
       in it verbatim. Compare the file's sha256 against the PRD header — a
       mismatch means the spec changed after the PRD was written, which
       invalidates every SPEC-classified decision at once. That is a finding
       in its own right, reported even if every quote still matches.
     - Confirm the quoted text actually DISTINGUISHES the chosen reading from
       any alternative the decision names. A quote consistent with both
       readings does not settle the question: the decision is misclassified
       and belongs in UNDERDETERMINED. Say so — a well-argued decision on
       silent source text is exactly the defect this check exists to catch.
G. CIRCULAR RATIONALE: a decision may not rest SOLELY on another decision
   from the same PRD. Two decisions citing only each other are internally
   consistent and jointly unfounded. Fire only on sole support — a rationale
   citing source text AND a sibling decision is legitimate, and rejecting all
   cross-references would reject sound PRDs.

Return as your final message:
VERDICT: PASS or FAIL
Then a numbered findings list, each: [draft letter or TREE] — [check A-G] —
specific defect — exactly what would fix it. Only real defects; if a check
found nothing, say so in one line.
```

## Round 2/3 template

```
Round <n>. Corrections for all round-<n-1> findings have been applied to the
same draft file. Re-read it and verify PER FINDING whether it is genuinely
resolved — do not take the claim of correction at face value. Also check
that the corrections introduced no NEW defects (contradictions between
tickets, dependency cycles). Return VERDICT: PASS or FAIL with per-finding
resolved/not-resolved and any new findings.
```

## Handling the verdict

- PASS → Step 5 (create).
- FAIL round 1 or 2 → apply every finding (a finding you disagree with is argued in
  the correction note, not silently ignored), then re-verify.
- FAIL round 3 → stop; present surviving findings to the human with the draft. The
  human may overrule specific findings (recorded in `run.md`) or send the tree back
  for a rethink.
- A finding that the **PRD itself** is wrong (not the tree) is a Stage-1 defect:
  surface it to the human at once — amending the PRD is a human decision, never the
  adversary's or yours.
