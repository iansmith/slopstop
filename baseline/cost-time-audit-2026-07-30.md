# slopstop cost + latency audit — 2026-07-30

**Question asked:** why is slopstop painfully slow, why are token costs out of sight, what does
ECC do differently, and what should we change? Stated preference: **optimize TIME over COST**
when they trade off.

**Method:** measured 1,440 real sessions / 385,137 assistant turns / 3.6 GB of transcripts from
`~/.claude/projects`, rather than reasoning from skill inspection. Scripts preserved in
`scratch/cost-audit-2026-07-30/` — see [Reproducing](#reproducing) at the bottom.

**Comparison target:** `github.com/affaan-m/ECC` (86 MB, 281 skills, 64 agents, 96 commands,
20 hooks, ~10,576 lines of hook JS) plus <http://ecc.tools>.

> ⚠️ Cost figures use a static rate table (no >200K-token tier, no 1h-cache tier, Fable priced
> as Sonnet-class). Treat absolute dollars as ±25%. The **ratios** are what the argument rests
> on, and those are robust.

---

## 1. The headline: cost is context size × session length, on Opus

Median prompt tokens per assistant turn, bucketed by position in the session
(five main projects: mobile-v2, louis14, mazzy, sophie, ticket-plugin):

| Turn index | n turns | Median prompt | p90 | Cost/turn @ Opus cache-read |
|---|---|---|---|---|
| 1 | 660 | 37,769 | 61,994 | $0.06 |
| 2–10 | 5,822 | 42,998 | 68,288 | $0.06 |
| 11–50 | 24,266 | 68,251 | 103,533 | $0.10 |
| 51–150 | 52,936 | 126,424 | 192,847 | $0.19 |
| 151–400 | 89,931 | 247,329 | 394,371 | $0.37 |
| **401+** | **91,068** | **465,146** | **763,482** | **$0.70 – $1.15** |

**The same turn costs 11–18× more late in a session than early in one.** 91,068 of 264,452
turns in those projects sit at index 401+ → roughly **$60K of ~$150K all-time spend is turns
401+, spent almost entirely re-reading context.**

Latency has the identical cause: a 500k-token prefill is slow even fully cached.
**Time and cost are the same problem here** — which resolves the stated TIME-vs-COST tradeoff:
there isn't one for the main fix.

### Global figures

```
sessions = 1,440        assistant turns = 385,137
uncached input =    140,305,071
output         =    472,766,990
cache write    =  2,288,684,479
cache read     = 91,818,965,489
total prompt   = 94,247,955,039

cache-read share  = 97.4%   <- prompt cache is near-perfect
cache-write share =  2.4%
uncached share    =  0.1%
est. cost         = ~$150,473
```

### Spend by model family (session attributed by dominant model)

| Family | Cost | Share | Sessions | Assistant turns |
|---|---|---|---|---|
| **opus** | **$133,169** | **88.5%** | 576 | 184,163 |
| sonnet | $14,261 | 9.5% | 415 | 125,819 |
| fable | $2,691 | 1.8% | 42 | 17,522 |
| haiku | $353 | 0.2% | 319 | 37,366 |

### Wall clock (sessions ≥ 20 turns, n=622)

| Metric | Median | Mean | p90 | Max |
|---|---|---|---|---|
| Session duration | 3.87 h | 14.19 h | 28.23 h | 485 h |
| Seconds / assistant turn | **42.2 s** | — | **278.7 s** | — |

---

## 2. Theories, scored

### ❌ Theory 1a — "changing models more frequently than we should"

**Refuted.** 84/1440 sessions (5.8%) use >1 model. **118 total switches across 385,137 turns.**
Median 1 switch among sessions that switch at all.

| Switches | n | cacheWrite share | cacheRead share | $/session | $/turn |
|---|---|---|---|---|---|
| 0 | 1,356 | 2.5% | 97.4% | $94.39 | $0.387 |
| 1–2 | 77 | 2.2% | 97.8% | $250.08 | $0.408 |
| 3–9 | 7 | 2.4% | 97.6% | $461.60 | $0.453 |

Cache-write share is flat across buckets — switching is *not* causing cache churn. The rising
`$/session` is confounded: switching happens in long sessions, and length is the real variable
(`$/turn` barely moves).

### ❌ Theory 1b — "clearing context more frequently than we should" → **INVERTED**

**Refuted, and backwards.** Only 106 sessions (7.4%) contain a compact summary; **92.6% never
compact at all.** That is exactly why turns 401+ dominate spend. The correct instruction is
**clear MORE, not less.** Highest-leverage correction in this audit.

### ❌ Theory 2 — "too many skills, even with the spine trick"

**Refuted as a cost driver — the spine trick works better than assumed.** Measured on this repo:

| Quantity | Value |
|---|---|
| skill + ref files listed | 85 |
| **description tokens (what the listing costs every turn)** | **~1,393** |
| full bodies if everything loaded | ~107,457 |
| turn-1 baseline (system + tool schemas + listing + CLAUDE.md + rules) | **37,769 median** |
| slopstop's share of that baseline | ~1.4k = **3.7%** |
| CLAUDE.md + `.claude/rules/repo-conventions.md` | 4,059 + 2,040 = 6,099 |

Lifetime cost of the **entire** baseline ≈ $21,800 (14% of spend). slopstop's skill listing is
~$800 of it. **Deleting skills is not where the money is.**

#### But there IS a true variant, unnamed in the original theory: the refs we *load*

| Skill | Ref lines | ≈ tokens | Sequential `→ Read` directives |
|---|---|---|---|
| `:pr` | 1,850 | ~26,000 | **16** |
| `:plan` | 1,077 | ~15,000 | **16** |
| `:merge` | 840 | ~12,000 | **13** |
| `:run` | 1,084 | ~15,000 | 8 |

Load 26k at turn 200 of a 600-turn session → 26k × 400 remaining turns = 10.4M cache-read
tokens ≈ **$15.60 per `:pr`**, plus **16 serialized round trips ≈ 11 min** at the median 42 s/turn
*before any real work starts*.

**The spine trick optimized the cheap axis (1.4k listing) and left the expensive one untouched.**

### ✅ Theory 3 — "too much in context from tests/checks/gates" — CONFIRMED, dominant

Tool-result volume, five main projects, 47.9M tokens total:

| Tool | Tokens | Share | Calls | Avg | Max |
|---|---|---|---|---|---|
| Read | 17,631,964 | 36.8% | 18,308 | 963 | 24,061 |
| **Bash** | **17,321,511** | **36.2%** | **67,803** | 255 | 7,436 |
| Agent | 3,325,071 | 6.9% | 4,407 | 754 | 11,868 |
| `linear__save_issue` | 2,120,012 | 4.4% | 1,790 | 1,184 | 9,274 |
| `linear__get_issue` | 1,050,372 | 2.2% | 817 | 1,285 | 12,329 |
| Edit | 832,147 | 1.7% | 17,832 | 46 | 29,796 |
| ticket-system MCP (all) | ~5.3M | ~11% | ~5,400 | — | — |

Bash is **52.4% of all 189k tool calls**. Note the *shape*: **no single Bash result exceeded
~7.4k tokens.** This is not one giant test dump — it is **67,803 small ones that never leave**.
Death by a thousand gates, each amplified by every remaining turn.

`:pr` is the worst offender by construction:

- **3 test-suite executions** — Step 0 (full suite), Step 2 (relevant tests), Step 2f
  (changed tests re-run against base)
- **3 independent model passes over the same diff** — Step 1 simplify, Step 2e slop,
  Step 6 code-review
- 15 steps, 16 ref reads

Corroborating signal: `ticket-plugin` has **cw/turn = 11,490** vs ~5,200–7,900 everywhere else
— nearly **2× the cache churn**, exactly what gate-heavy workflows repeatedly invalidating the
cache prefix would produce.

| Project | Cost | Sessions | Turns | prompt/turn | **cw/turn** | out/turn |
|---|---|---|---|---|---|---|
| lyos/mobile-v2 | $40,202 | 220 | 76,937 | 289,898 | 6,783 | 1,233 |
| louis14 | $27,095 | 148 | 61,794 | 249,476 | 5,871 | 1,446 |
| mazzy | $23,005 | 128 | 47,610 | 282,612 | 6,027 | 1,419 |
| sophie | $19,787 | 88 | 42,250 | 324,053 | 5,236 | 1,128 |
| **ticket-plugin** | **$16,302** | 73 | 35,861 | 212,892 | **11,490** | **1,768** |
| mazzy worktree (maz-task2) | $9,607 | 20 | 10,676 | 424,177 | 10,347 | 2,254 |

### ⚠️ Theory 4 — "failed fleet agents cost a lot; use Sonnet 5 not Haiku"

**Cost premise refuted — recommendation still correct, and nearly free.**

| Metric | Value |
|---|---|
| worktree sessions | 406 = 28.2% of sessions |
| worktree spend | $12,700 = **8.4%** of total |
| **Haiku all-time spend** | **$353 = 0.2%** |
| $/worktree-session | median **$2.38**, mean $31.28, **max $1,418.99** |
| models already used in worktrees | haiku 27,624 turns · **sonnet-5 22,151** · opus-4-8 12,053 · fable-5 1,523 |

The long tail is real (median $2.38 → max $1,419), so individual failures *are* expensive.
But small-tier Haiku→Sonnet 5 is ~3.75× on a $353 base → **~$1,300 all-time = 0.6% of spend.**
Under TIME > COST this is a trivial yes. The instinct was right; the magnitude was inverted —
it's cheap, not expensive.

### 🔍 Anomaly to chase

Most expensive single session: **$6,720** in `ticket-plugin` — 1,724 turns, prompt/turn 510,750,
**cache-write 215,785,159** (≈10× any other session), cache-read 664,154,186. That one session is
**4.5% of all-time spend**, and the cache-write share says something was invalidating the prefix
constantly. Worth identifying what it was.

---

## 3. ECC vs slopstop

**The pattern: ECC has the mechanism, slopstop has the semantics.** slopstop's gates ask better
questions ("did you cheat the test?" vs "is there a console.log?") but implement them in the most
expensive substrate available — model tokens. ECC implements weaker checks for free.

| Capability | ECC | slopstop |
|---|---|---|
| **Deterministic hooks** | 20 hooks / 8 events / ~10,576 lines JS | **zero** |
| **Stop-time batching** | `post-edit-accumulator.js` → `stop-format-typecheck.js`: one format+typecheck per *response*, explicitly "eliminating per-edit latency" | per-step, in-model |
| **Size classifier** | `orch-pipeline` Step 0 — trivial/small/standard/large selects which phases run; "ceremony scales to blast radius" | **all 15 `:pr` steps regardless of diff size** |
| **Cost telemetry** | `cost-tracker.js` → `~/.claude/metrics/costs.jsonl`; statusline harness-cost bridge; `ecc-context-monitor` at 35%/25% context + $5/$10/$50 | router meters **fleet only, while running** |
| **Compact pressure** | `suggest-compact.js` — transcript-derived usage, window-scaled (160k@200k, 250k@1M), re-fires every 60k | none |
| **Component budget audit** | `context-budget` + `agent-sort` (DAILY vs LIBRARY, grep-evidenced per-repo install plan) | ships all 17 skills + 68 refs everywhere |
| **Lazy-load routing** | trigger-table keyword→skill map, claims 50%+ baseline cut | spine trick (already fine: 1.4k) |
| **Config protection** | hook **blocks** edits to linter/formatter configs — slopstop's own anti-slop thesis, enforced for free | prose |
| **Fact-forcing gate** | `gateguard-fact-force.js` (1,278 lines) blocks first Edit/Write per file until importers/schemas investigated | prose scope boundary |
| **MCP health** | pre-flight blocks unhealthy MCP calls; tracks failures, reconnects | failures hit the model |
| **Control plane** | `ecc2` — Rust + SQLite session store, start/stop/resume, daemon, worktree scaffolding, risk scoring, TUI dashboard | model-driven polling in `:run` |
| **Learning loop** | `continuous-learning-v2` instincts w/ confidence scoring + decay; `delivery-gate` enforces capture via mtime | memory files, manual |
| **Cross-harness** | `.codex .cursor .opencode .gemini .kiro .zed .trae .qwen .kimi .hermes` | Claude Code + Desktop |
| **Breadth** | 281 skills, 64 agents, 96 commands, 102 AgentShield rules | 17 skills |

### What slopstop has that ECC doesn't

Don't over-rotate — these are real advantages:

- **Ticket-anchored lifecycle** with durable tracking dirs surviving session death. ECC has
  **no ticket model at all**.
- **Red-test-first with actual enforcement** — tamper gate (Step 2d) + vacuity gate (Step 2f)
  mechanically prove the test was red before and fails at base. ECC's `tdd-workflow` is advisory
  prose; nothing verifies it.
- **Declarative four-tier ladder**, each tier checked by the tier above (`[tiers]` +
  `[stage_tiers]`, two-hop stage→tier→model resolution).
- **Real metering proxy** with committed price table + sha256 provenance.
- **Fleet worktrees** with independent handoff verification before integration.
- ECC's 281 skills are largely a *library* (language-pattern reference docs), not workflow.

### ECC skill-size context

Their SKILL.md distribution: n=281, median 185 lines, p25 124, p75 340, max 948. Total ~73,282
lines. They do **not** use a spine/reference split as aggressively — big skills are monolithic.
slopstop's progressive disclosure is genuinely better on that axis; the problem is the **16
sequential reads**, not the split itself.

---

## 4. Recommendations, ordered by time saved

### Tier 1 — attack context growth (≈40% of spend, and the latency)

1. **Session-per-stage, not session-per-ticket.** $0.06/turn early vs $0.70–1.15/turn at 401+.
   The handoff mechanism **already exists** — the durable tracking dir. Make `:plan`, `:pr`,
   `:merge` each assume a *fresh* session that rehydrates from `$TRACKING_DIR/$TICKET/`.
   Cap sessions ~150 turns → prompt/turn 465k → 126k on the segment holding 40% of spend:
   **~25–30% total saving, and every turn gets faster.** This is Theory 1b inverted.

2. **Cap tool-result volume at the source.** Bash is 52.4% of calls. Gate commands pipe through
   summarizers (`| tail -30`, `--quiet`, `--reporter=dot`); full output → file in the tracking
   dir; only summary line + failures enter context. ECC's `verification-loop` does exactly this
   as convention.

3. **Gate evidence to disk, not context.** Every gate → `$TRACKING_DIR/$TICKET/gates.json`;
   later steps read the one line they need. Today Step 8 re-derives its summary from
   conversation — which is *why* everything must stay resident.

4. **Defer ticket writes to the end** (Ian's own idea — supported). Ticket-system MCP is ~11% of
   tool-result volume (~5,400 calls, up to 2,877 tokens returned each), every one a serialized
   round trip mid-flow. Keep state local, flush at `:merge`. Primarily a **latency** win.

### Tier 2 — stop paying for gates this change doesn't need

5. **Adopt ECC's size classifier.** Score the diff (files, public surface, test-file touched,
   LOC): `trivial` → Steps 2d/2f/3/4/5 only; `standard` → + simplify + review; `large` →
   everything. State the tier in one line so it's overridable. ~40 lines in `:pr`; biggest
   wall-clock win for the common case.

6. **Deduplicate the test runs.** Step 0 (full suite) and Step 2 (relevant tests) run the same
   command minutes apart with only a **behavior-preserving** simplify pass between. Cache Step
   0's result + HEAD sha; Step 2 skips when sha and file set are unchanged.
   **Keep 2f** — different question, and it's the gate with teeth.

7. **Collapse the three passes over the same diff.** Steps 1 / 2e / 6 each load the branch diff
   independently. Merge 1 + 2e into one agent with two output sections: diff in context once,
   both verdicts out, one fewer subagent round trip.

8. **Cut ref-read round trips.** 16 sequential reads in `:pr` ≈ 11 min of pure latency. Batch
   per-step reads into single messages; inline the small refs (many <40 lines) back into
   SKILL.md.

### Tier 3 — move mechanical gates out of the model (the core ECC lesson)

9. **Ship hooks — slopstop has none.** All mechanically decidable at ~0 tokens, ~ms:
   - **Step 2d red-test tamper gate** → hook. `skills/pr/SKILL.md` itself says it is "`git log`
     plus `git diff`: no cost, no latency." It then spends 11 lines arguing why the *policed
     party* must not control the skip switch — **a hook makes that argument unnecessary by
     construction.**
   - **Step 0c cyclomatic complexity** → Stop hook
   - **`--no-verify` / `--force` / `reset --hard` ban** → PreToolUse Bash matcher
     (ECC ships `block-no-verify.js`, 546 lines)
   - **format/typecheck** → PostToolUse accumulate + Stop batch (ECC's exact pattern)
   - **branch-topology check** (`git log <integration>..<branch>`, universal §3) → PreToolUse on
     `gh pr create`
   - **config-protection** (block weakening linter configs) → direct port; it *is* the slopstop
     thesis

10. **Port `suggest-compact.js`.** 92.6% of sessions never compact while reaching 465k prompt
    tokens. A window-scaled pressure hook pointing at the tracking dir as rehydration source is
    ~150 lines.

### Tier 4 — measure

11. **Port `cost-tracker.js`** to a Stop hook writing `.slopstop/metrics/costs.jsonl`. The router
    sees fleet agents only, while up — but **88.5% of spend is the Opus orchestrator**, which it
    never sees. ⚠️ ECC's own header records that their version silently emitted zero-filled rows
    for **52 days** (2,340 rows, 0.0% non-zero token rate). **Assert a non-zero rate.**

12. **Haiku → Sonnet 5 for the small tier.** ~$1,000 all-time; removes the long tail of expensive
    fleet failures. Easy yes under TIME > COST.

### Not recommended

- **Deleting skills to cut the listing.** Measured at 1,393 tokens / ~$800 all-time. Wrong target.
- **Reducing model switching.** 118 switches in 385,137 turns. Nothing to win.
- **Compacting less / holding sessions open longer.** The data says the opposite.
- **The `caveman` skill.** Evaluated 2026-07-30 — see [Appendix A](#appendix-a--caveman-considered-and-rejected).

---

## Appendix A — `caveman`: considered and rejected

**Evaluated 2026-07-30. Verdict: real software, oversold headline, worth ~0.7–1.1% of spend on
this workload. Rejected as not worth a ticket ahead of Tier 1.**

### Authorship (a premise that turned out wrong)

- **caveman** — [JuliusBrussee/caveman](https://github.com/juliusbrussee/caveman); same author
  also ships [cavekit](https://github.com/juliusbrussee/cavekit) (1.1k★), which contains a skill
  named `grill`.
- **grill-me** — [Matt Pocock](https://github.com/mattpocock/skills/tree/main/skills/productivity/grill-me),
  MIT, March 2026. **Different author.**
- `skills/grill/SKILL.md` here descends from **Pocock's** (`8160f4f`, BILL-170, "Vendor grill-me
  as /slopstop:grill"), not Brussee's. Easy to conflate because Brussee ships a `grill` too, but
  his emits caveman-encoded `§G/§C` blocks for a spec workflow — unrelated mechanism.

### The claim vs. the vendor's own newer data

Headline: "65% fewer output tokens." Recomputed from their committed snapshot
(`evals/snapshots/results.json`, 10 prompts, opus-4-6, tiktoken `o200k_base`):

| Comparison | Mean | Median | Range |
|---|---|---|---|
| caveman vs `__baseline__` (no system prompt) | **46.0%** | 44.6% | 11–88% |
| caveman vs `__terse__` ("Answer concisely.") | **46.1%** | 50.3% | 0–88% |
| `__terse__` vs `__baseline__` (control) | **−4.7%** | — | — |

**46%, not 65%.** The 65% is from an older `benchmarks/` dir; their own `evals/README.md` states
the newer harness exists because the earlier one "conflates the skill with the generic terseness
ask, which is why its numbers were inflated." The headline is the number their own methodology
note disavows.

Note the control arm: "Answer concisely." made replies *longer* here (−4.7%), contradicting the
HN reproduction below that found "be brief" ≈ caveman. Two careful tests disagreeing on the
control is itself evidence neither number is robust.

### Independent reproductions

| Source | Method | Result |
|---|---|---|
| [JetBrains](https://blog.jetbrains.com/ai/2026/07/speak-to-ai-agents-like-cavemen-tosave-tokens/) | Harbor 0.17, Docker paired A/B, SkillsBench 86/87 tasks, ~240 trials, 3 runs, $106, sonnet-5, **forced activation = ceiling** | advertised 65% → **measured 8.5%**; ~10% cost cut erased by variance; quality 8 better/10 worse/64 tied, **p=0.82** |
| [HN #47954745](https://news.ycombinator.com/item?id=47954745) (Max Taylor) | 24 prompts, 5 arms, Claude-as-judge | "be brief" 419 tok vs caveman 401–449; quality 0.985 vs 0.970–0.976 (inside noise floor) |
| [andrew.ooo](https://andrew.ooo/posts/caveman-claude-code-skill-token-savings-review/) | review of community reproductions | 30–50% typical; "a real tool dressed in a meme" |

JetBrains' explanation is the load-bearing one: **advertised savings come from chat-style prose;
agentic output is dominated by code, diffs, and tool invocations — which caveman deliberately
preserves.**

### Credit where due

[`docs/HONEST-NUMBERS.md`](https://github.com/JuliusBrussee/caveman/blob/main/docs/HONEST-NUMBERS.md)
is more candid than most vendor docs: states input savings are **0%**, that the skill costs
~1–1.5k input tokens/turn, that it goes **net-negative** below ~1.5–2k output tokens per reply,
and cites issues *against itself* (#145 terse-QA loss, #506 Copilot per-request billing, #550 a
Cursor A/B at 4.3M vs 1M tokens and 2× wall-clock). `evals/README.md` volunteers that it measures
no fidelity, that tiktoken only approximates Claude's tokenizer, and that it has no statistical
power. **The software is honest; the banner is oversold.**

### What it would do here — measured on 264,734 of our own assistant turns

| Component | Tokens | Share | Caveman effect |
|---|---|---|---|
| **tool_use arguments** (bash, paths, Edit payloads) | 25,514,170 | **64.8%** | preserved verbatim |
| thinking (transient, not re-read) | 7,463,739 | 19.0% | untouched |
| **text: prose** | 6,097,410 | **15.5%** | **compressed** |
| text: fenced code | 299,062 | 0.8% | preserved verbatim |

**Addressable surface = 15.5% of output.**

| Prose reduction | Total output saved | Net all-time (on $150,473) |
|---|---|---|
| 46% (their honest snapshot) | 7.1% | ~$1,000 → **0.7%** |
| 65% (their headline) | 10.1% | ~$1,600 → **1.1%** |

Method: output ≈ $19,763 (13% of spend, turn-weighted $41.8/M blended); skill residency
~1.25k tok × 385,137 turns × $0.84/M blended cache-read ≈ $403.

The 7.1% figure lands on JetBrains' independently measured 8.5% — **two unrelated methods, same
answer.** That convergence is the strongest single result in this evaluation.

⚠️ Caveats on our own number: chars/4 rather than a real tokenizer, and `tool_use` args were
JSON-serialized (quoting overhead likely **overstates** the 64.8% bucket). Neither moves the
conclusion.

### Correction to §3 of this audit

An instinct worth retracting: assistant output is **not** a major driver of context growth here.
Prose is 6.1M tokens against 47.9M of tool results. Halving it barely bends the growth curve —
the §3 focus on tool results was correct.

### Decision

**Rejected.** 0.7–1.1% of spend sits inside the noise of Tier 1 (25–30% from session-per-stage).
If adopted later, adopt it for the reason its own docs lead with — replies are faster to read —
not for tokens.

**One piece worth revisiting separately:** `caveman-compress` (~46% reduction on `CLAUDE.md`-style
memory files, **input-side, every session forever**). That attacks the 37,769-token baseline
rather than output. CLAUDE.md + rules here are 6,099 tokens; a 46% cut ≈ 2,800 tokens resident
across every turn — ~$900 all-time. Still small, but the right *axis*: it compounds with session
length instead of fighting it.

---

## 5. Open questions

- **What was the $6,720 / 215.8M-cache-write `ticket-plugin` session?** 4.5% of all-time spend in
  one session, with anomalous cache-write. Identify the invalidation source.
- **`:design`'s profile was not separately measured** — it was excused up front as legitimately
  slow, and that was taken at face value rather than spending turns on it. Worth confirming it
  isn't *also* carrying avoidable growth.
- **Sidechain attribution:** `isSidechain` was 0 across all 385,137 turns despite 5,815 `Agent`
  tool calls, so subagent cost is folded into parent totals rather than separable. Fine for
  totals; blocks per-subagent attribution. The `cost-tracker.js` port should fix this.
- **Rate-table fidelity:** no >200K-token tier, no 1h-cache tier, Fable priced as Sonnet-class.

---

## Reproducing

Scripts in `scratch/cost-audit-2026-07-30/`. Pure stdlib Python 3, no deps, ~15 s total over
3.6 GB.

```bash
cd scratch/cost-audit-2026-07-30
python3 analyze.py sessions.json   # parse ~/.claude/projects/**/*.jsonl -> per-session rollup
python3 report.py                  # global figures, model split, theory 1/2/3/4 tables
python3 deep.py                    # baseline, growth curve, tool_result volume, wall clock
```

`report.py` reads `sessions.json` from cwd by default; override with `SESSIONS=/path/to.json`.
Numbers drift slightly on re-run as new sessions land in `~/.claude/projects` — a re-run
immediately after this audit already read 385,164 turns / $150,491 vs the 385,137 / $150,473
quoted above. Ratios are stable; treat absolute totals as a high-water mark at time of writing.

`analyze.py` walks every `*.jsonl` under `~/.claude/projects`, keeps lines containing `"usage"`,
and sums `input_tokens` / `output_tokens` / `cache_creation_input_tokens` /
`cache_read_input_tokens` per session, tracking model sequence, in-session switches, compact
summaries, and tool-call counts. `deep.py` additionally maps `tool_use` ids to `tool_result`
bodies to size what actually fills the context, and buckets prompt size by turn index.

Note: `report.py` re-hydrates the JSON-serialized Counters at the top (`_c.Counter(...)`) — the
rollup is written as plain JSON, so `most_common` is unavailable without it.
