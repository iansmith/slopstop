---
layout: article
title: slopstop
---

**Ticket-anchored AI development for Linear, JIRA, and GitHub Issues, built on one
idea: stop slop before it goes in, instead of reviewing it out afterwards.**

Work starts from a ticket, not a prompt. One command drives the whole lifecycle —
investigate, write failing tests for what the ticket requires, prove each fails for
the right reason, attack the plan adversarially, implement, run three mechanical
gates, review in a clean context, open the PR, merge, close. It runs unattended by
default.

During August 2026 it delivered **16,595 lines of production code and
46,123 lines of tests** across five repositories, for **5.5 hours of human
attention** — one interruption every 2.8 hours of compute.

## [What slopstop produces](report.md)

The measurement, from the run logs: the rate, the concurrency, and an honest
comparison against what a strong engineer delivers — including a section on what
would make the comparison wrong.

## [Six defects, six different checks](walkthrough/index.md)

Real findings from real runs, each caught by a different mechanism and quoted from
the log that recorded it. Five of the six would have survived a fully green test
suite. The best answer to "does any of this actually catch anything?"

## [How slopstop works](how_slopstop_works.md)

The pipeline at a glance: design interview, ticket tree with adversaries,
worktree-isolated implementation, and the verification that follows — what each
stage does and where human judgment fits in.

## [Prevention, Not Recovery](what_is_slopstop.md)

The argument, at length: why prevention beats recovery, what the pipeline actually
does at each stage, and what it looks like when it catches something.

## [FAQ: Objections to AI-Written Code](faq.md)

Common objections from senior engineers — hallucinations, circular tests, spaghetti
code, scope creep — answered with the specific mechanism that addresses each one.

## [The Gates](gates.md)

All eighteen points where the pipeline refuses to continue, grouped by stage — and
what an agent is given instead of an override at each one. Three of them nobody can
wave past, including you.

## Elsewhere

- [Source and docs](https://github.com/iansmith/slopstop) — the repository
- [The six commands](commands.md) — when and why to use each
- [Quickstart](quickstart.md) — one real bug from ticket to merged PR

## Install

In Claude Code:

```
/plugin marketplace add iansmith/slopstop
/plugin install slopstop@slopstop
```

Commands are then available as `/slopstop:<name>`.

<div class="install-note">
<strong>Claude Desktop users:</strong> Desktop doesn't support the plugin manager yet.
Use the <a href="https://github.com/iansmith/slopstop#claude-desktop--manual-install">Desktop installer</a>
instead — commands appear as <code>/slopstop-run</code>, <code>/slopstop-design</code>, etc.
(hyphenated, not colon-separated).
</div>
