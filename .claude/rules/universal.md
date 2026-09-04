<!-- This file is MIRRORED.  Do not edit it here unless this repo is the
     reference (slopstop / ticket-plugin).  Edit the reference copy, then run
     tools/fleet-sync/setup-project.py --apply to propagate.
     Loaded automatically from .claude/rules/ — there is no import line. -->


# Universal Project Rules

These rules apply across all of Ian's projects unless this CLAUDE.md explicitly overrides them.

## 1. Pre-commit

- **Quality review happens once, at PR time — not before every commit.** `:pr`'s review gate reads the whole branch diff, so nothing escapes by being committed early. Commit freely; the gate is at the merge. (Measured 2026-08-04: a multi-agent cleanup pass before every commit cost 13–30 min and missed the most serious defect in its own diff, which a single review pass found in ~4 min. The rule this replaces called that pass "cheap" — it was written when it was one agent.)
- Run the project's build + targeted tests (the package or area you touched) before commit. Run the full suite only when touching shared/cross-cutting code.
- Commit, then push — only after the above are clean. **If the project has multiple remotes, push to all of them.**
- **A project with no test suite is a deliberate, documented exception — never a default.** It must say so in its own `CLAUDE.md`, under a heading naming this section, and state what it validates with instead. "There are no tests here" is a claim that needs a reason and an owner; discovering it by finding no `tests/` directory is not the same thing.

## 2. Tests

- **Tests-first for new behavior AND for fixes.** For new behavior, write the test describing the desired contract; confirm it's red **for the right reason** before implementing. For bug fixes, write a test that reproduces the bug — it must be red before the fix and green after. Trivial tweaks, copy changes, and pure refactors are exempt.
- **A failing test is signal, not chore.** Investigate the root cause before changing anything. Never delete a test, narrow an assertion, call `Skip()`, or cite an unverified "flake" to silence it. "Known flake" is a label, not an explanation.

(Test scope before commit is covered by §1. Project-specific guidance on test runtime and scoping lives in each project's CLAUDE.md.)

**These rules bind wherever tests are the verification mechanism, which is nearly everywhere.** A project that has genuinely replaced them — see §1's last bullet — still owes the same guarantee by other means: something must fail loudly, before merge, when the change is wrong. What must never happen is the guarantee quietly going missing because the mechanism did.

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

- **The gate is a review by a context that did not write the code, and every PR gets one.** In an autonomous run that is two things, both mandatory: the stage-10 `review` loop, running to `REVIEW CLEAN` and capped at 5 rounds; then stage 10b handoff verification — fresh checkers at the tier above, fed artifacts only and never the agent's own claims, producing a blessing bound to the branch tip SHA. **Which checkers is decided by the ticket's mode, not by cost:** a normal ticket gets both a `review` and a requirements adversary; a *refactor* ticket gets the reviewer only (there are no new requirements to check against), and a *backfill* ticket gets the adversary only (there is no new production code to review). One of the two is always wrong for an invariant ticket, and skipping it is the structural argument — never a saving. The rule underneath both is **the session that wrote the code never reviews it, and never decides which criticisms of it are valid.** It has an incident behind it: PR #411 recorded a passing review the authoring session had performed on its own work. The isolation is real and comes from the **launch form**: every worker runs as a subagent via `Agent()` (`worker-launch.md`), which gives it its own context window and no access to the conversation that wrote the code. **Corrected 2026-08-10:** this bullet used to say the worker *"carries `context: fork`, … rather than by a flag anyone can forget."* No slopstop skill declares `context: fork` — `grep -rn "context: *fork" skills/` returns nothing — so that named the wrong mechanism and, worse, offered false reassurance: invoking `Skill(slopstop:review)` **inline** instead of through `Agent()` would run the review in the calling context, which is exactly the PR #411 arrangement. It is enforced by the launch form, and the launch form is a step that can be got wrong. Launch workers per `worker-launch.md`; never invoke a review skill inline.
- **Claude `/code-review` CAN be invoked by an agent**, as `Skill(skill: "code-review", args: "<PR#>")`. **Corrected 2026-08-27**, and it replaces a bullet that asserted the exact opposite: that it carries `disable-model-invocation`, that *"a skill, a subagent, or a headless run cannot"* launch it, and that *"any call site that appears to invoke it is **inert**"* — citing a harness check dated 2026-08-09. Re-tested on 2026-08-27 by a subagent reviewing a consuming-project PR: the call was accepted, ran as forked execution, and returned real findings, among them four false claims in the authoring session's own doc comments. Whether the old bullet was wrong when written or the harness changed under it cannot be told apart from here; what is known is that it does not hold now, and that it stood unchallenged for eighteen days. Whether it cost anything in that window is unknown — nobody may have tried — so the case for fixing it rests on it being false and cheap to check, not on damage anyone can point to.
  - Verified is the **plain** form, invoked through `Skill()` from a subagent. `/code-review ultra` — the multi-agent cloud review — is billed per run and was **not** part of that check. Leave it to the user to launch until someone verifies otherwise, and never spend it on a guess.
  - **The isolation requirement above is untouched, and it is the half that matters.** That an agent *may* make the call changes nothing about *from where*: invoking `/code-review` inline in the session that wrote the code is still precisely the PR #411 arrangement this section exists to prevent. Launch it from an `Agent()` whose context did not write the diff.
  - The durable lesson is not about this command. A written-down claim about what the harness forbids can be wrong when written **or** go stale afterwards, and from the outside those look identical — which is why "it was verified once, on a date" is not the reassurance it reads as. This one was believed because it was confident, specific, and dated. When such a claim is what stops you doing something useful, re-test it before repeating it; here the test was a single call.
- **`[pr_review] backend` does not choose who reviews.** The forked `review` worker runs on every PR whatever the value is. The key selects only *whose bot comments* the bot-read step goes looking for; it accepts `claude` | `coderabbit` | `greptile`, stays per-project config, and is never hard-coded into a workflow. A project with no `[pr_review]` block still gets the full review gate — the default only changes which bot is read.
- **Bot reviews are opportunistic: read them if already there, never wait.** CodeRabbit reviews free on public repos but rate-limits hard, so most PRs get nothing. Before merging, look **once**, and sort what you find three ways — a real review (work its findings: verify each against the actual code, apply the real ones, state which you refuted and why); a non-review notice (match `Review limit reached`, or `auto reviews are disabled` when the base is not the default branch — **neither is a clean pass**); or silence. The last two are the same action: proceed on the `review` worker's verdict, which is the gate regardless. Do not post `@coderabbitai review` to force one — it spends rate-limit budget on a review that lands after you have merged.
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
propagating is a copy and verifying is a byte compare. `setup-project.py` owns both;
it does more than the rules (skills, `.gitignore`, `.project-conf.toml`), and this
file is one of the things it brings into line:

```bash
python3 ~/ticket-plugin/tools/fleet-sync/setup-project.py --repos <repo> --apply   # propagate
python3 ~/ticket-plugin/tools/fleet-sync/setup-project.py --repos <repo>           # verify — writes nothing
```

Omit `--repos` for the whole fleet. **Propagation stays the maintainer's call**: the
repos sit in different states, several are shared with other contributors, and being
behind is a normal condition rather than a fault to auto-correct.

A project may deliberately **override** a universal rule — the conventional form is a
section headed `## <Topic> (overrides universal §N)`. Overrides live in that project's
own `CLAUDE.md`, below the import — never in this file, which must stay byte-identical
everywhere. Because the import sits above them, an override is read after the rule it
overrides.

Promotion is one-way: memory → project-specific → universal. Rules go up when they prove durable.
