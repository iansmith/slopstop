#!/usr/bin/env bash
#
# install-for-project.sh
#
# Installs slopstop into a project's `.claude/skills/` as `slopstop-<name>/`, so the
# project can COMMIT a specific slopstop version and freeze on it. Unlike the two
# Desktop installers, which write to ~/.claude/commands/ for one user on one machine,
# this output is meant to be checked in and shared.
#
#     bash install-for-project.sh ~/lyos/server-v2
#
# A TARGET IS REQUIRED, and the reference repo is refused outright. This used to default
# to `$SRC_DIR` — "into this repo" — which installed slopstop into slopstop. That output
# was 31 tracked, generated files that nothing ever read: this repo is the SOURCE, and
# `install-for-project.sh` reads `skills/`, never `.claude/skills/`. Worse, the reference
# is exempt from `setup-project.py`'s skills check ("self-install lags one commit by
# construction"), so the copies were never regenerated and sat permanently stale — for
# months they described a `**Mode:**` body marker that BILL-508 had removed. Deleted
# 2026-08-09; the guard below is what stops a bare run from silently recreating them.
#
# WHY `slopstop-<name>` AND NOT `<name>`:
#   A skill at .claude/skills/foo/ becomes `/foo` — flat, no namespace. The
#   `slopstop:foo` form comes from PLUGIN installation and does not exist here.
#   Claude Code ships bundled `run` and `review` skills, and a project skill of the
#   same name OVERRIDES the bundled one silently. Namespacing avoids shadowing them.
#
#   Note precedence is enterprise > personal > project: a ~/.claude/skills/slopstop-run
#   would beat the committed copy, defeating the version freeze with no error. Check
#   for one if a project ever seems to be running the wrong slopstop.
#
# THE OUTPUT IS GENERATED. Never hand-edit `.claude/skills/slopstop-*` — edit
# `skills/` and re-run this (universal §5). Each generated SKILL.md says so.

set -euo pipefail

SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

[ $# -ge 1 ] || { echo "Usage: install-for-project.sh <target-repo>" >&2
                  echo "  A target is required. This repo is the SOURCE, not a consumer." >&2
                  exit 2; }

TARGET="$1"
[ -d "$SRC_DIR/skills" ] || { echo "No skills/ in $SRC_DIR — wrong directory?" >&2; exit 1; }
[ -d "$TARGET" ]         || { echo "Target does not exist: $TARGET" >&2; exit 1; }

# Refuse to install slopstop into slopstop. See the header: the output is unread, and being
# exempt from the skills check it would sit stale forever rather than fail loudly.
if [ "$(cd "$TARGET" && pwd)" = "$SRC_DIR" ]; then
  echo "Refusing to install into the slopstop reference repo itself." >&2
  echo "  It is the source of these skills, not a consumer of them." >&2
  exit 2
fi

DEST="$TARGET/.claude/skills"

# Derived from the directory, never hand-maintained — same rule as the other installers.
SKILLS=()
for d in "$SRC_DIR"/skills/*/; do
  [ -f "$d/SKILL.md" ] || continue
  SKILLS+=("$(basename "$d")")
done
[ ${#SKILLS[@]} -gt 0 ] || { echo "No skills found under $SRC_DIR/skills/" >&2; exit 1; }

if git -C "$SRC_DIR" rev-parse --git-dir >/dev/null 2>&1; then
  ver="$(git -C "$SRC_DIR" rev-parse --short HEAD)"
  git -C "$SRC_DIR" diff --quiet && git -C "$SRC_DIR" diff --cached --quiet || ver="$ver-dirty"
else
  ver="unknown"
fi

echo "Installing ${#SKILLS[@]} slopstop skills from $SRC_DIR ($ver)"
echo "                                  into $DEST"
mkdir -p "$DEST"

# Path rewrites, applied to every installed file.
#
#   slopstop:<name>                              -> slopstop-<name>
#   ~/.claude/commands/slopstop-<x>-refs/<file>  -> ../slopstop-<x>/references/<file>
#   skills/<x>/references/<file>                 -> ../slopstop-<x>/references/<file>
#
# Paths are REPO-ROOT-RELATIVE, not `../`-relative to the skill directory.
#
# The docs show supporting files referenced as a bare filename -- `[reference.md](reference.md)`
# -- and say nothing about how a cross-skill `../` path resolves, or whether resolution is
# relative to the skill file or the working directory. :design and :tickets both read
# run's references, so cross-skill pointers are unavoidable here.
#
# A wrong guess fails silently and expensively: an orchestrator that cannot read
# run-jsonl.md or worker-launch.md does not stop, it proceeds WITHOUT its binding
# contracts. So use the one form that needs no undocumented rule -- the path from the
# repository root, which is where Claude Code is started in the normal case.
# The generic placeholder in worker-launch.md's launch template. No per-skill rule
# matches it, and left alone it tells an orchestrator to invoke a name that does not
# exist in a project install.
SED_ARGS=(-e 's|slopstop:<worker>|slopstop-<worker>|g')
for s in "${SKILLS[@]}"; do
  SED_ARGS+=(-e "s|~/.claude/commands/slopstop-$s-refs/|.claude/skills/slopstop-$s/references/|g")
  SED_ARGS+=(-e "s|\`skills/$s/references/|\`.claude/skills/slopstop-$s/references/|g")
  SED_ARGS+=(-e "s|slopstop-$s-refs/|.claude/skills/slopstop-$s/references/|g")
  SED_ARGS+=(-e "s|slopstop:$s|slopstop-$s|g")
done

installed=0; refs_total=0
for s in "${SKILLS[@]}"; do
  out="$DEST/slopstop-$s"
  mkdir -p "$out"

  # `name:` must not pass through: it decides the invoked command name, so a `name: run`
  # would claim /run and shadow the bundled skill this namespacing exists to avoid.
  # Every other frontmatter field is preserved (BILL-456).
  # The GENERATED marker goes AFTER the closing --- of the frontmatter. Putting it
  # first stops the frontmatter being frontmatter at all: it is only parsed when it is
  # the first thing in the file, so the marker silently became each skill's description.
  # Measured, not theorised — it shipped that way for one run.
  awk -v marker="<!-- GENERATED from slopstop $ver by install-for-project.sh — do not edit.\n     Edit skills/$s/ in the slopstop repo and re-run. (universal §5) -->" '
       BEGIN { in_fm=0; done=0 }
       NR==1 && /^---$/ { in_fm=1; print; next }
       in_fm && /^---$/ { in_fm=0; print; print ""; print marker; done=1; next }
       in_fm && /^name:[[:space:]]/ { next }
       { print }
       END { if (!done) print marker }' "$SRC_DIR/skills/$s/SKILL.md" \
    | sed "${SED_ARGS[@]}" > "$out/SKILL.md"
  installed=$((installed + 1))

  if [ -d "$SRC_DIR/skills/$s/references" ]; then
    mkdir -p "$out/references"
    n=0
    for r in "$SRC_DIR/skills/$s/references"/*.md; do
      [ -f "$r" ] || continue
      sed "${SED_ARGS[@]}" "$r" > "$out/references/$(basename "$r")"
      n=$((n + 1))
    done
    # manifest.txt is a Desktop-install artifact: that installer needs a list because it
    # fetches files one at a time over HTTP. Here the directory IS the list.
    rm -f "$out/references/manifest.txt"
    refs_total=$((refs_total + n))
    echo "  /slopstop-$s  ($n references)"
  else
    echo "  /slopstop-$s"
  fi
done

# Effort carriers: one subagent definition per reasoning-effort level, copied verbatim.
# The orchestrator passes `model` on the Agent() call and picks the carrier by resolved
# effort, so this is tier x effort with N files instead of N*M.
#
# FIRST INSTALL CAVEAT: creating `.claude/agents/` where none existed leaves a window in
# which a launch can fail with `Agent type not found` — Claude Code's watcher covers
# directories that existed at session start. Observed 2026-08-07 to resolve on its own
# within a session; a restart also resolves it. Neither is promised here: the honest
# statement is that the first launch may fail and that this is expected and transient.
if [ -d "$SRC_DIR/agents" ]; then
  mkdir -p "$TARGET/.claude/agents"
  n=0
  for a in "$SRC_DIR"/agents/*.md; do
    [ -f "$a" ] || continue
    sed "${SED_ARGS[@]}" "$a" > "$TARGET/.claude/agents/$(basename "$a")"
    n=$((n + 1))
  done
  echo "  $n effort-carrier subagents -> .claude/agents/"
fi

# Remove skills that no longer exist in source. Without this, a renamed or deleted skill
# lingers in the target forever and a stale copy keeps being invocable — the exact drift
# a generated directory is supposed to make impossible.
for existing in "$DEST"/slopstop-*/; do
  [ -d "$existing" ] || continue
  name="$(basename "$existing")"; name="${name#slopstop-}"
  keep=false
  for s in "${SKILLS[@]}"; do [ "$s" = "$name" ] && keep=true && break; done
  if [ "$keep" = false ]; then
    echo "  removing stale: slopstop-$name"
    rm -rf "$existing"
  fi
done

cat <<EOF

Installed $installed skills + $refs_total reference files.

These are GENERATED. Do not edit them — edit skills/ in the slopstop repo and re-run.
Commit them to freeze this project on slopstop $ver.

Invoke as /slopstop-run, /slopstop-design, /slopstop-tickets. The rest are workers the
orchestrators launch; you do not call them directly.
EOF
