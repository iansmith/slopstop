# The slopstop workflow — one ticket, start to finish

> **This page describes the loop for a *single ticket*: one person, one branch, one PR.** It is
> not how a fleet works. slopstop's multi-agent side — `/slopstop:design` → `/slopstop:tickets` →
> `/slopstop:run`, which decomposes a feature into a ticket tree and drives parallel headless
> agents against it — is a different shape with different gates, described in
> [the annotated walkthrough](walkthrough/) and in [`design/slopstop-process.md`](design/slopstop-process.md).
> The commands below are what each *individual* fleet agent runs internally, one ticket each, so
> understanding this loop is the prerequisite for understanding that one.

The slash commands are the loop, from picking up a ticket to shipping it. Each ticket gets its own
plan, investigation notes, and session log on disk, so a fresh Claude Code session can resume
exactly where you left off, and that record syncs back to the ticket on close.

Full per-command reference: [COMMANDS.md](COMMANDS.md).

---

## The loop

```
   /slopstop:start <KEY>
            │       fetch ticket → transition to In Progress → create <type>/<KEY>
            │       branch → seed task_plan.md / findings.md / progress.md
            ▼
   /slopstop:plan [constraint]      ←─── optional but recommended
            │  ┌─────────────────────────────────────────────────┐
            │  │  Step 0   red tests for the DESIRED behavior,   │
            │  │           committed and frozen before any impl  │
            │  │  Step 1   investigate the codebase              │
            │  │  Step 2   Definition of Done + technical plan   │
            │  │  Step 3   decide: serial or parallel?           │
            │  │  Step 4-10  optional agent fanout in worktrees, │
            │  │           monitor, integrate (each step         │
            │  │           confirmed with you)                   │
            │  └─────────────────────────────────────────────────┘
            ▼
        (work happens)
            │
            │   ┌─ /slopstop:update ──┐   mid-session checkpoint to progress.md;
            │ ←─┤  (repeat as needed) │   local only, never calls the ticket system
            │   └─────────────────────┘
            │
            │   ┌─ /slopstop:update-ticket ─┐   same, but also pushes task_plan +
            │ ←─┤  (optional)               │   findings up to the ticket
            │   └───────────────────────────┘
            ▼
   /slopstop:pr
            │  ┌──────────────────────────────────────────────────┐
            │  │  simplify → tests → commit → push → open PR →    │
            │  │  review (CodeRabbit, Greptile, or Claude —       │
            │  │  per [pr_review] backend)                        │
            │  │  loops on 🔴/🟡 findings until clean             │
            │  └──────────────────────────────────────────────────┘
            ▼
   /slopstop:merge
            │  ┌──────────────────────────────────────────────────┐
            │  │  1  merge the PR (MCP preferred, gh fallback)    │
            │  │  2  advance the ticket ONE state (In Progress →  │
            │  │     In Review, not straight to Done)             │
            │  │  3  update tracking files                        │
            │  │  4  push docs to the ticket (task_plan as        │
            │  │     description, DoD-confirmation + findings     │
            │  │     as comments)                                 │
            │  │  5  delete the branch, propagate to all remotes  │
            │  │  6  if the ticket is now TERMINAL: chain         │
            │  │     :archive automatically                       │
            │  └──────────────────────────────────────────────────┘
            ▼
   ┌────────────────────────────────────────────┐
   │ ticket landed in a terminal (Done) state?  │
   └────────────────────────────────────────────┘
        │ yes                          │ no — e.g. "In Review"
        ▼                              ▼
   :archive already ran           (wait for QA / review to
   as part of :merge               move the ticket, then:)
        │                              │
        │                         /slopstop:archive
        │                              │  move the tracking dir to
        │                              │  ticket-archive/ — local only
        └──────────────┬───────────────┘
                       ▼
                     done
```

---

## Two corrections worth flagging if you knew the old diagram

**`:archive` no longer pushes documentation.** It is now purely a local file move — tracking dir
from `ticket-active/` to `ticket-archive/`. The documentation push (task plan → ticket
description, DoD-confirmation comment, findings comment) happens in **`:merge` Step 7**, before
archive runs. Earlier versions of this diagram credited the push to `:archive`.

**There is no `/slopstop:pause`.** It appears in older documentation and in draft design notes,
but no such skill ships. Use `/slopstop:update` to checkpoint before you walk away;
`/slopstop:start <KEY>` resumes and prints where you left off.

---

## Properties of the loop that matter

- **Per-ticket context isolation.** Each ticket gets its own `task_plan.md`, `findings.md`, and
  `progress.md` under `.slopstop/ticket-active/<TICKET>/`. When you are on `MAZ-26`, only
  `MAZ-26`'s notes load — not the dozen others you have touched recently.
- **Parallel project work.** Multiple active tickets across different projects are each isolated
  in their own directory. Different Claude sessions in different repos never conflict.
- **Tests are frozen before implementation.** `:plan` Step 0 commits failing tests for what the
  *ticket* requires — not for what the code already does — and only tests observed failing may
  enter that commit. Everything downstream is measured against that baseline, including the
  tamper check a fleet run applies to its agents.
- **The ticket advances one state at a time, with confirmation.** `:merge` computes the next state
  and shows it to you in a single prompt before doing anything. Nothing marks a ticket Done that
  was not already terminal on the ticket system.
- **A durable record goes back to the ticket.** The final task plan becomes the ticket's
  description, a timestamped DoD-confirmation comment walks each Definition-of-Done item with
  evidence, and findings become a separate comment. The ticket becomes a record of what was
  actually done, not just a title and a merged diff.
- **`progress.md` never leaves your machine.** It is a per-session diary — too noisy for the
  durable record. The commit history, the findings comment, and the description carry the story.

---

## Where to go next

- **[COMMANDS.md](COMMANDS.md)** — every command, what it does, and what it refuses to do.
- **[QUICKSTART.md](QUICKSTART.md)** — this loop run once, by hand, on a real bug, in about 15 minutes.
- **[walkthrough/](walkthrough/)** — the other shape: one feature, nine tickets, a fleet of
  parallel agents, read minute by minute from a real transcript.
- **[CONFIG.md](CONFIG.md)** — every setting in `.project-conf.toml`.
