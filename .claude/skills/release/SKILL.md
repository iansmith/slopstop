---
name: release
description: Release checklist for the slopstop plugin. Use before pushing a version tag, or when adding/renaming a skill (the install shape and the Desktop install script are listed here).
---

# slopstop — release checklist

**MANDATORY before pushing a new version tag.**

1. **Validate the manifests.** Run `claude plugin validate` against both the plugin manifest and (separately) the marketplace manifest. Both must pass.

   ```bash
   ~/.local/bin/claude plugin validate ~/ticket-plugin/.claude-plugin/plugin.json
   ```

   Or from inside the repo (`cd ~/ticket-plugin && claude plugin validate .`) — the latter form validates both `plugin.json` and `marketplace.json` in one shot.

   (The GitHub repo is `iansmith/slopstop`; the local checkout is still `~/ticket-plugin` from before the rename. These commands take the **local** path.)

   Common past failure: `marketplace.json` had `"source": "."` (bare-dot path). The schema rejects that. Fixed in v1.1.2 by switching to the object form:

   ```json
   "source": {
     "source": "github",
     "repo": "iansmith/slopstop"
   }
   ```

   If you change either manifest, **re-run validate before committing**.

2. **Bump `version` in `.claude-plugin/plugin.json`.** Semver — `MAJOR.MINOR.PATCH`. Patch for fixes / metadata polish; minor for new features (e.g., a new slash command); major for breaking changes (e.g., renamed plugin, changed install command shape).

3. **Update `CHANGELOG.md`** with the new version section before tagging. Keep entries factual; explain *why* not just *what*.

4. **Never force-move tags** once they're pushed, except during the very-pre-release period before any users existed. The `v1.0.0` tag was force-moved several times during initial polish before submission; from `v1.0.0`-and-later, all tags are immutable. If a release ships broken, ship the fix as a new patch version (`v1.x.y+1`), never rewrite history.

5. **Push master, then push both tags.** The plugin marketplace resolves `/plugin marketplace add iansmith/slopstop@X.Y.Z` by doing `git clone --branch X.Y.Z` — so `v2.5.0` won't satisfy `@2.5.0`. Push an annotated v-prefixed tag AND a lightweight bare-version alias pointing at the same commit:

   ```bash
   git tag -a vX.Y.Z -m "Release vX.Y.Z: <summary>"
   git tag X.Y.Z vX.Y.Z^{}
   git push origin master vX.Y.Z X.Y.Z
   ```

## Plugin format reference

- Plugin manifest: `.claude-plugin/plugin.json` (schema: `https://json.schemastore.org/claude-code-plugin-manifest.json`)
- `homepage` in both manifests points at the published site, <https://iansmith.github.io/slopstop/>; `repository` and the marketplace `source` stay on GitHub. They are separate slots in the plugin-manager UI, and only `source` is used to resolve an install.
- Self-distribution marketplace: `.claude-plugin/marketplace.json` — uses the `{"source": "github", "repo": "..."}` form (NOT bare-dot or `"./"` — schema rejects those)
- Skills: `skills/<name>/SKILL.md` with YAML frontmatter — `description:` required, `disable-model-invocation: true` on every skill that is an explicit slash command. Don't quote a count here; `skills/` is the source of truth. (`gh-init` is currently the only one without it — it carries no note saying why, so confirm before treating that as intentional.)
- Claude Desktop standalone install: `install-for-claude-desktop.sh` curls each `SKILL.md` from GitHub, strips frontmatter, rewrites `/slopstop:<name>` → `/slopstop-<name>`, and drops the files into `~/.claude/commands/`. Update the script's `SKILLS=( ... )` array and `sed` substitutions when adding or renaming a skill.

## Authoritative docs

- Plugins guide: https://code.claude.com/docs/en/plugins
- Plugins reference (manifest schema): https://code.claude.com/docs/en/plugins-reference
- Marketplaces reference (`source` schema): https://code.claude.com/docs/en/plugin-marketplaces
- Submission form: https://clau.de/plugin-directory-submission (alternately: claude.ai/settings/plugins/submit, platform.claude.com/plugins/submit)

## Distribution paths

| Audience | Path | Invocation |
|---|---|---|
| Claude Code (CLI) — third-party marketplace | `/plugin marketplace add iansmith/slopstop` then `/plugin install slopstop@slopstop` | `/slopstop:<name>` |
| Claude Code (CLI) — official Anthropic marketplace (pending review) | `/plugin install slopstop@claude-plugins-official` | `/slopstop:<name>` |
| Claude Desktop (no `/plugin` support yet) | `curl -fsSL https://raw.githubusercontent.com/iansmith/slopstop/<ref>/install-for-claude-desktop.sh \| bash` | `/slopstop-<name>` (un-namespaced) |

**The install command shape is copy-pasted across the repo — enumerate it, don't recall it.**
Release-checklist step 2 names a changed install shape as a MAJOR-bump trigger; when that
happens, find every site rather than working from a list that rots:

```bash
grep -rn --include='*.md' --include='*.sh' "plugin install slopstop@slopstop" . | grep -v CHANGELOG
```

As of 2026-08-04 that is **nine** sites: this table, `README.md`, `QUICKSTART.md`,
`SETUP-GUIDE.md`, `install-for-claude-desktop.sh`, `site/index.md`,
`site/what_is_slopstop.md`, `skills/design/SKILL.md`, and `skills/tickets/SKILL.md`. This
paragraph previously said "six places" and named only the first six — the last three were
already live and would have been missed. The two under `skills/` are the sharpest: they
print an install line inside a handoff block that ships to plugin users.

`site/` is easy to miss for a different reason — it is the public landing page at
<https://iansmith.github.io/slopstop/>, deployed by `.github/workflows/pages.yml` on any push to
`master` touching `site/**`, `walkthrough/**`, or the workflow itself. That path filter
deliberately decouples it from the rest of the repo, so a docs-only fix elsewhere never prompts a
look at it.
