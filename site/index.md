---
layout: article
title: slopstop
---

**Ticket-anchored AI development for Linear, JIRA, and GitHub Issues, built on one
idea: stop slop before it goes in, instead of reviewing it out afterwards.**

## [How slopstop works](how_slopstop_works.md)

The pipeline at a glance: design interview, ticket tree with adversaries,
multi-agent implementation, and verification — what each stage does and where
human judgment fits in.

## [Prevention, Not Recovery](what_is_slopstop.md)

The argument, at length: why prevention beats recovery, what the pipeline actually
does at each stage, and what it looks like when it catches something.

## [What slopstop produces](report.md)

The measurement: 3,888 production lines in four days across four repositories, the
rate that implies, and an honest comparison against what a strong engineer
delivers — including what would make the comparison wrong.

## [The Gates](gates.md)

Every point where the pipeline refuses to continue, grouped by stage — and what
an agent is given instead of an override at each one.

## Elsewhere

- [Source and docs](https://github.com/iansmith/slopstop) — the repository
- [The annotated walkthrough](walkthrough/index.md) — one real multi-agent run, read start to finish
- [The full command list](https://github.com/iansmith/slopstop/blob/master/COMMANDS.md)

## Install

In Claude Code:

```
/plugin marketplace add iansmith/slopstop
/plugin install slopstop@slopstop
```

Commands are then available as `/slopstop:<name>`.
