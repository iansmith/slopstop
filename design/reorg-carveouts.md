# Reorg carve-outs — content that must be re-homed before phase 3 deletes its source

> Provenance: Claude · 2026-08-06 · branch `minor_fix`
> Companion to `design/prd-slopstop-reorg.md`.
>
> **STATUS: phases 1–4 are complete. This file has served its purpose and is now a
> record, not a blocker.** Individual `- [ ]` boxes below were not all ticked as work
> landed — read the commit history, not the checkboxes, for what actually happened. Every
> item was either absorbed (adversary machinery and `--frozen` threading into `:run`;
> the two mechanical gates into workers), resolved by a decision recorded inline, or
> deliberately dropped with the reason stated.
>
> Two things here are still genuinely open and are **not** phase work:
> `:run` does not verify `$IN_PROGRESS_LABEL` exists at intake (a mis-bootstrapped
> project dies at stage 3 after `investigate` has run), and `--interactive` is specified
> but unimplemented by Ian's deferral.

Charter C8: *"A deletion that leaves references behind is not done."* The inverse also
holds — a deletion that drops content nothing else picked up is not done either.

Each entry below is substance found in a phase-1 source file that does **not** belong in
the extracted worker, and therefore has no home yet. **Phase 3 must not delete a source
file until every carve-out from it is landed somewhere.** Check them off here.

---

## From `skills/plan/references/plan-adversary-gaps.md` → owner: `:run` orchestrator

- [ ] **Post-verdict gap-test machinery.** The interactive `add all / add selected / skip`
      prompt over the adversary's findings; the rule that a gap test naming a
      not-yet-existing surface is created as a **stub**; the RED re-verification run after
      adding gap tests with `revise / continue / abort`; and the
      `git commit -m "[$TICKET] Phase 0: adversary gap tests"` step.
      **This is the largest carve-out.** The `adversary` worker returns findings and is
      forbidden to write, commit, or prompt — so all of this is orchestrator work now.
- [ ] **Adversary-unavailable fallback** — "fall back to an inline checklist" is a caller
      decision, meaningless inside the worker.
- [ ] **Verdict handling + the argue-don't-ignore rule.** PASS advances; FAIL at round 3
      goes to a human; and findings the caller disagrees with must be **argued in the
      correction note, not silently ignored**. That last one is real discipline and
      currently has no home.
- [ ] **Caller branch logic changes shape.** The old plan path emitted prose
      (`N gaps found`); the consolidated worker emits `ADVERSARY PASS` /
      `ADVERSARY FAIL: n` / `ADVERSARY GOAL DEFECT`. Any caller must branch on the new
      verdict line.

## From `tickets-adversary.md` / `single-ticket-adversary.md` → owner: every orchestrator launch site

- [ ] **Tier resolution knowledge.** `[stage_tiers].ticket_adversary` → `[tiers]`, the rule
      that **the adversary runs one tier above the work it checks**, and the note that
      `[fleet.agents].adversary_effort` does *not* govern this spawn. Deliberately excluded
      from the worker (model is passed by the caller), so it must land at each launch site.
      References `design/agent-effort-capability.md` and issue #450.

## From `skills/plan/references/plan-adversary-gaps.md` → owner: `:pr` docs, or drop deliberately

- [ ] **Vacuity-gate cross-reference (BILL-343).** The note that the false-negative attack
      vector is blind to tests written *after* the adversary pass, which `:pr` Step 2f's
      vacuity gate covers. Commentary about another skill's coverage. Verify it exists in
      the slop/vacuity documentation; if not, either re-home it or drop it on purpose.

## From `skills/pr/references/pr-slop-detection.md` → owner: `:run` orchestrator

- [ ] **`--frozen` must be carried forward.** `slop-check` takes the Phase 0 sha as a
      required *input* and is explicitly forbidden to derive it (same reason `review` is
      given its scope explicitly — a fork has no conversation history). The orchestrator
      must thread the sha from the `red-tests` worker's return value into the `slop-check`
      launch. Nothing else does this now.

## Two mechanical gates — RESOLVED 2026-08-06 (Ian): both become workers

Ian's call: *"Vacuity and CC gate should become workers and should behave (and be
written/invoked) just like the other workers."* PRD D8 revised seven → nine.

- [x] **The vacuity gate (`:pr` Step 2f, BILL-343)** → `skills/vacuity-check/`.
      Complementary to `slop-check`, not redundant: `slop-check` asks the vacuity question
      as a reasoned read, `vacuity-check` runs the test at the base commit and proves it.
- [x] **The cyclomatic-complexity gate (`pr-cc-gate.md`, 357 lines)** → `skills/complexity-check/`.

**Residual risk — the mechanics live mostly in doomed test files.** Both gates' precise
behavior is documented more exactly in the tests than in the prose:
`tests/test_bill343_behaviors.py` (432 lines: AST span analysis, node-id selection, pytest
exit-code 4-vs-2, base-sha re-runs, conftest copying) and `tests/test_cc_*.py` (lizard
`--csv` invocation, exit-zero-on-unmeasurable-input, line-range-overlap exemption,
inclusive-lower-bound thresholds). Both extraction agents were pointed at those files
explicitly and asked to report what existed ONLY there.
**Phase 3 must not delete those test files until that report is checked off.**

## From the deleted `tests/test_cc_*.py` → owner: NOBODY. Decision needed.

- [x] **Cross-document agreement on the CC defaults — RESOLVED 2026-08-06 (Ian).**
      `test_cc_thresholds.py` guarded that the 5/10 defaults *agree* across `CONFIG.md`,
      `design/project-conf-options.md`, and `skills/pr/references/pr-test-gates.md`. No
      worker skill can hold a four-document consistency check, so the fix is to remove the
      disagreement rather than police it:
      - **The orchestrator holds the operative defaults** and is the sole reader of
        `.project-conf.toml` (charter C3a). `complexity-check` was amended to require all
        four thresholds as arguments and to block rather than read config itself.
      - **`CONFIG.md` is the one human-readable home.**
      - [ ] **Phase 4 must delete the restatements** in `design/project-conf-options.md`
        and `skills/pr/references/pr-test-gates.md` (the latter dies with `:pr` anyway).
        `.project-conf.toml.example` may keep them as commented illustration.

### `CONFIG.md` keys `complexity-check` depends on — do NOT remove in phase 4

All under `[autonomous]` (`CONFIG.md:483–485`, `:496`):
`cc_warn_threshold` (5) · `cc_reject_threshold` (10) · `cc_exempt_pre_existing` (false) ·
`file_nloc_warn_threshold` (400, `0` disables).

### Deliberate drops from `pr-cc-gate.md` — confirmed, not oversights

- **The run-time `pip install lizard` cascade.** It ended in `|| true` with errors
  discarded, which is the cheapest untraceable way to disable the gate; a worker silently
  mutating the environment is worse than reporting `CC SKIPPED` with a stated fix.
  `install-for-claude-desktop.sh:119–125` already installs lizard at *install* time, which
  is the right place for it.
- **The `grade=E` report field.** Defined nowhere in the repo — it appears only in
  `pr-cc-gate.md`'s sample output and its signals JSON. Dropped rather than propagated.
- **`bin/lizard` does not exist.** The brief that launched the extraction claimed a
  vendored binary; `bin/` holds only `_slopstop-lib.sh` and `pre-commit-file-size.sh`. The
  worker documents the `.venv/bin/lizard` → `venv/bin/lizard` → PATH → `python3 -m lizard`
  cascade instead.

## Phase 4: the installer help text enumerates deleted commands

- [ ] `install-for-claude-desktop.sh`'s closing `cat <<EOF` block prints a per-command help
      listing (`/slopstop-start`, `/slopstop-plan`, `/slopstop-pr`, `/slopstop-merge`,
      `/slopstop-archive`, `/slopstop-document`, …). Every one of those is deleted in
      phase 3. The block must be rewritten, not just the `SKILLS` array.

## Phase 3 references sweep — surfaced by the `:tickets` rewrite (2026-08-06)

- [ ] **`skills/tickets/references/tickets-adversary.md` is dead on arrival.** Fully
      superseded by `skills/adversary/SKILL.md`; its checks A–G map onto the caliber
      families and its verdict handling moved into the loop `:tickets` now owns. Nothing
      links to it.
- [ ] **The old adversary refs' `[fleet.agents].adversary_effort` note, and the pointers to
      `design/agent-effort-capability.md` and issue #450, have no home.** `worker-launch.md`
      settles effort as session-inherited and not per-stage configurable. Either delete
      those pointers or record the limitation where `agent-effort-capability.md` can be
      found — **do not leave them claiming a capability that is not reachable.**
- [ ] **Sweep `run.md` mentions** out of `ticket-standard.md` and
      `tickets-create-dispatch.md` (D5 retires it).
- [ ] **The old `:tickets` "Effort" and router-status paragraphs** have no successor —
      confirm that is intended, since D3 unwires the router.

## Surfaced by the `:run` rewrite (2026-08-06) — two need Ian's decision

- [ ] **The ticket-rewrite path has no home. DECISION NEEDED.** The old `:run` could
      diagnose a *ticket defect* after two failed attempts and rewrite the ticket, gated by
      a huge-tier delta check (`[stage_tiers].rewrite_delta_check`) before relaunch. There
      was also a human-authorized *salvage* path. Neither survives. The new `:run`
      represents failure as: stop that ticket, close its span `failed`, escalate to the
      human, keep the other tickets running.
      → If ticket rewrite should survive, it is **`:tickets`' work, not `:run`'s** — a
      ticket defect is a ticket-authoring problem. Decide before phase 3 deletes the
      source, because `rewrite_delta_check` is also a live `[stage_tiers]` key.
- [ ] **Branch-type heuristics have no home.** `skills/start/references/start-branch-type-heuristics.md`
      holds the label/title → branch-type table behind `[autonomous].branch_type`. `:run`
      stage 3 only refers to the shape `<type>/<TICKET>`; the table itself dies with
      `:start`. Either re-home the table or drop `branch_type` from `CONFIG.md` — **do not
      leave a config key whose behavior is undefined.**
- [ ] **`:start`'s layout-mismatch scan was not carried over.** It existed because `:start`
      was a ticket's entry point into the tree. If it should live on, it belongs at `:run`
      stage 1 (`intake`). Confirm drop or re-home.
- [x] **DoD scoring** — `:run` had inlined the verdict vocabulary; replaced with a pointer
      to `skills/run/references/dod-scoring.md`, which survives. One definition restored.
- [x] **Tracking-dir resolution** — compressed inline into `:run` (correct: D9 makes the
      orchestrator the sole resolver and every other consumer is deleted). Verified the
      load-bearing `ROOT="$(dirname "$(git rev-parse --git-common-dir)")"`-not-cwd check
      survived, along with the `~/.claude/` tier-3 guard.

## 4-state workflows: `:run` may land the ticket in the wrong state (2026-08-06)

- [ ] **`:run` stage 14 says "advance the ticket one state".** That is correct for a 3-state
      workflow — this repo's, and the documented default. In a **4-state** workflow (one
      with `[status_labels].in_review`), advancing one state after a *merge* lands the
      ticket in `in_review`, not done.
      The old `:merge` computed the post-merge state through a state machine
      (`merge-state-machines.md`, `merge-ticket-system.md`) and `[autonomous].merge_target_state`
      existed precisely to skip intermediates. All of that is deleted, and the key was
      removed 2026-08-06 because nothing read it.
      → This is now a **`:run` behavior question, not a config one**: after a merge the
      ticket should go to its terminal state, not the next one. Fix in `:run`, do not
      reintroduce a key.

## Deferred by Ian, 2026-08-06: `--interactive` is scaffolding, not a feature

- [ ] **`/slopstop:run --interactive` is declared but not implemented.** Ian: *"We can
      postpone the implementation of the --interactive version, that is perfectly fine and
      it is of considerably less value."*
      What exists: the flag, `$MODE` derived from it, the per-gate behavior table in
      `:run`, and `--mode $MODE` passed to `review`. What does not exist: the actual
      ask-and-wait handling at each gate.
      **Autonomous is the real path and is fully specified.** Do not treat the mode table
      as implemented behavior, and do not let a future pass quietly delete the flag either
      — the gate list in it is the spec for whenever this is built.

## `LOCAL_RULES_REPOS` is not retirable by BILL-462 (corrected 2026-08-06)

- [x] I suggested BILL-462 might retire it. **Wrong.** It governs `CLAUDE-universal.md`,
      not `.project-conf.toml`, and its only function is suppressing
      `migrate-universal-block.py`'s guard against propagating into a repo where the rules
      file is gitignored. `lyos/mobile-v2` and `lyos/server-v2` gitignore the rules because
      Ian will not impose his working process on a repo shared with another contributor —
      a decision no amount of config layering touches. `fleet.py` already states the two
      gitignore decisions merely coincide and "a future divergence is legitimate."
      Ticket corrected.

## Ordering constraint: `review`'s frontmatter is pinned by a live test

- [ ] **`skills/review/SKILL.md` must lose `context: fork`, `model`, `background` and
      `effort`** to match the worker contract (D4 — model is passed by the caller so
      per-project `[tiers]` reaches it). It **cannot change yet**:
      `tests/test_bill436_behaviors.py` asserts `context: fork` is present, and
      `install-for-claude-desktop.sh` carries a comment saying withholding `review` is what
      forces a human to type `/code-review` on every PR.
      → Do this in **phase 3, in the same commit that deletes the test suite**, not before.
      `review` is also the only worker whose caller (`:pr` Step 6-claude) still invokes it
      as a top-level fork, so that call site dies in the same pass.

---

## Python inventory (charter C13 — update at every phase boundary)

Started at **45 tracked files / 7,167 lines**, of which 78% was test machinery or the
metrics collector.

| group | files | lines | status |
|---|---|---|---|
| `tests/` | 24 | 4,487 | deleted in phase 3 |
| `tools/metrics/` | 13 | 1,093 | deleted in phase 3 |
| `tools/fleet-sync/` | 4 | 1,016 | **KEEP** — `CLAUDE.md` §10 mandates running these |
| ~~`tools/mcp-go-edit/`~~ | ~~1~~ | ~~286~~ | **deleted 2026-08-06** (Ian) |
| ~~`baseline/`~~ | ~~3~~ | ~~285~~ | **deleted 2026-08-06** (Ian) |

**End state: 4 files, 1,016 lines — all of it `tools/fleet-sync/`.** No Python remains that
exists to serve a test.

`tools/fleet-sync/` survives because it is operational tooling Ian runs by hand:
`fleet.py` (84 — the single home of the repo list), `migrate-universal-block.py` (442 —
propagation), `sync-project-conf.py` (271), `audit-project-conf.py` (219).

- [ ] **Phase 3 note:** `audit-project-conf.py`'s `DEAD_KEYS` list exists because
      `tools/metrics/conventions.load()` raised on those keys. It is only a comment
      reference — nothing breaks — but the rationale evaporates when metrics is deleted.
      Re-read that comment and either restate the reason or drop the list.
- [ ] **`conftest.py` is clean to delete.** All 24 importers are inside `tests/`; nothing
      outside imports it. `CSV_COLUMNS` and the `changed_line_ranges`/`touched` overlap
      predicate are already restated in `skills/complexity-check/SKILL.md`.

### Deletion fallout already handled (2026-08-06)

- `.mcp.json` deleted — `go-edit` was its only server, leaving an empty shell.
- `baseline/**` removed from the ignore list in `skills/pr/references/pr-size-classifier.md`.
- `CHANGELOG.md` entries for both are **left intact** — a changelog records what happened.

- [x] **`design/design-brief-lifecycle-metrics.md` — RESOLVED 2026-08-06 (Ian).** Moved to
      gitignored `docs/`, `git rm`'d from `design/`, with a superseded banner separating its
      dead design direction from its still-valid findings. Ian: write a replacement brief
      once the reorg lands. Its unanswered open question 2 is now PRD **R3a**.
- [ ] **`.claude/settings.local.json` still lists `go-edit`** as an enabled MCP server.
      Gitignored and local to Ian's machine, so harmless but stale — his to clean.

---

## Open risk this file records

The three adversary sources were **not** three implementations of one method by accident —
`plan-adversary-gaps.md` was roughly 40% orchestrator actions rather than adversary
instructions. That is why it read as a separate implementation. The consolidation is sound,
but it means the orchestrator inherits real work that previously hid inside a "reference
file for an adversary", and that work is easy to lose.
