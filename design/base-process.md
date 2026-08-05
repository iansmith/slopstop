# base process

> **Framing:** this is the **inner loop** each agent runs to take *one* ticket from
> start through merge and archive. The **slopstop process** — the four-tier pipeline
> that decides what the tickets are and orchestrates fleets of agents running this
> loop — is in [slopstop-process.md](slopstop-process.md).

[slopstop](https://github.com/iansmith/slopstop) is a Claude Code plugin for ticket-anchored development. The thesis: **stop slop before it goes in**, not after. Prevention happens through TDD-first planning, per-ticket scope boundary, and a pre-merge clean-context review pipeline.

## We always follow the base process

Every ticket travels this loop — no shortcuts:

```
/slopstop:start <KEY>         — fetch ticket, create branch, seed tracking files
/slopstop:plan [constraint]   — Phase 0 red tests → investigate → plan → optional agent fanout
  (work happens)
/slopstop:update              — mid-session checkpoint (local only)
/slopstop:pr                  — tests → commit → push → open PR → clean-context review
  (review iteration)
/slopstop:merge               — merge PR → advance ticket one state → propagate → delete branch
/slopstop:archive             — sync docs to ticket → move tracking to archive/
```

Each ticket has its own isolated `task_plan.md`, `findings.md`, `progress.md`. When you're on `KEY-N`, only that ticket's notes load.

## Why the order matters

- **`:plan` before code.** Phase 0 writes failing tests for the *intended* behavior before any implementation. Tests reverse-engineered from existing code pin down bugs and pass vacuously — tests for the desired behavior give the implementation a real target.
- **`:pr` does the review.** After the PR is open, a forked review reads the branch diff, applies what it verifies, and loops until it applies nothing or five rounds. It reads the branch, so committing early costs nothing.
- **`:merge` is not Done.** It advances the ticket one state (e.g. In Progress → In Review). Run `:archive` only after the ticket reaches a terminal state.

## Rules

- **Never skip the process.** If a context switch or broken environment forces work outside the normal flow, that work still follows the emergency exit below.
- **Never `git commit --no-verify`, `git push --force`, `git reset --hard`, or `gh pr merge --admin`.** These bypass safety gates.
- **All commits get a ticket anchor.** Subject: `[KEY] <imperative summary>`. Trailer: `Refs: KEY` (or `Closes: KEY` on the final commit before `:pr`).
- **Run the full test suite before any commit pause.** Never ask "ready to commit?" with unverified code in the working tree — surface actual results.
- **Commit freely.** The review reads the whole branch diff, so nothing escapes by being committed early.

## Emergency exit — work outside the process

If something goes wrong and you must update source outside the normal flow (hotfix, broken environment, context loss):

1. Make the change.
2. Commit. Quality review happens once, at PR time — see `:pr`'s review loop.
3. Run the full test suite and surface the results.
4. Only then commit — with a ticket anchor and the full trailers.

The review gate is at the merge, not at each commit. It is not optional, and no confirmed 🔴 finding is left unfixed.
