# The multiagent-go run — an annotated walkthrough

On 2026-07-25 a single feature went from a five-sentence description to seven merged pull
requests in three hours and fifty-two minutes, built by a fleet of AI agents that were
deliberately chosen to be too weak for the job. This document is a time-ordered reading of what
happened, with attention to the moments where something was caught: a spec-level defect no test
covered, an agent that reported success without doing any work, an edited test helper, and — at
the very end — a false claim the orchestrator made about one of its own agents.

The software built is beside the point. It is a toy. What is worth reading is the machinery that
kept checking it, and the several occasions on which that machinery was the only thing standing
between a plausible-looking result and a wrong one.

> **A word about that three-hour-fifty-two figure before you draw conclusions from it.** It is
> elapsed time, not working time, and the difference is mostly *me*. A large share of it was the
> process sitting idle waiting for a human — waiting on an answer to a grill question, waiting for
> authorization to push to a public repo, waiting at a gate. I was doing other things while this
> ran, so I frequently did not notice for a while that it had stopped and was waiting on me. None
> of that is compute; it is my attention arriving late.
>
> The two effects compound in a way worth naming. Because the fleet ran on a deliberately
> underpowered model, attempts failed more often, and a failed attempt does not only cost another
> attempt — it tends to generate a question about how to proceed, which parks the run until I
> surface again. Had the coding agents succeeded on the first try, there would have been both
> fewer retries *and* markedly fewer interruptions to wait on. Read the timestamps in this
> document as a sequence, not as a benchmark.

---

## Contents

1. [What was being built](#1-what-was-being-built) — the raw input
2. [What slopstop is](#2-what-slopstop-is) — for readers who have never heard of it
3. [Notation](#3-notation) — how to read the transcript excerpts
4. [Reading order](#4-reading-order)
5. [Read the actual tickets](#5-read-the-actual-tickets)
6. [The whole run in one paragraph](#6-the-whole-run-in-one-paragraph)
7. [Outcome](#7-outcome)

---

## 1. What was being built

The entire input to the process — everything the human specified before being asked a single
question — was this, passed as the argument to `/slopstop:design` at **10:01:32**:

> I want a small command-line tool that stores key-value pairs persisted to a
> local JSON file. It should support five commands: `set <key> <value>` (store
> a pair), `get <key>` (retrieve a value), `delete <key>` (remove a pair),
> `list` (print all keys, optionally with values), and `export <path>` (write
> the whole store out to a different file). Implement each command in its own
> module/file rather than one shared file, so the work can be decomposed into
> independent, parallel-friendly pieces with disjoint file maps.

Five sentences. Read them again with an eye to what is *missing*, because the next 19 minutes
consist of the process finding out:

- **No language.** Not Go, not anything.
- **No error behavior.** What does `get` do on a missing key? What does `delete` do?
- **No output format.** Sorted? Insertion order? Does `list -v` print `key=value` or `key\tvalue`?
- **No file semantics.** Where does the JSON live? What happens if it is missing, or corrupt, or
  half-written when the process dies?
- **No concurrency story at all** — and this turns out to be the thread that runs through the
  entire document.

The last sentence is the interesting one, and it is doing a different job from the rest. *"so the
work can be decomposed into independent, parallel-friendly pieces with disjoint file maps"* is not
a requirement about the key-value store. It is an instruction about **how the work should be
shaped for parallel agents** — the human telling the process that the deliverable is a
demonstration of multi-agent decomposition, and the KV store is just the pretext.

That framing matters for reading everything downstream. When the process spends a question on
"five agents all need the same load/save code — how do we handle that shared surface?", it is
answering the last sentence, not the first four.

**Nothing else was provided.** No repo (it was empty but for a README and a config file), no
design doc, no architecture. Everything specific in the finished product — the transactional
store API, the sidecar lock file, the exit-code table, the test strategy — was produced by the
interview in [§1](01-design-and-grill.md) or forced by an adversary in [§2](02-tickets-and-adversary.md).

You can watch that happen in the public record rather than taking this document's word for it:
the tickets the process wrote from this paragraph are listed in
[§5](#5-read-the-actual-tickets), and every design decision below is traceable to a numbered
behavior in one of them.

---

## 2. What slopstop is

If you have used Claude Code, Cursor, Aider, or any coding agent, you know the failure mode this
exists to address: the agent produces something that looks right, claims it works, and is wrong
in a way that surfaces later. Tests pass because the agent wrote tests that pass. The summary at
the end describes work that was partly not done.

**slopstop** is a plugin — a set of slash commands for Claude Code — that wraps agent work in a
pipeline of interviews, adversarial checks, and human gates. Its thesis is in the name: stop the
slop before it goes in, rather than reviewing it out afterwards.

### The prime rule

From the process spec, and it explains most of the design decisions you will see:

> **No information, artifact, report, or claim is ever accepted at face value by any model doing
> checking.** Checkers are always fresh invocations fed only artifacts (documents, tickets, git
> state) — never the author's narrative or transcript.

This is why, throughout this document, verification is done by agents that were *just spawned*,
have never seen the conversation, are handed file paths rather than summaries, and are told to
re-run things themselves rather than believe a report that says they pass.
[§5](05-report-adversary.md) is entirely about what happened when one such agent was pointed at
the run's own final report.

### Four tiers of model

| Tier | Model here | Runs |
|---|---|---|
| **huge** | `claude-opus-5` | `:design` — the interview and the PRD; also the *checks on* the large tier's output |
| **large** | `claude-opus-5` | `:tickets` — cutting the ticket tree |
| **medium** | `claude-sonnet-5` | `:run` — the orchestrator that launches, kills, and verifies fleet agents |
| **small** | `claude-haiku-4-5` | the fleet agents that actually write the code, one per ticket |

The tiers are a config table, not a fixed list of models — each one names whatever model you point
it at. The **huge** tier is where the largest available model belongs, which today means Fable 5;
this run used Opus 5 there instead, partly to hold costs down and partly because the advantage of
Fable 5 over Opus 5 on this kind of work is not yet clear enough to pay for. Huge is also the tier
used least often — it runs the interview once and the adversarial checks on ticket trees and
reports — so the choice matters less than it would further down the ladder.

Two properties of this ladder do real work in the story:

- **Each stage runs one tier below the previous**, and **the tier above a producer checks its
  work.** Small agents write code; medium verifiers check it. Large cuts tickets; a huge adversary
  attacks them.
- **Each stage hard-stops if the session's model does not match its declared tier.** Not a
  warning — a refusal. [§3](03-handoff-and-gates.md) is the run hitting this and being unable to
  continue, *on a model more capable than the one required*, which is the clearest demonstration
  that the gate is about authority rather than ability.

### Stages and human gates

Each stage is a separate session. The only things that cross a stage boundary are **artifacts** —
files and tickets, never conversation history. The human is involved at a small number of gates,
each of which is a report followed by "go ahead?".

| Stage | Command | Produces | Gate |
|---|---|---|---|
| 1 | `/slopstop:design` | an interview, then a PRD + feature charter | **G-design** — proceed to ticket breakdown? |
| 2 | `/slopstop:tickets` | a ticket tree on GitHub, adversary-approved | **G-tickets** — launch the fleet? |
| 3 | `/slopstop:run` | worktrees, agents, merges, a final report | **G-final** — accept the run? |

> **A naming note, so the quotations do not confuse you.** At the time of this run the first two
> gates were called **G1** and **G2**, and the red-test tamper check was called **Gate 0**; slopstop
> has since renamed them to `G-design`, `G-tickets`, and *tamper check*, on the grounds that
> "stop at gate G2" tells a new user nothing. The transcript excerpts below say `G1`, `G2`, and
> `Gate 0` because that is what was actually printed. They are the same gates.

### Why the coding agents were chosen to be bad

The single most important thing to understand before reading [§4](04-fleet-execution.md). The
fleet ran on `claude-haiku-4-5` — the weakest tier — **by deliberate configuration**. The
orchestrator said so explicitly at 11:03:39:

> "That's the tutorial's deliberate choice: **a weak model so `:run`'s file-map-violation kill,
> handoff adversary, and rewrite loop have something real to catch. Expect failed attempts;
> they're the demonstration, not a malfunction.**"

So when you read that an agent failed verification, or produced nothing at all, or had to be
escalated to a stronger model — that is the instrument registering a reading. A run where nothing
failed would have demonstrated nothing.

**But there is a real trade-off underneath the demonstration, and it is not the one you would
expect.** Haiku is cheap, and putting the implementation work — by far the largest share of the
tokens — on the cheapest tier is the main lever for making a process this check-heavy affordable.
What it costs you is not money and it is not, in the end, correctness: every defect in this run
was caught. It is **wall-clock time**. Each attempt at a ticket is followed by a tamper check, two
independent verifying subagents, and an integration pass, so a failed attempt does not fail
cheaply — it fails *slowly*, having spent the full verification battery to establish that it
failed. Two of the nine tickets here burned an entire attempt on an agent that produced literally
nothing, and #2 consumed its whole three-attempt budget before escalating. The checks do their job
either way; you just wait longer. A higher failure rate on the small tier converts, almost
directly, into elapsed time — so the tier choice is a dial between spend and duration, and where
to set it depends on which of the two you are actually short of.

### Vocabulary you will need

| Term | Meaning |
|---|---|
| **run-id** | `kvstore-20260725-1001` — minted by `:design`, tags every artifact for the whole run |
| **grill** | the interview stage: relentless questioning until no design branch is unresolved |
| **PRD / charter** | the two artifacts `:design` produces; the charter holds broad-stroke rules for the run |
| **ticket tree** | GitHub issues in a dependency shape — umbrellas (no code) over leaves (one unit of work each) |
| **umbrella** | a parent ticket that owns no code, only children |
| **observable behavior** | a numbered, testable claim in a ticket; leaves carry 2–5 of them |
| **fleet agent** | a headless `claude -p` session, one per ticket, in its own git worktree and branch |
| **adversary** | a fresh agent whose instructions are to prove the work wrong, not to review it |
| **Gate 0** | the red-test tamper check — did the implementer edit tests that were supposed to be frozen? (called the *tamper check* in current slopstop) |
| **handoff verification** | two fresh subagents (requirements adversary + code reviewer) that must both pass an agent's work before it is integrated |
| **attempt budget** | each ticket gets 3 attempts; 2 failures triggers a diagnosis fork, which may escalate the model tier |
| **drift check** | an audit at an umbrella boundary asking whether the children collectively delivered what the parent promised |
| **fix-forward** | a real defect found late, filed as its own ticket rather than blocking the run |

---

## 3. Notation

The excerpts below are quotations from a real transcript, and they come from four different kinds
of speaker. Keeping them straight is most of the work of reading this, so every excerpt is
labelled:

| Label | Who is speaking | Audience |
|---|---|---|
| **SLOPSTOP ASKS** | the process, putting a question to the human | Ian |
| **IAN ANSWERS** | the human, selecting an option | the process |
| **SLOPSTOP SAYS** | the process narrating to the human | Ian |
| **GATE** | the process stopping, requiring an explicit human decision | Ian |
| **ADVERSARY** | a fresh checking agent with no conversation history | the process |
| **FLEET AGENT** | a headless implementation agent | its ticket, and the process |

Two more marks:

- **⚠** on an answer means **the human overrode the process's own recommendation.** Five of the
  thirteen grill questions carry this, and they are the source of nearly everything interesting
  downstream. Watching what happens after a ⚠ is the fastest way to read [§1](01-design-and-grill.md).
- **`[349]`** is a turn number in the session transcript, so any quotation can be traced back to
  its exact place in the run. Stages 1–2 and Stage 3 are separate sessions — **Transcript A** and
  **Transcript B** — because the run had to fork at 11:08 ([§3](03-handoff-and-gates.md)); each
  section names which one it is citing.

A worked example, from [§1](01-design-and-grill.md):

> ### 10:18:41 `[97]` — Q12 Concurrency · **recommendation overridden**
>
> **SLOPSTOP ASKS:** "Two `kv set` processes running at once can lose a write — both load, both
> save, last writer wins. Address it now or defer?"
> *Recommended:* defer, document last-writer-wins.
>
> **IAN ANSWERS:** add advisory file locking now ⚠

Everything the process asked came with a recommendation and a stated trade-off; every answer is
one of those options or a free-text override. The process never picked for the human, and the
human never had to invent an option from nothing.

---

## 4. Reading order

| # | Section | Window | The moment |
|---|---|---|---|
| 1 | [Design and grill](01-design-and-grill.md) | 10:01–10:23 | 13 questions; an override creates a contradiction the grill catches on itself |
| 2 | [Tickets and the adversary](02-tickets-and-adversary.md) | 10:26–10:53 | The tree passes its own checklist and is rejected anyway — 18 findings over 3 rounds |
| 3 | [The handoff](03-handoff-and-gates.md) | 10:59–11:06 | Stage 3 refuses to launch on an *over*-powered model |
| 4 | [Fleet execution](04-fleet-execution.md) | 11:08–12:52 | Failed attempts, a no-op, an escalation ladder, two tamper investigations |
| 5 | [The report adversary](05-report-adversary.md) | 12:55–13:53 | The code is fine; the story about it is not |

**If you only read one section:** §2 for the strongest single catch (a lock that does not lock),
or §5 for the most uncomfortable one (the process catching itself in a false claim and retracting
it in public).

### Jump straight to a moment

These eight links are stable — they will keep working even if headings are reworded, so they are
safe to cite.

| Link | Time | What happens |
|---|---|---|
| [The grill contradicts itself](01-design-and-grill.md#grill-contradiction) | 10:19:36 | two of its own answers, 70 seconds apart, turn out to be incompatible — and it reopens the question |
| [The lock that does not lock](02-tickets-and-adversary.md#flock) | 10:39:12 | an adversary rejects the ticket tree over a defect no test in the tree would have caught |
| [Measured, not argued](02-tickets-and-adversary.md#experiment) | 10:46:19 | the fix is validated by experiment: 40/40 failures before, 0/40 after |
| [A gate refuses an over-powered model](03-handoff-and-gates.md#tier-gate) | 11:02:30 | Stage 3 will not launch on Opus when the config says Sonnet, and explains why |
| [A requirement written 69 minutes earlier catches a bug](04-fleet-execution.md#writable-dir) | 11:55:55 | two independent verifiers reproduce it live on a read-only directory |
| [The agent that reported success and did nothing](04-fleet-execution.md#no-op) | 11:58:31 | clean exit, green tree, zero commits |
| [A tamper investigation that ends in acquittal](04-fleet-execution.md#tamper-check) | 12:18:44 | an edited test helper, adjudicated on evidence and in public |
| [The report that libeled its own agent](05-report-adversary.md#retraction) | 13:02:41 | the code was correct; the story about it was not — followed by a public retraction |

---

## 5. Read the actual tickets

Everything this run produced is public and still live, in
[`iansmith/slopstop-multiagent-example`](https://github.com/iansmith/slopstop-multiagent-example).
That includes the tickets themselves — and they are worth opening, because **not one word of them
was written by a human.** The tree was derived from the PRD by `/slopstop:tickets`, rewritten
three times under adversary pressure, and filed automatically. When this document says a decision
was "recorded in the ticket," you can go look at the record.

| Ticket | | Read it for |
|---|---|---|
| [#1](https://github.com/iansmith/slopstop-multiagent-example/issues/1) | kv — file-backed key-value CLI (root umbrella) | the PRD, charter, and final report, archived as comments at run close |
| [#2](https://github.com/iansmith/slopstop-multiagent-example/issues/2) | Foundation: module, store package, CLI dispatch, five stubs | **the single most instructive ticket in the tree** — see below |
| [#3](https://github.com/iansmith/slopstop-multiagent-example/issues/3) | Command implementations (parallel wave) | an umbrella that owns no code, only children |
| [#4](https://github.com/iansmith/slopstop-multiagent-example/issues/4)–[#8](https://github.com/iansmith/slopstop-multiagent-example/issues/8) | `set`, `get`, `delete`, `list`, `export` | five leaves with deliberately disjoint file maps |
| [#9](https://github.com/iansmith/slopstop-multiagent-example/issues/9) | Integration: end-to-end smoke test and README | the fan-in that proves the wiring |
| [#17](https://github.com/iansmith/slopstop-multiagent-example/issues/17) | Fix-forward: `set` test tautology, `delete` file-creation inconsistency | a real defect found late and filed rather than buried ([§4](04-fleet-execution.md)) |

**Start with [#2](https://github.com/iansmith/slopstop-multiagent-example/issues/2).** Its
Observable behavior 5 reads, in part:

> "locking uses `unix.Flock` (**not** `unix.FcntlFlock` — the concurrency test relies on flock's
> per-descriptor semantics) on the sidecar file `<store>.lock`, created at mode `0600` and **never
> renamed, never removed, never read — only locked**. Because the sidecar is never replaced, the
> atomic rename of the store file cannot orphan the lock, and two concurrent updaters never lose a
> write."

Every clause of that sentence is scar tissue. The sidecar exists because an adversary found that
the originally-specified lock did not lock ([§2](02-tickets-and-adversary.md)); the "never
renamed, never removed" is the *reason* it works; the `Flock`-not-`FcntlFlock` parenthetical was
added after a later round found the distinction load-bearing. Behavior 4, immediately above it,
carries the writable-directory requirement that a fleet agent then violated
([§4](04-fleet-execution.md)).

That is what these tickets are for. A leaf ticket carries a provenance header (which model, which
run, which parent), 2–5 numbered observable behaviors, an explicit file map, and its test
expectations — enough that an agent with no conversation history and no access to the PRD can
implement it correctly, which is exactly the situation every fleet agent is in.

The pull requests (#10–#16) and the agent and orchestrator comment threads on each issue are also
public, including the retraction in [§5](05-report-adversary.md).

---

## 6. The whole run in one paragraph

Read this after the sections, not before — it is a summary, not an introduction.

> A human override at **10:18:41** put locking in the design. It collided with a policy set at
> **10:17:31**, was resolved at **10:19:44** onto the store file, and silently contradicted an
> unremarkable decision from **10:14:37**. The tree passed its own structural checklist at
> **10:31:46**; the adversary rejected it at **10:39:12** and proved the defect 40/40 at
> **10:46:19**. The fix — a sidecar lock — created a new requirement the adversary itself wrote
> into the ticket at **10:46:55**. At **11:55:55** the implementing agent violated that exact
> requirement, and two independent verifiers reproduced it live on a `0500` directory. Three
> attempts and one model escalation later it was fixed. The suite was green the entire time —
> through vacuous assertions in `set` (**12:43**) and four README claims contradicted by the code
> (**12:42**, **12:52**), neither of which any test could catch. And at **13:02:41** an adversary
> pointed at the *report* found that the orchestrator had fabricated a violation against one of
> its own agents; it verified the accusation, retracted it publicly on the issue at **13:03:36**,
> and propagated the correction through four files before bringing the gate to the human.

---

## 7. Outcome

7 leaf tickets merged onto `master`, 2 umbrellas, suite green at `f8e8512` (including
`GOOS=windows go build`), 50 tests, 0 skips, `golangci-lint` clean — all independently re-run by
an adversary that was instructed not to believe the report. One fix-forward ticket
([#17](https://github.com/iansmith/slopstop-multiagent-example/issues/17)) left open by design.
Run directory deleted at 13:53 after human acceptance; PRD, charter, and final report live on as
comments on [issue #1](https://github.com/iansmith/slopstop-multiagent-example/issues/1).

Total elapsed **3 hours 52 minutes** — but see the caveat at the top: roughly 20 minutes of that
was the human actively answering questions and about 90 seconds was the human making gate
decisions, while an unmeasured but substantial remainder was the run parked, waiting for that
human to notice it had stopped.

---

**Start here → [1. Design and grill](01-design-and-grill.md)**
