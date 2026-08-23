---
description: Interview the user relentlessly about a plan or design until reaching shared understanding, resolving each branch of the decision tree. Use /slopstop:grill to stress-test a plan — typically before breaking it into tickets.
---

# /slopstop:grill

<!-- Provenance: adapted 2026-07-09 from the standalone `grill-me` skill so slopstop
     ships with no external skill dependency. Keep divergences deliberate. -->

Interview the user relentlessly about every aspect of the plan in `$ARGUMENTS` until
you reach a shared understanding. If `$ARGUMENTS` is empty, ask for the plan (or a
brain-dump of it) first.

## Arguments

If `$ARGUMENTS` begins with the literal prefix `--autonomous `, strip it and run in
**autonomous mode** (below); the rest of `$ARGUMENTS` is the plan, exactly as if the flag
were absent. No prefix → standard mode, fully interactive, as this skill has always run.

This skill takes the flag directly rather than reading `[design] autonomous` itself —
grill is invoked inline, has no access to `.project-conf.toml`, and a caller other than
`:design` may invoke it someday; a self-contained flag keeps it callable on its own.
`:design` resolves the config key and passes the flag through (`design/SKILL.md` Step 2).

## How to grill

- Walk down each branch of the design tree, resolving dependencies between decisions
  one-by-one — settle the decisions other decisions hang off before descending.
- Ask the questions **one at a time**. Never batch a questionnaire.
- For each question, work out your **recommended answer** and the reasoning for it
  first — before deciding, in autonomous mode, whether there's anyone to ask.
- If a question can be answered by exploring the codebase, **explore the codebase
  instead of asking**.
- Record each resolved decision as you go, tagged as below; when every branch is
  resolved, close with a consolidated summary of the shared understanding — this is the
  raw material for a PRD.

## Standard mode (no `--autonomous`)

Present each question using the `AskUserQuestion` tool. For each question:

1. Work out your recommended answer, 1–3 plausible alternatives, and the reasoning for
   each — before calling the tool.
2. Call `AskUserQuestion` with **one question** per call (never batch). The recommended
   answer is the **first option** with `(Recommended)` appended to its label. Each
   option's `description` carries the reasoning for that choice — this is where the
   argued position lives, not in surrounding prose. Use a short `header` (the decision
   area, e.g. `"Auth method"`, `"Storage"`, `"API style"`).
3. The tool automatically offers "Other" for freeform input, so 2–4 options is the right
   range — the recommendation plus 1–3 alternatives.
4. The user's selection (or their "Other" text) is the resolved answer. Tag it `HUMAN`.

**Do not print the question as conversational text and then also call `AskUserQuestion`.**
The tool *is* the question. State any necessary context (what depends on this decision,
what you found in the codebase) in a sentence or two before the call, but the
recommendation and alternatives live in the options, not in a paragraph the user has to
parse before clicking.

**A decision you resolved by exploring the codebase is tagged `AUTO`, in this mode too.**
No `AskUserQuestion` call — there is nobody to ask. The rule above tells you to explore
rather than ask when the codebase can answer, so standard mode produces these by
design — and nobody was asked, which is precisely what `AUTO` means. Tagging them `HUMAN`
would claim a review that never happened, and it is the `UNDERDETERMINED` + `AUTO` set
that `:design` Step 3 singles out as the weakest basis anything can rest on. This is the
one thing standard mode's tagging used to have no answer for (BILL-609).

## Autonomous mode (`--autonomous`)

- **You reached a recommended answer** — the ordinary case; the rule above already
  produces one, argued and reasoned, for nearly every question. **Resolve the branch to
  it. Do not ask, do not wait for a reply.** Record the answer and its reasoning exactly
  as you would have presented them to a user, tagged `AUTO`.
- **You genuinely could not reach one** — the branch turns on information only the user
  has (a business decision, a preference with no principled default, something the
  codebase and the topic are both silent on): say so explicitly, ask, and wait for the
  real reply. Tag it `HUMAN`. This is the only case autonomous mode still interviews
  anyone for.

**The bar is genuine absence of a recommendation, not difficulty.** A hard question with
an argued best answer is still `AUTO` — this mode skips *confirming* positions you can
actually defend, not the thinking that produces them. If you cannot state why your answer
beats the alternative you didn't pick, that is the real "no recommendation" case, not a
recommendation you're being lazy about arguing for. Padding the `HUMAN` count by declining
to argue is not what this mode is for.

## Recording a decision

Every resolved decision, either mode, carries the same shape — the caller (`:design` Step
3) reads `Resolution` alongside its own SPEC/DERIVED/UNDERDETERMINED classification, and
the two are independent: grounded-in-spec and reviewed-by-a-human answer different
questions about the same decision.

```
Decision: <the question or branch, in one line>
Answer: <the resolved answer>
Reasoning: <why — the argued recommendation, or a summary of the human's stated reason>
Resolution: AUTO | HUMAN
```

**`AUTO` means no human was asked; `HUMAN` means one answered.** Both an argued
recommendation you resolved yourself and an answer you found in the codebase are `AUTO`, in
either mode. There is deliberately no third value: the distinction that matters downstream
is whether a person weighed in, and a two-value tag cannot drift out of step with a third.
Say in the decision's `Reasoning` which it was — a recommendation or a codebase finding —
so the basis is still legible.

## When it ends

The grill is done when there are no unresolved branches left: every open question is
resolved — `AUTO` from a recommendation, `HUMAN` from a real reply, answered by the
codebase, or explicitly deferred with an owner. Do not stop early because the
conversation is long, and in autonomous mode, do not let "no one is waiting on an
answer" become "no one worked one out" — every `AUTO` decision still needs its
reasoning recorded, not just its answer.

Close with a consolidated summary reporting the count by resolution (`<n> AUTO, <n>
HUMAN`) alongside the existing shared-understanding summary — this is what `:design`
Step 5 reports at gate G-design.
