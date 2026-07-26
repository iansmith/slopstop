---
layout: default
title: slopstop
author: iansmith
---

# slopstop

**Ticket-anchored AI development for Linear, JIRA, and GitHub Issues, built on one
idea: stop slop before it goes in, instead of reviewing it out afterwards.**

## [Prevention, Not Recovery](what_is_slopstop.md)

The argument, at length: why prevention beats recovery, what the pipeline actually
does at each stage, and what it looks like when it catches something.

## Elsewhere

- [Source and docs](https://github.com/iansmith/slopstop) — the repository
- [The annotated walkthrough](https://github.com/iansmith/slopstop/tree/master/walkthrough) — one real multi-agent run, read start to finish
- [The full command list](https://github.com/iansmith/slopstop/blob/master/COMMANDS.md)

## Install

In Claude Code:

```
/plugin marketplace add iansmith/slopstop
/plugin install slopstop@slopstop
```

Commands are then available as `/slopstop:<name>`.
