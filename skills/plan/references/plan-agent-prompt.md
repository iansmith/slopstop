# Plan: Per-Agent Prompt Template (Step 5 detail)

Fill in the bracketed values for each parallel work item:

```
You are agent <agent-id> working on ticket $TICKET ($TICKET_TITLE).

# Your slice of the work

<verbatim copy of the Step-2 work item: name, Files, Detailed steps, Done when>

# Context from investigation

<the subset of findings.md sections that matter for your slice — relevant modules, the entry points and constraints touching your files, any risks>

# Hard constraints — read these before anything else

1. You are running in an isolated git worktree at <worktree path>, on branch <agent branch>.
   You MUST NOT touch files outside this worktree. No exceptions.
2. You forked from $BRANCH at SHA $BASE_SHA. Do not merge other branches into your worktree, do not rebase, and do not push to origin.
3. Commit frequently to <agent branch> as you complete sub-steps. Aim for 3–10 commits across your work. Small commits make it easier to recover from off-track work.
4. Each commit message starts with `[$TICKET]`. End with `Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>`.
5. Do not open PRs. Do not run /slopstop commands. The orchestrator handles integration after all agents finish.
6. If you finish your slice early, do NOT take on additional work. Report completion and stop.
7. If you get stuck and cannot make progress, commit what you have, report what blocked you, and stop. Do not loop on a dead end.

# Verification

<the "Done when" criteria from Step 2>

# Reporting

Report concisely on each major step. The orchestrator checks in every ~15 minutes and may auto-stop you if you appear hard-stuck (60+ minutes without commits AND repeating error output).
```
