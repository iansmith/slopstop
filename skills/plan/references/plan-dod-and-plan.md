# Plan: Definition of Done and Technical Plan (Step 2 detail)

Two documents with two different audiences. The DoD is read by whoever accepts the
work; the Plan is read by whoever executes it, possibly in a cold session.

## 2a. Draft the Definition of Done (client-readable)

Plain language, observable outcomes. Write it **above** `## Original description` in
`task_plan.md`, so it appears at the top of the ticket after `:archive`.

```markdown
## Definition of Done

This ticket will be considered complete when ALL of the following are true and observable:

1. **<plain-language outcome — what changes from the client's perspective>**
   How to verify: <a concrete check the client can do without reading code>

2. **<plain-language outcome>**
   How to verify: <observable check>

If any of these aren't true at delivery, the ticket isn't done.
```

Guidelines: observable outcomes only — no code symbols, test names, or jargon. Each
"How to verify" must be executable by someone who cannot read the code; that is the
test of whether the outcome is really observable. 2–5 items. Reflect any scope dropped
by `$ARGUMENTS`.

## 2b. Draft the technical Plan

Write into `task_plan.md`'s `## Plan` section, replacing or augmenting per the
pre-flight choice. Detailed enough that a separate session can execute items cold.

```markdown
## Plan

**Constraint:** $ARGUMENTS (or "none — full ticket scope")

### Work items

1. <descriptive name>
   - **Files:** <files this item creates, modifies, or deletes>
   - **Depends on:** <ids of items that must complete first, or "none">
   - **Parallel-safe with:** <ids it can run alongside; explain why>
   - **Detailed steps:**
     a. <concrete sub-step>
   - **Done when:** <verification criteria — preferably red tests from Phase 0 turning green>

### Parallelism analysis

- **Items eligible for parallel execution:** <list>
- **Sequential dependencies:** <list>
- **Recommended execution:** <"serial" | "parallel: N agents covering items [list]; serial integration after">
```

**Two items with overlapping files are NOT parallel-safe, even when logically
independent.** `Parallel-safe with` must reflect actual file-level disjointness, not a
judgement about whether the changes "should" conflict. Step 3 reads this field to
decide whether to fan out at all, so an optimistic answer here produces conflicting
worktrees later.
