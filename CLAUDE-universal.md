<!-- This file is MIRRORED.  Do not edit it here unless this repo is the
     reference (slopstop / ticket-plugin).  Edit the reference copy, then run
     tools/fleet-sync/migrate-universal-block.py --apply to propagate.
     Imported by CLAUDE.md via a single `@CLAUDE-universal.md` line. -->


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
- **One ticket, one branch, one PR — and always cut the branch from the integration
  branch** (`master` or `main`, per project). Never branch off another feature branch.
  A nested branch inherits its parent's commits, so the PR silently carries work
  belonging to a different ticket: the diff, the review, and the test evidence all
  cover two tickets at once, and merging it lands the parent's work under the child's
  ticket number. If you need something that only exists on an unmerged branch, wait
  for it to merge or raise the dependency — do not stack.
- **The expected shape is two commits: the RED test commit, then the implementation.**
  More is fine when the work genuinely warrants it, but every commit must belong to
  the branch's one ticket. A cleanup you noticed in passing goes on its own branch —
  including when it is a one-line deletion, and including when it would otherwise ride
  along inside the red-test commit.
- **Verify the branch topology before opening the PR:** `git log <integration>..<branch>`
  must list only this ticket's commits. If it shows a parent ticket's work, rebase onto
  the integration branch — don't merge it and don't explain it away in the PR
  description. Re-run the tests after rebasing: results gathered on the stacked branch
  covered the parent's changes too, so they never established that this ticket's change
  is green on its own.

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

- **Claude `/code-review` is the base review, and the only one that gates a merge.** Every PR gets it; a PR is reviewed once it is clean. Nothing else is required.
- **Every project must set `[pr_review] backend = "claude"` explicitly.** `coderabbit` is the *default*, so a missing `[pr_review]` block is the bug, not the safe state: it sends `:pr` into Step 6-cr's poll (60s × 20), which under CodeRabbit's rate limiting usually burns 20 minutes and returns nothing. `backend` accepts `claude` | `coderabbit` | `greptile` — it stays per-project config, so never hard-code a tool name into a workflow.
- **CodeRabbit is opportunistic: read it if it is already there, never wait for it.** It reviews free on public repos but rate-limits hard, so most PRs get nothing. Before merging, look **once**, and sort what you find three ways — a real review (work its findings: verify each against the actual code, apply the real ones, state which you refuted and why); a non-review notice (match `Review limit reached`, or `auto reviews are disabled` when the base is not the default branch — **neither is a clean pass**); or silence. The last two are the same action: merge on the Claude review. Do not post `@coderabbitai review` to force one — it spends rate-limit budget on a review that lands after you have merged.
- `/simplify`'s pre-commit role is to preempt review findings, not to substitute for the actual review.
- When a project has multiple remotes, **prefer the GitHub remote** for any hosted review bot. Bot reviews do not work on Bitbucket; if Bitbucket is the only remote, factor that into the review plan separately.

## 10. Adding a new rule — where it lives

- **Project-specific operational tip or bug record** → `feedback_*.md` in this project's memory dir; index it in `MEMORY.md`. Default home for new learnings.
- **Project-specific rule every session must follow** → the project-specific section of this `CLAUDE.md`. Delete the memory file if it would duplicate.
- **Universal rule applying to every project of Ian's** → edit **this file in the
  `ticket-plugin` (slopstop) repo**, which is the reference copy, then propagate. Don't
  drift one project's copy.

**This file is mirrored, and `ticket-plugin`'s copy is the reference.** Every other
project carries a byte-identical `CLAUDE-universal.md` at its repo root, pulled into
context by a one-line `@CLAUDE-universal.md` import in that project's `CLAUDE.md`. Edit
the reference and propagate outward — never edit a mirror, and never propagate from one.
Fitting home: slopstop is the tool these rules run on.

**The fleet list is not repeated here.** It lives in one place —
`tools/fleet-sync/fleet.py` in the slopstop repo — and every sync/audit script
imports it from there. Enumerating the repos in this file would duplicate that
list into every copy of it (universal §5), and a mirrored file naming other
projects also breaks any repo whose own rules forbid referencing a sibling.

**Propagation is mechanical — do not hand-copy.** The unit is this whole file, so
propagating is a copy and verifying is a hash compare:

```bash
python3 ~/ticket-plugin/tools/fleet-sync/migrate-universal-block.py --apply    # propagate
python3 ~/ticket-plugin/tools/fleet-sync/migrate-universal-block.py --verify   # one hash = in sync
```

A project may deliberately **override** a universal rule — the conventional form is a
section headed `## <Topic> (overrides universal §N)`. Overrides live in that project's
own `CLAUDE.md`, below the import — never in this file, which must stay byte-identical
everywhere. Because the import sits above them, an override is read after the rule it
overrides.

Promotion is one-way: memory → project-specific → universal. Rules go up when they prove durable.
