# Tickets: Big-Tier Adversary Prompt (Step 4 detail)

Spawn with the model from `[tiers].big`, fresh context, no conversation history.
Round 2+ re-verification goes to the same adversary with the corrected draft; it must
re-read the file, never trust the claim of correction.

## Prompt template (round 1)

```
You are a big-tier ADVERSARY reviewing a drafted ticket tree against its PRD
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
   header, parent link. A structural failure rejects the leaf without
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

Return as your final message:
VERDICT: PASS or FAIL
Then a numbered findings list, each: [draft letter or TREE] — [check A-E] —
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
