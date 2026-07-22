#!/usr/bin/env bash
#
# install-for-claude-desktop-local.sh
#
# Local-source variant of install-for-claude-desktop.sh.
#
# Installs from the working copy this script lives in, NOT from GitHub —
# so you can test uncommitted changes on a feature branch in Claude Desktop
# before opening a PR. Otherwise identical: same destination, same frontmatter
# stripping, same /slopstop:<name> -> /slopstop-<name> rewrites.
#
# Run from anywhere; the script resolves its own location:
#
#     bash install-for-claude-desktop-local.sh
#
# For release installs (pinned to a tag or master on GitHub), use the
# non-"-local" sibling script instead.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEST="$HOME/.claude/commands"
SKILLS=(start plan update document archive pr merge doc-sync create-gh gh-init update-ticket grill design tickets single-ticket focus run)

# Report what we're installing so it's obvious when testing branches.
if git -C "$SCRIPT_DIR" rev-parse --git-dir >/dev/null 2>&1; then
  branch=$(git -C "$SCRIPT_DIR" rev-parse --abbrev-ref HEAD)
  sha=$(git -C "$SCRIPT_DIR" rev-parse --short HEAD)
  dirty=""
  if ! git -C "$SCRIPT_DIR" diff --quiet || ! git -C "$SCRIPT_DIR" diff --cached --quiet; then
    dirty=" (working tree has uncommitted changes)"
  fi
  echo "Installing slopstop commands from local source: $SCRIPT_DIR"
  echo "  branch=$branch sha=$sha$dirty"
else
  echo "Installing slopstop commands from local source: $SCRIPT_DIR"
fi

mkdir -p "$DEST"

# Build sed args dynamically from SKILLS so adding a new skill only requires
# updating one list.
SED_ARGS=()
for skill in "${SKILLS[@]}"; do
  # The bare namespaced form (no slash) also covers Skill({skill: "slopstop:<name>"})
  # invocation literals; the slash-prefixed command form is a substring case of it.
  SED_ARGS+=(-e "s|slopstop:$skill|slopstop-$skill|g")
done

for skill in "${SKILLS[@]}"; do
  src="$SCRIPT_DIR/skills/$skill/SKILL.md"
  dst="$DEST/slopstop-$skill.md"
  if [ ! -f "$src" ]; then
    echo "  /slopstop-$skill — MISSING source at $src; skipping" >&2
    continue
  fi
  echo "  /slopstop-$skill"
  awk 'BEGIN { in_fm=0 }
       NR==1 && /^---$/ { in_fm=1; next }
       in_fm && /^---$/ { in_fm=0; next }
       in_fm { next }
       { print }' "$src" \
    | sed "${SED_ARGS[@]}" \
    > "$dst"
done

# Install references/ files alongside each skill for token-efficient conditional loading.
echo ""
echo "Installing slopstop skill references..."
refs_total=0
for skill in "${SKILLS[@]}"; do
  manifest_file="$SCRIPT_DIR/skills/$skill/references/manifest.txt"
  [ -f "$manifest_file" ] || continue
  refs_dir="$DEST/slopstop-$skill-refs"
  mkdir -p "$refs_dir"
  skill_count=0
  while IFS= read -r ref_name; do
    [ -z "$ref_name" ] && continue
    ref_src="$SCRIPT_DIR/skills/$skill/references/$ref_name"
    # References get the same namespace rewrite as the spine. run-agent-brief.md tells a
    # fleet agent to call Skill(skill="slopstop:start"); in a commands install only
    # slopstop-start resolves, so an un-rewritten reference hands the agent a skill name
    # that does not exist.
    # Write through .tmp: `sed src > dst` truncates dst *before* reading src, so a
    # manifest listing a file that no longer exists would empty a previously-good
    # installed reference. Guarding inside the `if` also stops `set -e` aborting the
    # whole install on a sed failure. sed's stderr is left visible on purpose.
    if [ -f "$ref_src" ] && sed "${SED_ARGS[@]}" "$ref_src" > "$refs_dir/$ref_name.tmp"; then
      mv "$refs_dir/$ref_name.tmp" "$refs_dir/$ref_name"
      skill_count=$((skill_count + 1))
    else
      rm -f "$refs_dir/$ref_name.tmp"
      echo "  warning: missing or unreadable reference file $ref_src" >&2
    fi
  done < "$manifest_file"
  [ "$skill_count" -gt 0 ] && echo "  slopstop-$skill-refs/ ($skill_count files)"
  refs_total=$((refs_total + skill_count))
done

cat <<EOF

Installed ${#SKILLS[@]} commands + $refs_total reference files to $DEST.

Restart Claude Desktop if the commands don't appear in autocomplete.

To revert to the released version from GitHub, run the sibling script:
  bash $SCRIPT_DIR/install-for-claude-desktop.sh

To uninstall entirely:
  rm $DEST/slopstop-{$(IFS=,; echo "${SKILLS[*]}")}.md
  rm -rf "$DEST"/slopstop-*-refs/
EOF
