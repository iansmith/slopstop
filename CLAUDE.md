# slopstop (ticket-plugin)

The slopstop plugin itself — the `/slopstop:*` skills, their reference docs, and
the plugin manifest. Repo: `github.com:iansmith/slopstop`. Consumed by the other
five projects via `.project-conf.toml`.

Its own process docs live in `docs/`; `CONFIG.md` documents `.project-conf.toml`
(including `[pr_review] backend`, referenced by universal §9 below).

---

## Universal Project Rules

These live in **`.claude/rules/universal.md`**, which Claude Code loads automatically —
no import line, and nothing to forget. One mirrored copy per project, byte-identical
everywhere. **Edit them in the slopstop repo (the reference copy) and propagate; never
edit the copy in this repo.**

Moved from a root `CLAUDE-universal.md` + `@import` on 2026-08-06. Three reasons: the
import was a step every repo had to remember; `.claude/rules/*.md` loads without one; and
some repos gitignore `/*.md` at the root, which silently hid the file there.

**Precedence caveat.** Rules in `.claude/rules/` load with the *same* priority as
`CLAUDE.md` — not higher. So a project override of a universal rule is resolved by its
**heading**, not by file order: write `## <Topic> (overrides universal §N)` and it reads
correctly regardless of load order. Do not rely on position. `CLAUDE.local.md` is the one
file that genuinely loads last, and it is per-developer.

Project-specific rules and deliberate overrides go below, in this file.

---

# Slopstop-Specific Declarations

## Tests (per universal §1)

This repo has **no test suite**, deliberately, as of 2026-08-06.

It had one: ~4,500 lines of Python whose main job was asserting on the content of its own
markdown. It pinned wording, proved no behavior, and could not catch the failures that
actually occurred. Building a test-first tool test-first is where the recursion stopped
paying.

**What replaces it:** slopstop is validated by being run on the repos that consume it. That
is the only thing that ever proved the process worked.

**What this does not license.** slopstop still enforces TDD *in those repos* — `red-tests`
and `mutation-check` are workers in every run. The exemption is for the tool, not for
anything the tool builds. `router/` keeps its 3,551 lines of Go tests: it is a real network
proxy, not part of the recursion problem.

**Before you commit here,** "verified" means the change was actually exercised — the
installer run, the skill invoked, the tool executed — not that it looked right. Say in the
commit what you ran.

## This repo is the tool the other projects' rules run on

A change here changes how every other project's ticket flow behaves. The universal
block above is not decoration: the skills in this repo are what enforce it, so a
rule and its implementation can drift apart. When they disagree, say so rather
than quietly following one.
## Propagating the universal rules (this repo is the reference)

§10 says to edit the reference and propagate. This is how.

The universal rules live in **`.claude/rules/universal.md`** in every repo, loaded
automatically — no import line anywhere. Edit the copy **here**, update
`.claude/rules/universal.sha256` in the same commit, then:

```bash
python3 ~/ticket-plugin/tools/fleet-sync/setup-project.py --repos <repo> --apply
python3 ~/ticket-plugin/tools/fleet-sync/setup-project.py --repos <repo>   # verify — writes nothing
```

Omit `--repos` for the whole fleet. Idempotent — running it when nothing changed is a
safe way to check a repo agrees. `REPOS` in `fleet.py` is the list; a path that does not
exist is reported and skipped, never guessed at. Note this does more than the rules: it
also installs skills and agents, repairs `.gitignore`, and syncs `.project-conf.toml`.

**`migrate-universal-block.py` was deleted on 2026-08-07, not retired-in-place.** It
still wrote the pre-2026-08-06 layout — root `CLAUDE-universal.md` plus an `@import` —
so running the procedure this section used to document would have *reverted* a migrated
repo while reporting success. That is not a stale doc; it is a tool that undoes the
current standard, and this section pointed straight at it. Found while migrating mazzy,
where following the old instructions would have undone the migration in the same pass
that performed it.

### Why a whole file, and not a marked region

Until 2026-08-01 the rules were a region spliced *inside* each `CLAUDE.md`, delimited
by `<!-- BEGIN/END UNIVERSAL SECTION -->` markers. That design had a trap worth
remembering even though it is now gone: **the marker names appeared in §10's own prose**,
so any loose match (`awk '/BEGIN/,/END/'`, `s.index(END, i)`) terminated at the wrong
place *silently*. Both wrong versions bit during the 2026-07-17 mirror — one extracted
6 lines instead of ~118, the other duplicated content into every mirror and wiped
sophie's project-specific declarations. Neither raised an error; the tells were a hash
mismatch and files inexplicably growing.

The whole-file design removes the failure mode rather than documenting it: there is no
region to mis-delimit. It also let the drift found on 2026-08-01 be fixed in the same
pass — the reference had silently run 18 lines ahead of all five mirrors.

Kept as a scar, not a procedure: if you ever reintroduce a marker-delimited region
anywhere, anchor the pattern to whole lines and assert exactly one of each marker.

### Landing it

Ian's rule (2026-07-17): **repos with a clean master → commit straight to master.**
For a repo sitting on a feature branch → commit to master, then carry it in with
`git merge master`, not rebase: those branches are pushed and often have open PRs, so
a rebase needs `--force`, which universal §3 forbids without an explicit ask.

Push to **both** remotes where two exist (mobile-v2 and server-v2 have `mycopy` +
`origin`).

### Two things that will waste your time

- **Overrides go BELOW the import**, in the project's own `CLAUDE.md`. A project may
  deliberately override a universal rule — `mazzy`'s `## Pre-commit (overrides universal
  §1)` is the live example. `CLAUDE-universal.md` stays byte-identical everywhere; the
  override sits after the `@CLAUDE-universal.md` line so it is read second. This section
  you are reading lives only in slopstop's `CLAUDE.md`, which is why it is not mirrored.
- **`skip-worktree` can hide a mirror from you.** `~/mazzy/CLAUDE.md` had the bit set:
  the file on disk was a stale pre-refactor copy, `git status` reported clean, and an
  edit there would have been swallowed with no diff. Cleared 2026-07-17. If a `CLAUDE.md`
  or `CLAUDE-universal.md` looks inexplicably out of date, check `git ls-files -v <file>`
  — `S` = skip-worktree, `h` = assume-unchanged.
- **Two repos keep personal files machine-local: `lyos/mobile-v2` and `lyos/server-v2`.**
  Both are shared with another contributor, so `.project-conf.toml` *and*
  `CLAUDE-universal.md` are gitignored there — config edits and rules edits cannot be
  committed, so don't go looking for a diff that will never appear. Everywhere else both
  are tracked (louis14 and gaston were un-ignored 2026-08-01). The list lives in
  `tools/fleet-sync/fleet.py` as `LOCAL_RULES_REPOS`;
  `tools/fleet-sync/audit-project-conf.py` checks the fleet.
