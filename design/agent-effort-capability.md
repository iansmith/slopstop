# Agent effort capability audit

Which of slopstop's spawn sites can carry a reasoning-effort value, and how.

> **Corrected 2026-08-05.** The original audit (BILL-333) concluded that every in-session
> `Agent(...)` spawn was **"incapable of carrying an effort value in the current
> harness."** That is right about the *call site* and wrong as a conclusion: effort
> travels through the **subagent definition's frontmatter**, not through the call. The
> capability existed the whole time, and the audit told nine sites it did not.
>
> Same shape as BILL-436, where `context: fork` — one line of frontmatter — replaced
> ~600 lines of hand-built orchestration. Twice now the harness has already had what
> slopstop documented as impossible. **Check the frontmatter reference before concluding
> a capability is absent.**

## Verdict summary

| Mechanism | Effort? | How |
|---|---|---|
| `Agent(...)` **call parameters** | **no** | The tool exposes `description`, `isolation`, `model`, `prompt`, `run_in_background`, `subagent_type`. No `effort` parameter — re-confirmed against the live tool schema 2026-08-05. |
| **Subagent definition frontmatter** | **yes** | A subagent file (`.claude/agents/*.md`) supports `effort: low\|medium\|high\|xhigh\|max`. A spawn selects that definition via `subagent_type`, so the effort reaches the agent even though the call never names it. |
| **Skill frontmatter** (forked skills) | **yes** | `skills/review/SKILL.md` carries `model: opus` / `effort: high`. For a `context: fork` skill this is the only channel. |
| Fleet CLI launch (`claude -p --model … --effort …`) | **yes** | `skills/run/SKILL.md` — already wired via `[fleet.agents].effort` / `adversary_effort`. |
| `/code-review` via `Skill({args: "--effort …"})` | **yes** | The invocation threads a literal `--effort` flag. |

## What a spawn gets when nothing sets effort

It **inherits the invoking session's effort**. Precedence:

```
CLAUDE_CODE_EFFORT_LEVEL  >  skill/subagent frontmatter  >  session level  >  model default
```

The model default is `high` on every model that supports effort, except Opus 4.7 which
defaults to `xhigh`. Frontmatter overrides the session level but **not** the environment
variable.

Two consequences worth holding onto:

- An **inherited** effort is a property of whoever launched the session, not of the stage.
  It is not comparable across runs. Anything recording effort must say which it was.
- The effort scale is **calibrated per model** — `high` on Fable is not `high` on Haiku.
  Re-tiering a stage silently changes what its effort level means.

## Why effort cannot be per-project

`[stage_tiers]` lives in `.project-conf.toml` and varies by repo. Subagent frontmatter is
a static file. So the two split:

- **Model** stays per-project: resolve `[stage_tiers].<key>` → `[tiers].<tier>` and pass
  `Agent(model: $RESOLVED, subagent_type: "<role>")`. The per-invocation `model`
  parameter outranks frontmatter.
- **Effort** is fixed per role in the agent definition.

Per-project effort is not expressible without generating agent files. That is a wall, not
a preference.

`CLAUDE_CODE_SUBAGENT_MODEL` outranks **both** the per-invocation `model` parameter and
frontmatter. If it is set in a fleet launch environment, every tier resolution slopstop
performs is silently overridden.

## Per-site status

Nine sites spawn via a bare `Agent(...)` call and inherit session effort today, because
none of them names a slopstop-defined subagent type:

| Site | Role |
|---|---|
| `skills/tickets/references/tickets-adversary.md` | ticket-tree adversary |
| `skills/single-ticket/SKILL.md` + `references/single-ticket-adversary.md` | single-ticket adversary |
| `skills/run/references/run-verification.md` | two handoff verifiers |
| `skills/run/references/run-failure-handling.md` | rewrite delta check |
| `skills/run/references/run-final-report.md` | drift check, report adversary |
| `skills/plan/references/plan-investigation.md` | `Explore` investigation |
| `skills/plan/references/plan-fanout.md` | worktree implementation agents |
| `skills/plan/SKILL.md` (Step 0f) | Phase 0 adversary gap finder |
| `skills/slop-check/SKILL.md` | slop detection — was `skills/pr/SKILL.md` Step 2e; `:pr` was deleted in `32ecb23` and this is now a standalone worker launched by `:run` stage 9 (`gates`) |

**#450** is the open ticket that gives them declared tiers and effort. Until it lands,
each runs at the session's effort, and the four that pass no `model` run at the session's
model too.

`[fleet.agents].adversary_effort` is a **different mechanism**: it scopes a fleet agent's
own *inline* `:plan`/`:pr` adversaries, which execute in the agent's own context with no
spawn at all. Do not conflate the two.

## One live cost note

As of Claude Code v2.1.198 the built-in `Explore` subagent **inherits the main
conversation's model** (capped at Opus on the Claude API) instead of always running Haiku.
`plan-investigation.md`'s "cheap retrieval" spawn therefore runs at Opus in any
interactive session.

Sources verified 2026-08-05: `code.claude.com/docs/en/sub-agents` (supported frontmatter
fields, `effort`, Explore model inheritance), `code.claude.com/docs/en/model-config`
(effort precedence and defaults).
