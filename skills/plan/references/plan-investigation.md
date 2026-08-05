# Plan: Investigation (Step 1 detail)

Goal: map the codebase relative to the ticket, scoped by `$ARGUMENTS`. Output is an
appended section in `findings.md`.

## 1a. Read existing context

- `task_plan.md`'s `## Original description (snapshot at start)` section.
- `findings.md` — any prior investigation. Read it, but don't duplicate it.
- (Optional) Re-fetch the ticket from Linear/JIRA/GitHub for the current description,
  if it may have been edited since `:start`.

## 1b. Apply the constraint

If `$ARGUMENTS` is non-empty it is a **hard scope**: excluded areas MUST NOT be
investigated. Note the constraint in the findings header, so a later reader can tell
an unexplored area from an absent one.

## 1c. Map the relevant code

If `--inline` was passed **or** `Explore` is unavailable: use `Grep`/`Glob`/`Read`
directly against the five questions.

Otherwise use the `Explore` subagent for the heavy lifting — it keeps the
orchestrator's context clean:

```
Agent(subagent_type: "Explore", description: "Investigate $TICKET", prompt: <template>)
```

The full Explore prompt template (the 5-question investigation format, scoped to the
ticket plus constraint):
→ Read `~/.claude/commands/slopstop-plan-refs/plan-explore-prompt.md`

(Effort is not a parameter on the `Agent(...)` call — it comes from the subagent
definition's frontmatter, and defaults to the invoking session's effort. See
`design/agent-effort-capability.md`.)

Note `Explore` inherits the main conversation's model as of Claude Code v2.1.198
(capped at Opus on the Claude API) — it no longer always runs Haiku, so this spawn is not
as cheap as its name suggests. #450 gives it a declared tier.

## 1d. Write findings

Append to `findings.md`:

```markdown
## Investigation <UTC timestamp>

**Constraint:** $ARGUMENTS (or "none — full ticket scope")

### Relevant modules
### Entry points
### Dependencies
### Constraints to honor
### Risks
```

`Constraints to honor` and `Risks` are the two a later session actually needs and the
two most often left empty. An empty section is a claim that there are none — if you
did not look, say so rather than leaving it blank.
