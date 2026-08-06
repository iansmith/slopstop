#!/usr/bin/env bash
#
# install-for-claude-desktop.sh
#
# Installs slopstop's commands into ~/.claude/commands/ for use in
# Claude Desktop (which doesn't yet support /plugin install). They appear
# as /slopstop-<name> for every entry in the SKILLS array below
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
SKILLS=(start plan update document archive pr merge doc-sync create-gh gh-init update-ticket grill design tickets single-ticket focus run review investigate red-tests mutation-check adversary implement slop-check)

echo "Installing slopstop commands from $REPO@$REF..."
mkdir -p "$DEST"

# Build sed args dynamically from SKILLS so adding a new skill only requires
# updating one list (same approach as install-for-claude-desktop-local.sh).
SED_ARGS=()
for skill in "${SKILLS[@]}"; do
  # The bare namespaced form (no slash) also covers Skill({skill: "slopstop:<name>"})
  # invocation literals; sed applies the more specific slash form via the same rule.
  SED_ARGS+=(-e "s|slopstop:$skill|slopstop-$skill|g")
done

for skill in "${SKILLS[@]}"; do
  src="https://raw.githubusercontent.com/$REPO/$REF/skills/$skill/SKILL.md"
  dst="$DEST/slopstop-$skill.md"
  echo "  /slopstop-$skill"
  # Frontmatter is PRESERVED (BILL-456). Custom commands were merged into skills, and
  # .claude/commands/*.md supports the same frontmatter -- so stripping it discarded
  # `disable-model-invocation` from 16 skills (leaving every installed copy
  # model-invocable) and made it impossible to ship `review`, whose entire mechanism is
  # `context: fork`.
  #
  # `name:` is the one field that must NOT pass through: it is the display name that
  # decides the invoked command name, so `name: pr` inside slopstop-pr.md would claim
  # /pr and collide with a bundled or project skill. Dropping it lets the name fall back
  # to the filename, which is already slopstop-<skill>.
  # Skip-on-404, same intent as the references loop below (which spells it `|| continue`;
  # this one needs the body in a variable, so it is an if-block). A skill absent at $REF
  # 404s, and under `set -euo pipefail` an unguarded curl aborts the whole install
  # partway. Reachable today — `review` exists on master but in no released tag, so a
  # pinned `SLOPSTOP_REF=v3.7.5` would have died after writing 17 of 18 files.
  if ! body=$(curl -fsSL "$src"); then
    echo "  /slopstop-$skill — not present at $REF; skipping" >&2
    continue
  fi
  printf '%s\n' "$body" \
    | awk 'BEGIN { in_fm=0 }
           NR==1 && /^---$/ { in_fm=1; print; next }
           in_fm && /^---$/ { in_fm=0; print; next }
           in_fm && /^name:[[:space:]]/ { next }
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
    # References get the same namespace rewrite as the spine. run-agent-brief.md tells a
    # fleet agent to call Skill(skill="slopstop:start"); in a commands install only
    # slopstop-start resolves, so an un-rewritten reference hands the agent a skill name
    # that does not exist.
    # Both steps stay inside the `if` condition: under `set -e` an unguarded
    # `sed ... > dst` aborts the whole install on any sed failure, and the redirect
    # truncates dst before sed runs, so a failure would also strand a 0-byte
    # reference. Writing through .tmp and only then moving keeps a previously-good
    # installed file intact when a re-run fails.
    if curl -fsSL "$ref_url" -o "$refs_dir/$ref_name.raw" 2>/dev/null \
       && sed "${SED_ARGS[@]}" "$refs_dir/$ref_name.raw" > "$refs_dir/$ref_name.tmp"; then
      mv "$refs_dir/$ref_name.tmp" "$refs_dir/$ref_name"
      rm -f "$refs_dir/$ref_name.raw"
      skill_count=$((skill_count + 1))
    else
      rm -f "$refs_dir/$ref_name.raw" "$refs_dir/$ref_name.tmp"
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
  /slopstop-pr              open a PR: commit + push + clean-context review (CodeRabbit,
                          Greptile, or Claude); posts a ticket comment linking back
                          to the PR/review once it runs
  /slopstop-merge           ship the code: merge PR + advance ticket one state. Chains
                          into /slopstop-archive automatically once the ticket lands
                          in a terminal state (same in interactive and autonomous
                          mode) — set [workflow] skip_archive=true to disable
  /slopstop-doc-sync        mirror design/ to the project's doc store (GH wiki / Linear
                          Docs). One-way push; orphan-pruning; reads .project-conf.toml
  /slopstop-grill [plan]    interview you relentlessly about a plan until shared
                          understanding — run it before breaking work into tickets
  /slopstop-design <topic>  Stage 1 of the four-tier process: grill -> PRD + charter
                          into scratch/runs/<run-id>/, stop at gate G-design (huge tier)
  /slopstop-tickets <run>   Stage 2: cut the umbrella/leaf tree from the PRD, drive the
                          huge-tier adversary loop, stop at gate G-tickets (large tier)
  /slopstop-single-ticket <KEY>  retrofit an existing ticket to the five-section
                          standard via grill + the huge-tier adversary loop; original
                          content preserved below a separator. Interactive only
  /slopstop-run <run>       Stage 3: orchestrate the fleet — launch, monitor, verify,
                          integrate — stop at gate G-final (medium tier)

Restart Claude Desktop if the commands don't appear in autocomplete.

Don't forget to create .project-prefix in each project dir, e.g.:
  echo MAZ > .project-prefix    # Linear team prefix
  echo PLTF > .project-prefix   # JIRA project prefix

This plugin requires either the Linear or Atlassian MCP installed.
See https://github.com/$REPO#prerequisites for details.

To uninstall later:
  rm $DEST/slopstop-{$(IFS=,; echo "${SKILLS[*]}")}.md
  rm -rf "$DEST"/slopstop-*-refs/
EOF
