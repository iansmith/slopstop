# slopstop — repo conventions

This file is loaded by Claude Code (and Claude Desktop) when working inside this repo via the `.claude/rules/` mechanism (any `*.md` file in there gets pulled into context at session start, same way `CLAUDE.md` would at the repo root). Treat the rules below as binding for any session iterating on the plugin.

(Originally lived at `CLAUDE.md` at the repo root, but the Claude Code plugin validator warns about `CLAUDE.md` at a plugin root — it assumes that file is trying to ship context to *plugin users*, which doesn't work. Our use case is the opposite — repo conventions for *maintainers*. `.claude/rules/` is the right home for that, and avoids the false-positive warning.)

## Releasing a new version

**MANDATORY before pushing a version tag** — the checklist is on-demand, not in this file.
→ Read `.claude/skills/release/SKILL.md` (invoke as `/release`)

**Adding or renaming a skill** also has release consequences, and they bite long before
you cut a tag: update the `SKILLS=( … )` array and the `sed` substitutions in **both**
`install-for-claude-desktop.sh` and `install-for-claude-desktop-local.sh`, or the Desktop
install silently ships without the new command. `/release` lists the other sites the
install shape appears in.

`test_bill436_behaviors.py::test_every_skill_on_disk_is_installed` now catches the
omission — every skill in `skills/` must appear in both arrays, with no exemptions. (This
note used to say "No test catches that", which was true until BILL-436.)

**Frontmatter passes through the install, and that is load-bearing** (BILL-456). The
installers copy it verbatim except `name:`, which is dropped so the command name falls
back to the `slopstop-<skill>` filename instead of claiming the bare `/<skill>`. Do not
reintroduce blanket stripping: it silently discarded `disable-model-invocation` from 16
skills — leaving every installed copy model-invocable when the repo says it must not be —
and it is why `review`, whose whole mechanism is `context: fork`, could not ship at all.
A new frontmatter field needs no installer change; a new field that must *not* reach the
install does.

## Workflow conventions inside this repo

- All commits anchored to a ticket get `[TICKET-KEY]` prefix in the subject and `Refs: TICKET-KEY` (or `Closes:` on the final commit) trailer. These trailers are **provenance only — not GitHub closing keywords**: GitHub parses `Closes #312`, not `Closes: BILL-312`, so nothing auto-closes from them. `:run` stage 14 (`close`) performs the actual close/label transition via the API — *"score the DoD, advance the ticket state / swap labels"* (`skills/run/SKILL.md`, the state-machine table), with the mechanics under **Stages 13–15**; merging outside that path leaves the ticket open and the status label stuck. (This said `/slopstop:merge` until BILL-537. That skill was deleted in `32ecb23` and `:run` absorbed it inline, so the instruction sent every session in this repo at a `Skill()` call that would fail.)
- **Never write `Closes #N` (or `Fixes #N` / `Resolves #N`) in a PR description** — those *are* GitHub closing keywords, and GitHub auto-closes the issue the moment the PR merges. That races `/slopstop:merge`'s own Step 5, which is what's supposed to own closure (see the trailer note above — the whole point of keeping trailers non-triggering is defeated if the PR body does the same thing). It doesn't corrupt the end state (`:merge` still detects CLOSED/COMPLETED and proceeds), but it does silently skip the label side of Step 5 — GitHub's auto-close never removes `status:in-progress`, so that removal has to happen as an explicit follow-up instead of the normal one-shot transition. Reference the ticket in a PR body as plain prose (`Refs #312`, `For #312`, or just naming it) instead.
- Co-Authored-By trailer on all Claude-assisted commits, naming the model that actually authored it: `Co-Authored-By: Claude <model> using slopstop <noreply@anthropic.com>` — e.g. `Claude Opus 4.8 using slopstop`, `Claude Fable 5 using slopstop`. (This rule used to hardcode `Claude Sonnet 4.6`, which no commit had used for months; the trailer is provenance, so it tracks the real model.)
- Never `git push --force`, `git commit --no-verify`, `gh pr merge --admin`, or `git reset --hard` — none of these have a place in this repo's flow.
- **Run the full test suite before pausing to ask about a commit.** When working in a batched plan (or any multi-step change), do NOT pause and ask "ready to commit?" with unverified code in the working tree. This repo has **no test suite** as of the 2026-08-06 reorg — see `## Tests` below — so "verified" here means the change was actually exercised: the installer run, the skill invoked, the tool executed. Surface what you actually ran in the consult message. The pause is for the human to approve a *known-green* state, not to ratify untested work. If a layer can't run locally (e.g. image build is broken, registry unreachable), say so explicitly in the consult — don't silently skip.
