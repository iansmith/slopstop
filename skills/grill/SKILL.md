---
description: Interview the user relentlessly about a plan or design until reaching shared understanding, resolving each branch of the decision tree. Use /slopstop:grill to stress-test a plan — typically before breaking it into tickets.
disable-model-invocation: true
---

# /slopstop:grill

<!-- Provenance: adapted 2026-07-09 from the standalone `grill-me` skill so slopstop
     ships with no external skill dependency. Keep divergences deliberate. -->

Interview the user relentlessly about every aspect of the plan in `$ARGUMENTS` until
you reach a shared understanding. If `$ARGUMENTS` is empty, ask for the plan (or a
brain-dump of it) first.

## How to grill

- Walk down each branch of the design tree, resolving dependencies between decisions
  one-by-one — settle the decisions other decisions hang off before descending.
- Ask the questions **one at a time**. Never batch a questionnaire.
- For each question, provide your **recommended answer** and the reasoning for it, so
  the user is choosing between argued positions rather than facing a blank prompt.
- If a question can be answered by exploring the codebase, **explore the codebase
  instead of asking**.
- Record each resolved decision as you go; when every branch is resolved, close with a
  consolidated summary of the shared understanding — this is the raw material for a
  PRD.

## When it ends

The grill is done when there are no unresolved branches left: every open question is
either answered by the user, answered by the codebase, or explicitly deferred with an
owner. Do not stop early because the conversation is long.
