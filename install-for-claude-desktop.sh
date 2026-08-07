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
# Derived from the repo, never hand-maintained. A hardcoded array silently ships an
# install without a new skill -- the failure BILL-436 was filed for -- and the test
# that used to catch it is gone. There is nothing to keep in sync now.
#
# raw.githubusercontent.com cannot list a directory, so this needs the contents API.
# Names are extracted without jq (not everywhere) and without python3 (not a
# dependency an installer should add): compact the JSON, split into flat objects,
# keep the directories, read their names.
skills_json=$(curl -fsSL -H "Accept: application/vnd.github+json" \
  "https://api.github.com/repos/$REPO/contents/skills?ref=$REF") || {
  echo "Could not list skills/ from the GitHub API (rate limit, or bad SLOPSTOP_REF=$REF)." >&2
  echo "Clone the repo and run install-for-claude-desktop-local.sh instead." >&2
  exit 1
}
# The `_links` strip is load-bearing: each entry carries a NESTED _links object, so
# splitting on {...} without removing it first matches _links and never the entry.
# Measured against the live API: 0 skills parsed before this sed, 17 after.
SKILLS=($(printf '%s' "$skills_json" | tr -d '\n ' \
  | sed 's/"_links":{[^{}]*}//g' \
  | grep -o '{[^{}]*}' | grep '"type":"dir"' \
  | sed -n 's/.*"name":"\([^"]*\)".*/\1/p' | sort))
if [ ${#SKILLS[@]} -eq 0 ]; then
  echo "GitHub returned no skill directories for $REPO@$REF. Refusing to install nothing." >&2
  exit 1
fi

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
  # decides the invoked command name, so `name: run` inside slopstop-run.md would claim
  # /run and collide with a bundled or project skill. Dropping it lets the name fall back
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
    # References get the same namespace rewrite as the spine. worker-launch.md tells an
    # orchestrator to call Skill(skill="slopstop:adversary"); in a commands install only
    # slopstop-adversary resolves, so an un-rewritten reference hands the agent a skill name
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

Installed ${#SKILLS[@]} commands + $refs_total reference files to $DEST.

Six of them are yours to invoke:

  /slopstop-run <TICKET...>   the whole lifecycle for one or more tickets, interleaved:
                              investigate, red tests, adversary, implement, gates,
                              review, PR, merge, archive. AUTONOMOUS BY DEFAULT
  /slopstop-design <topic>    Stage 1 — grill to shared understanding, write the PRD
                              and charter into scratch/runs/<run-id>/
  /slopstop-tickets <run-id>  Stage 2 — cut an adversary-approved ticket tree from the
                              PRD. Also --retrofit <TICKET> to bring an existing ticket
                              up to standard, --rewrite <TICKET> to repair one that
                              failed implementation, and --refactor <fn>... to cut a
                              "nothing broke" ticket from complexity-check's exempt list
  /slopstop-grill [topic]     interview you until there are no unresolved branches left
  /slopstop-gh-init           bootstrap a GitHub repo: status labels + .project-conf.toml
  /slopstop-doc-sync          mirror design/ to the project's doc store

The rest are workers. The orchestrators launch them as agents; you do not invoke them:
investigate, red-tests, mutation-check, adversary, implement, review, slop-check,
vacuity-check, complexity-check, create-ticket, archive.

Every run appends its stage transitions to run.jsonl in the ticket's tracking directory —
state machine, resume point and timing record in one file.

Restart Claude Desktop if the commands don't appear in autocomplete.

Configure each project with a .project-conf.toml (system, key, prefix). /slopstop-gh-init
writes one for GitHub; see https://github.com/$REPO/blob/master/CONFIG.md for the rest.
Linear and JIRA need their respective MCP server installed.

To uninstall later:
  rm $DEST/slopstop-{$(IFS=,; echo "${SKILLS[*]}")}.md
  rm -rf "$DEST"/slopstop-*-refs/
EOF
