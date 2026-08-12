# Tracking-dir resolution — the one definition

`$TRACKING_DIR` and `$ARCHIVE_DIR`, resolved the same way by every skill that touches
per-ticket state. Read this instead of re-deriving it — twelve skills used to carry their
own copy, which is why they disagreed. It lives under `run/references/` because `:run`
owns the tracking dir's lifecycle entry (and the mismatch check below); every other skill
points here.

> It lived under `start/references/` until the 4.0.0 mass deletion, when `32ecb23` removed
> `skills/start/` and `:run` absorbed its work as stage 1 `intake`. The file moved with the
> owner; this note is here because the old path is the one still in people's fingers.

**Resolve both paths together, in one pass.** They are a pair. Resolving one and leaving
the other to a different tier is the bug this file exists to prevent — active state landing
in the repo while archives land in `~/.claude/`, or the reverse.

## The ladder — first match wins

**Tier 1 — an explicit key.** `tracking_dir` / `archive_dir` set in `.project-conf.toml` →
that value, **verbatim**. Each key is independent at this tier: setting one does not stop
the other from falling to tier 2.

`tracking_dir = ".slopstop"` therefore still means exactly `.slopstop` — the ticket dir is
`.slopstop/<TICKET>`, not `.slopstop/ticket-active/<TICKET>`. Existing state is never
restranded by this ladder.

**Tier 2 — a project-local `.slopstop/`.** Neither key set, and `.slopstop/` exists at the
main worktree root →

```
$TRACKING_DIR = .slopstop/ticket-active
$ARCHIVE_DIR  = .slopstop/ticket-archive
```

**Run this exact check — do not paraphrase it:**

```bash
ROOT="$(dirname "$(git rev-parse --git-common-dir)")"
[ -d "$ROOT/.slopstop" ] && echo tier2
```

`$ROOT`, never cwd. `.slopstop/` is gitignored and exists only at the main worktree root,
so a `[ -d .slopstop ]` run from a linked worktree finds nothing, falls through to tier 3,
and lands on the one path a headless agent cannot write — which is the original bug, in the
population tier 2 exists to protect. Fleet agents *always* run from a linked worktree, so
the wrong form of this check fails exactly where it matters most.

**The directory's presence alone is sufficient.** It implies both subdirectories; neither
key needs setting, and neither subdirectory needs to exist yet (create on first write).
This is the tier that should cover almost every project.

**Tier 3 — the historical default.** No key, no `.slopstop/` →

```
$TRACKING_DIR = ~/.claude/ticket-active
$ARCHIVE_DIR  = ~/.claude/ticket-archive
```

Reachable only by a project that has neither key nor a `.slopstop/`, which is why tier 2
exists. See the guard below — this tier works interactively and silently breaks fleet agents.

## Path rules (all tiers)

- **Relative** (no leading `/` or `~/`) → resolve from the **main worktree root**,
  `dirname "$(git rev-parse --git-common-dir)"` — *not* from cwd. Deliberate: every linked
  worktree resolves to the same directory, so a fleet agent's worktree session and the main
  checkout share one tracking dir with no symlinking.
- **Absolute** (leading `/` or `~/`) → used as-is.

## The `~/.claude/` guard

If a resolved path lies under `~/.claude/`, warn and continue:

```
tracking_dir/archive_dir resolves under ~/.claude, a protected path — headless agents
cannot write there even with a matching --add-dir. Create a project-local .slopstop/
directory (tier 2 then applies automatically, no config needed).
```

`~/.claude/` is protected: an agent's `Write` refuses it *even when the session was launched
with a matching `--add-dir`*. A fleet agent that cannot write its tracking dir invents a
local one and carries on, so the failure is silent divergence rather than an error.

The remedy is a **directory, not a key** — do not reintroduce "set `tracking_dir` to a
project-local path (e.g. `.slopstop/ticket-active`)". A session holding an
already-configured `.slopstop` reads that as an instruction to append `ticket-active`,
which is how the divergent trees got invented.

## Layout mismatch — detect and report, never relocate

**Who checks, and when.** `:run` stage 1 `intake` only, on the fresh-start path, before it
seeds `$TRACKING_DIR/<TICKET>/`. Not the other skills that resolve these paths: they run
mid-ticket, where a scan every invocation is noise the operator learns to ignore. Intake is
where a ticket enters the tree, so it is the one moment the answer changes anything.

**What to compare.** Exactly the two paths the *other* tiers would have produced, plus the
flat shape — three candidates, no open-ended search:

```bash
ROOT="$(dirname "$(git rev-parse --git-common-dir)")"
# candidates other than the resolved $TRACKING_DIR:
#   $ROOT/.slopstop/ticket-active     (tier 2)
#   $ROOT/.slopstop                   (flat — a tier-1 `tracking_dir = ".slopstop"`)
#   ~/.claude/ticket-active           (tier 3)
```

**What counts as a ticket dir.** A directory whose name matches `^$PREFIX-[0-9]+$` — this
project's prefix only. Without that predicate a scan of `~/.claude/ticket-active` reports
every other project's tickets, and under the flat shape the subdirectory literally named
`ticket-active` counts itself.

**What to do.** Report and continue. Never move, merge, or delete:

```
Layout mismatch: resolved $TRACKING_DIR = <resolved>, but <N> $PREFIX ticket dir(s) exist
at <other candidate>. Nothing has been moved. Those tickets will not be found by this
session. To adopt them, move them yourself, or set tracking_dir to <other candidate>.
```

Losing a ticket's tracking dir is the failure this whole ladder exists to prevent, so a
mismatch is the operator's call, never an automatic migration — a wrong guess silently
destroys the only record of in-flight work.

**One case this deliberately catches:** `:design` and `:gh-init` create `.slopstop/`, which
flips a project from tier 3 to tier 2 as a side effect. On a project with live state in
`~/.claude/`, the next `:run` intake is what tells the operator their tracking dir just moved.
