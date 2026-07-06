#!/usr/bin/env bash
#
# install-for-claude-desktop.sh
#
# Installs slopstop's commands into ~/.claude/commands/ for use in
# Claude Desktop (which doesn't yet support /plugin install). They appear
# as /slopstop-start, /slopstop-plan, /slopstop-update, /slopstop-document,
# /slopstop-archive, /slopstop-pr, /slopstop-merge, /slopstop-doc-sync,
# /slopstop-create-gh, and /slopstop-update-ticket
# (no plugin namespace — Claude Desktop loads them as standalone slash commands).
#
# For Claude Code (CLI) users, the proper install is:
#
#     /plugin marketplace add iansmith/slopstop
#     /plugin install slopstop@slopstop
#
# To pin to a specific version, set SLOPSTOP_REF (defaults to master):
#
#     SLOPSTOP_REF=v1.0.0 bash install-for-claude-desktop.sh
#

set -euo pipefail

REPO="iansmith/slopstop"
REF="${SLOPSTOP_REF:-master}"
DEST="$HOME/.claude/commands"
SKILLS=(start plan update document archive pr merge doc-sync create-gh update-ticket)

echo "Installing slopstop commands from $REPO@$REF..."
mkdir -p "$DEST"

# Build sed args dynamically from SKILLS so adding a new skill only requires
# updating one list (same approach as install-for-claude-desktop-local.sh).
SED_ARGS=()
for skill in "${SKILLS[@]}"; do
  SED_ARGS+=(-e "s|/slopstop:$skill|/slopstop-$skill|g")
done

for skill in "${SKILLS[@]}"; do
  src="https://raw.githubusercontent.com/$REPO/$REF/skills/$skill/SKILL.md"
  dst="$DEST/slopstop-$skill.md"
  echo "  /slopstop-$skill"
  curl -fsSL "$src" \
    | awk 'BEGIN { in_fm=0 }
           NR==1 && /^---$/ { in_fm=1; next }
           in_fm && /^---$/ { in_fm=0; next }
           in_fm { next }
           { print }' \
    | sed "${SED_ARGS[@]}" \
    > "$dst"
done

# Install references/ files alongside each skill for token-efficient conditional loading.
# The spine loads on every invocation; references are read only when the relevant code
# path is taken (e.g. the CC gate reference is only loaded on PRs with changed source files).
# Iterates all SKILLS; the manifest fetch failing (404 for skills with no references/ dir)
# is handled by || continue — self-maintaining when new skills gain a references/ dir.
echo ""
echo "Installing slopstop skill references..."
refs_total=0
for skill in "${SKILLS[@]}"; do
  manifest_url="https://raw.githubusercontent.com/$REPO/$REF/skills/$skill/references/manifest.txt"
  manifest=$(curl -fsSL "$manifest_url" 2>/dev/null) || continue
  [ -z "$manifest" ] && continue
  refs_dir="$DEST/slopstop-$skill-refs"
  mkdir -p "$refs_dir"
  skill_count=0
  while IFS= read -r ref_name; do
    [ -z "$ref_name" ] && continue
    ref_url="https://raw.githubusercontent.com/$REPO/$REF/skills/$skill/references/$ref_name"
    if curl -fsSL "$ref_url" -o "$refs_dir/$ref_name" 2>/dev/null; then
      skill_count=$((skill_count + 1))
    else
      rm -f "$refs_dir/$ref_name"
      echo "  warning: failed to fetch $skill/references/$ref_name" >&2
    fi
  done <<< "$manifest"
  if [ "$skill_count" -gt 0 ]; then
    echo "  slopstop-$skill-refs/ ($skill_count files)"
  else
    rmdir "$refs_dir" 2>/dev/null
  fi
  refs_total=$((refs_total + skill_count))
done

echo ""
echo "Installing slopstop system dependencies..."
if pip install lizard --quiet 2>/dev/null \
   || pip3 install lizard --quiet 2>/dev/null \
   || python3 -m pip install lizard --quiet 2>/dev/null; then
  echo "  lizard (cyclomatic complexity gate) — OK"
else
  echo "  lizard (cyclomatic complexity gate) — install failed; run 'pip install lizard' manually"
fi

cat <<EOF

Installed ${#SKILLS[@]} commands + $refs_total reference files to $DEST:

  /slopstop-start <KEY>     start or resume work on a ticket
  /slopstop-plan [args]     investigate + write a parallelism-aware plan; optional agent fanout
  /slopstop-update [KEY]    mid-session checkpoint to progress.md; optional explicit ticket key
  /slopstop-document        push current local docs (description + DoD-confirmation comment
                          + findings) to the ticket. Idempotent; stops on divergence.
                          --force overrides; --dry-run previews
  /slopstop-archive         push final plan + DoD-confirmation comment + findings to a
                          ticket already moved to a Done-type state on Linear/JIRA, then
                          archive the local tracking dir (delegates the push to
                          /slopstop-document; stops cleanly if divergence is detected)
  /slopstop-pr              open a PR: simplify + commit + push + CodeRabbit poll
  /slopstop-merge           ship the code: merge PR + advance ticket one state. Does NOT
                          archive — the summary tells you whether to run
                          /slopstop-archive now (terminal state) or wait (intermediate)
  /slopstop-doc-sync        mirror design/ to the project's doc store (GH wiki / Linear
                          Docs). One-way push; orphan-pruning; reads .project-conf.toml

Restart Claude Desktop if the commands don't appear in autocomplete.

Don't forget to create .project-prefix in each project dir, e.g.:
  echo MAZ > .project-prefix    # Linear team prefix
  echo PLTF > .project-prefix   # JIRA project prefix

This plugin requires either the Linear or Atlassian MCP installed.
See https://github.com/$REPO#prerequisites for details.

To uninstall later:
  rm $DEST/slopstop-{start,plan,update,document,archive,pr,merge,doc-sync,create-gh,update-ticket}.md
  rm -rf "$DEST"/slopstop-*-refs/
EOF
