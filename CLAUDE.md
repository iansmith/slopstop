# slopstop (ticket-plugin)

The slopstop plugin itself — the `/slopstop:*` skills, their reference docs, and
the plugin manifest. Repo: `github.com:iansmith/slopstop`. Consumed by the other
five projects via `.project-conf.toml`.

Its own process docs live in `docs/`; `CONFIG.md` documents `.project-conf.toml`
(including `[pr_review] backend`, referenced by universal §9 below).

---

<!-- BEGIN UNIVERSAL SECTION -->
<!-- REFERENCE COPY. This repo (ticket-plugin / slopstop) holds the canonical universal
     block; the other five projects carry byte-identical copies of it. Edit it HERE, then
     propagate — never the other way round, and never by hand.
     Extract with the ANCHORED pattern (^...$) — an unanchored one also matches the
     marker names mentioned in prose below, and stops early:
       awk '/^<!-- BEGIN UNIVERSAL SECTION -->$/,/^<!-- END UNIVERSAL SECTION -->$/' CLAUDE.md
     Project-specific overrides go OUTSIDE these markers. See §10. -->

# Universal Project Rules

These rules apply across all of Ian's projects unless this CLAUDE.md explicitly overrides them.

## 1. Pre-commit

- **ALWAYS run `/simplify` on uncommitted changes before every commit.** No exceptions on size — a one-line change can introduce a duplicate constant, touch the wrong file, or violate a project rule, all of which `/simplify` catches cheaply. Apply real findings inline before committing.
- Run the project's build + targeted tests (the package or area you touched) before commit. Run the full suite only when touching shared/cross-cutting code.
- Commit, then push — only after the above are clean. **If the project has multiple remotes, push to all of them.**

## 2. Tests

- **Tests-first for new behavior AND for fixes.** For new behavior, write the test describing the desired contract; confirm it's red **for the right reason** before implementing. For bug fixes, write a test that reproduces the bug — it must be red before the fix and green after. Trivial tweaks, copy changes, and pure refactors are exempt.
- **A failing test is signal, not chore.** Investigate the root cause before changing anything. Never delete a test, narrow an assertion, call `Skip()`, or cite an unverified "flake" to silence it. "Known flake" is a label, not an explanation.

(Test scope before commit is covered by §1. Project-specific guidance on test runtime and scoping lives in each project's CLAUDE.md.)

## 3. Git

- **NEVER squash-merge or rebase-merge.** Use `gh pr merge --merge` (real merge commit). Squash and rebase lose fixup context and break `git bisect`.
- Always include the explicit branch name in `git push origin <branch>`.
- Never `git push --force`, `git reset --hard`, `git commit --no-verify`, `git push --no-verify`, or `gh pr merge --admin` unless the user explicitly asks. When a hook or check fails, fix the underlying issue, don't bypass.
- Create new commits rather than amending. The single exception: amending one fresh commit on a solo branch before anyone has pulled it.

## 4. Refactoring scope

- **Dedupe is in scope.** If you find 2+ near-identical code paths while working on a change, extract the helper and migrate the duplicates in the same PR.
- **Structural changes are out of scope without discussion.** Renaming exported symbols, altering public signatures, moving files, or reshaping module boundaries must be raised separately.
- When extending an existing system, study its types and patterns first. Mirror existing vocabulary; don't invent parallel terms for the same concept.
- Foundational correctness over quick wins. "Nearly passing" is failing. When working through a category of failures, **don't declare done by cherry-picking the easy cases** — solve the problem completely.

## 5. Source of truth

- **One definition per value.** No duplicate constants, aliases, or parallel names. If something needs renaming, update every reference — never add an alias.
- Never edit generated files by hand. Edit the source and regenerate.

## 6. Agents and worktrees

### Coordinator rules — how to behave when running agents

- Commit and push before launching worktree agents — worktrees start from HEAD, not the working directory.
- **Aim for fine-grained milestones** — frequent enough that progress is visible (rough target: a check-in every few minutes of work), but not so frequent that the output becomes noise. Every 10 seconds is too often; every 20 minutes is too long.
- **Aim for parallelism that won't cause merge-back conflicts on the base branch.** If the work can't be cleanly parallelized, consider whether sequential agent offload is actually worth the overhead — small tasks belong on your own plate; genuinely large offloads (long builds, multi-file refactors you'd otherwise wait on) can still be a win even when sequential.
- **Never use `open` to display files unless the user explicitly asks.** Disruptive even from the main session.

### Agent instructions — what to include in every agent prompt

- **Run on a separate branch in a separate directory.** Before working, prepare the directory if the project requires it — e.g., symlink large, rarely-changing directories that aren't under git control from the worktree to their original location, so the agent has its dependencies without duplicating them.
- **Commit only to your worktree's branch.** Never touch `main`/`master` or other shared branches from a worktree.
- **Commit and report at every milestone, not just at the end.**
- **Never use `open` to display files** (disrupts the user's screen).
- **Restate the relevant project rules verbatim in the prompt.** Agents start with no prior context and won't follow rules they don't see.

## 7. Environment

- Never modify PATH manually. If the project has special path or environment requirements, ask the user the first time, then save them to memory for that project so subsequent sessions pick them up automatically.

## 8. Documentation directory layout (universal)

- `docs/` is **gitignored** — used for personal notes, scratch work, drafts. Not committed.
- `design/` is **tracked**, but you do **not** add files to it without explicit user confirmation. Design docs are deliberate artifacts.
- Files specific to a particular ticket (continuation prompts, mid-flight notes, ticket-local plans) go into the **ticket's local storage directory** (`~/.claude/ticket-active/<TICKET>/`), not into `docs/` or `design/`.

## 9. Automated PR review

- **CodeRabbit is OFF** — the subscription was cancelled 2026-07-17. Do not wait for it, do not post `@coderabbitai review`, and do not treat its absence on a PR as a problem. (Greptile is under consideration; nothing is decided.)
- **The review backend is per-project config, not a fixed tool.** `[pr_review] backend` in `.project-conf.toml` selects it: `claude` (Claude's own `/code-review`), `coderabbit`, or `greptile`. Both lyos repos are on `claude`. Switching later is a one-line config change — do not hard-code a tool name into a workflow.
- `/simplify`'s pre-commit role is to preempt review findings, not to substitute for the actual review.
- When a project has multiple remotes, **prefer the GitHub remote** for any hosted review bot. Bot reviews do not work on Bitbucket; if Bitbucket is the only remote, factor that into the review plan separately.

## 10. Adding a new rule — where it lives

- **Project-specific operational tip or bug record** → `feedback_*.md` in this project's memory dir; index it in `MEMORY.md`. Default home for new learnings.
- **Project-specific rule every session must follow** → the project-specific section of this `CLAUDE.md`. Delete the memory file if it would duplicate.
- **Universal rule applying to every project of Ian's** → edit the **reference copy in
  `ticket-plugin`** (slopstop), then propagate to the other five. Don't drift one project's
  universal block.

**`ticket-plugin/CLAUDE.md` is the reference copy.** The other five carry byte-identical
mirrors of the marked block. Edit there and propagate outward — never edit a mirror, and never
propagate from one. Fitting home: slopstop is the tool these rules run on.

The six: `ticket-plugin` (slopstop, **reference**), `lyos/mobile-v2`, `lyos/server-v2`,
`louis14`, `mazzy` (mazarin), `sophie`.

**Mirroring is mechanical — do not hand-copy.** The block is delimited by
`<!-- BEGIN UNIVERSAL SECTION -->` / `<!-- END UNIVERSAL SECTION -->` markers, so:

```bash
# 1. extract from the reference. The ^...$ anchors matter: the marker names also
#    appear in this prose, and an unanchored pattern terminates on them early
#    (it silently yields ~6 lines instead of the whole block).
awk '/^<!-- BEGIN UNIVERSAL SECTION -->$/,/^<!-- END UNIVERSAL SECTION -->$/' \
    ~/ticket-plugin/CLAUDE.md > /tmp/UNIVERSAL.md

# 2. replace the marked region in each mirror, then verify — all six must print one hash:
for f in ~/ticket-plugin/CLAUDE.md ~/lyos/mobile-v2/CLAUDE.md ~/lyos/server-v2/CLAUDE.md \
         ~/louis14/CLAUDE.md ~/mazzy/CLAUDE.md ~/sophie/sophie/CLAUDE.md; do
  awk '/^<!-- BEGIN UNIVERSAL SECTION -->$/,/^<!-- END UNIVERSAL SECTION -->$/' "$f" | md5 -q
done | sort -u   # exactly one line = in sync
```

A project-specific section may deliberately **override** a universal rule (e.g. mazzy's
"Pre-commit (overrides universal §1)"). That is fine and belongs *outside* the markers — the
marked region must stay byte-identical everywhere.

Promotion is one-way: memory → project-specific → universal. Rules go up when they prove durable.

<!-- END UNIVERSAL SECTION -->

---

# Slopstop-Specific Declarations

## This repo is the tool the other projects' rules run on

A change here changes how every other project's ticket flow behaves. The universal
block above is not decoration: the skills in this repo are what enforce it, so a
rule and its implementation can drift apart. When they disagree, say so rather
than quietly following one.

## Propagating the universal block (this repo is the reference)

§10 says to edit the reference and propagate. This is how. Do not improvise it —
the obvious approaches are silently wrong, and the failure produces a
plausible-looking file rather than an error.

**Edit `CLAUDE.md` here, between the markers. Then run this.** It is idempotent,
so running it when nothing changed is a safe way to check the mirrors agree.

```python
#!/usr/bin/env python3
"""Propagate the universal block from this reference to the five mirrors."""
import hashlib, pathlib, sys

BEGIN = "<!-- BEGIN UNIVERSAL SECTION -->"
END   = "<!-- END UNIVERSAL SECTION -->"
REFERENCE = pathlib.Path.home() / "ticket-plugin/CLAUDE.md"
MIRRORS = [pathlib.Path.home() / p for p in (
    "lyos/mobile-v2/CLAUDE.md", "lyos/server-v2/CLAUDE.md",
    "louis14/CLAUDE.md", "mazzy/CLAUDE.md", "sophie/sophie/CLAUDE.md")]

def bounds(lines, path):
    """Whole-line matches only, and exactly one of each. See the trap below."""
    b = [i for i, l in enumerate(lines) if l == BEGIN]
    e = [i for i, l in enumerate(lines) if l == END]
    if len(b) != 1 or len(e) != 1 or b[0] >= e[0]:
        sys.exit(f"{path}: need exactly one BEGIN and one END line, in order "
                 f"(got {len(b)}/{len(e)})")
    return b[0], e[0]

ref = REFERENCE.read_text().split("\n")
i, j = bounds(ref, REFERENCE)
block = ref[i:j+1]

for m in MIRRORS:
    lines = m.read_text().split("\n")
    a, z = bounds(lines, m)
    m.write_text("\n".join(lines[:a] + block + lines[z+1:]))

hashes = set()
for f in [REFERENCE, *MIRRORS]:
    lines = f.read_text().split("\n")
    a, z = bounds(lines, f)
    hashes.add(hashlib.md5("\n".join(lines[a:z+1]).encode()).hexdigest())
if len(hashes) != 1:
    sys.exit(f"MIRRORS DISAGREE: {hashes}")
print(f"in sync: {hashes.pop()}  ({len(block)} lines x {len(MIRRORS)+1} files)")
```

### ☠️ The trap: match the markers as WHOLE LINES

**The marker names appear inside §10's own prose describing them.** Anything that
matches them loosely will hit those mentions first and stop at the wrong place —
silently, with no error:

| approach | what happens |
|---|---|
| `awk '/BEGIN/,/END/'` | terminates on the END quoted in §10 — extracts **6 lines, not ~118** |
| `s.index(END, i)` in Python | splices at that same quoted marker — **duplicates content into every mirror**; on the first attempt sophie lost its declarations entirely |
| `awk '/^<!-- BEGIN UNIVERSAL SECTION -->$/,/^<!-- END UNIVERSAL SECTION -->$/'` | correct — anchored to whole lines |
| `l == BEGIN` on split lines (above) | correct, and asserts exactly one of each |

Both wrong versions bit during the 2026-07-17 mirror. Neither raised anything;
the tells were a hash mismatch and files inexplicably growing. Hence the
`bounds()` assertion: a file with 0 or 2+ markers is a corrupted mirror, and the
script must refuse rather than guess.

### Landing it

Ian's rule (2026-07-17): **repos with a clean master → commit straight to master.**
For `mobile-v2` and `server-v2` → commit to master, then carry it into the feature
branches. Use `git merge master`, not rebase: those branches are pushed and often
have open PRs, so a rebase needs `--force`, which universal §3 forbids without an
explicit ask.

Push to **both** remotes where two exist (mobile-v2 and server-v2 have
`mycopy` + `origin`).

### Two things that will waste your time

- **Overrides belong OUTSIDE the markers.** A project may deliberately override a
  universal rule — `mazzy`'s `## Pre-commit (overrides universal §1)` is the live
  example. The marked region stays byte-identical everywhere; the override sits in
  the project-specific section after the END marker. This section you are reading
  is itself outside the markers, which is why it is not mirrored.
- **`skip-worktree` can hide a mirror from you.** `~/mazzy/CLAUDE.md` had the bit
  set: the file on disk was a stale pre-refactor copy with no universal block,
  `git status` reported clean, and an edit there would have been swallowed with no
  diff. Cleared 2026-07-17. If a CLAUDE.md looks inexplicably out of date, check
  `git ls-files -v CLAUDE.md` — `S` = skip-worktree, `h` = assume-unchanged.
