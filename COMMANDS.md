# slopstop commands

> **Claude Desktop users:** commands in this document use the Claude Code form
> (`/slopstop:run`, `/slopstop:design`, etc.). If you installed via the Desktop
> installer, use the hyphenated form instead: `/slopstop-run`, `/slopstop-design`,
> and so on.

**Six commands. These are the things a human types.**

Everything else in slopstop — the investigator, the adversary, the three mechanical gates, the
reviewer — runs *inside* these commands as agents you never invoke directly. There is no
`/slopstop:implement`. If you find yourself wanting one, the answer is almost always `:run`.

| Command | Use it when |
|---|---|
| [`:design`](#slopstopdesign) | You have an idea and no plan. Produces a PRD. |
| [`:tickets`](#slopstoptickets) | You have a PRD and no tickets. Produces a ticket tree. |
| [`:run`](#slopstoprun) | You have tickets. Produces merged pull requests. |
| [`:grill`](#slopstopgrill) | You have a plan and want it attacked before you commit to it. |
| [`:gh-init`](#slopstopgh-init) | First time in a GitHub repo. Run once. |
| [`:doc-sync`](#slopstopdoc-sync) | You changed `design/` and want the wiki to match. |

## The normal path

```
/slopstop:design <your idea>      →  a PRD and a charter, and a gate where you read them
/slopstop:tickets <run-id>        →  a ticket tree in GitHub / Linear / JIRA
/slopstop:run TICKET [TICKET...]  →  merged PRs, closed tickets
```

Three commands, and the third one does the overwhelming majority of the work. You can enter at any
point: if you already have tickets, skip straight to `:run`.

---

<a id="slopstopdesign"></a>
## `/slopstop:design <topic>`

**When:** You know what you want to build but have not written it down, and you are about to start
handing work to an agent.

**Why:** Because everything downstream inherits this. The PRD shapes the ticket tree, the ticket
tree shapes every implementation, and a wrong assumption caught here costs a sentence. Caught at
review it costs a run. This is the highest-leverage half hour in the process.

`:design` does not take your description and start building. It **interviews you**. It runs
`:grill` against your idea and argues with it until you and it agree on what is actually being
built.

### What you type

```
/slopstop:design I want to build an online store that sells exclusively left handed
merchandise. It is a speciality store and selling speciality products, so it has a higher
markup than other stores. It doesn't need to be deployed on a server yet, it can just run
locally on this machine. It should have a typescript front end that talks via graphql to a
golang back end.
```

That is a good input. It states the product, the economics, the deployment constraint, and the
stack. It is also nowhere near enough to build from, which is the point.

### What comes back

Questions, and they will be uncomfortable ones. On that input, expect to be asked things like:

- Is "left-handed" a product category, a filter over a normal catalogue, or the entire inventory?
- Higher markup than what — do you need competitor pricing in the model, or is markup just a
  number on a product?
- "Runs locally" — is that one developer's machine, or does it need to survive a restart? Does it
  need a real database or is in-memory acceptable?
- Who can log in? Is there a checkout, and if so does money actually move, or is it stubbed?
- GraphQL between a TS front end and a Go back end: is the schema hand-written or generated, and
  which side owns it?

You answer. It pushes back on answers that are vague or that contradict something you said
earlier. It keeps going until the decision tree is resolved.

### What you get

A run directory under `scratch/runs/<run-id>/` containing:

- **`prd.md`** — what is being built and why, decision by decision.
- **`charter.md`** — the scope fence. What this feature is *not*.
- **`run.jsonl`** — the timing log.

Then it stops at gate **G-design** and shows you both documents. Nothing proceeds until you have
read them. **This is a real gate, not a notification.**

### Arguments

| | |
|---|---|
| `<topic>` | A feature name or a brain-dump. Empty → it asks for one sentence. |
| `--spec <path>` | Names an authoritative spec document. **Repeatable** — pass once per document. Every PRD decision gets classified against it, and the ticket adversary re-reads it later. |
| `--autonomous` | Resolves the grill's questions itself instead of asking you. Also settable per-project as `[design] autonomous = true`. |

Use `--spec` when there is an existing document that must be obeyed — an API contract, a
compliance rule, a design your team already agreed. It converts "the model should probably know
this" into "every decision is checked against this."

---

<a id="slopstoptickets"></a>
## `/slopstop:tickets <run-id>`

**When:** `:design` finished and handed you a run id.

**Why:** Because `:run` needs tickets that state what "done" means, and a PRD is not that. This
command turns one document into a tree of independently implementable tickets, each with an
explicit Definition of Done.

It also **attacks its own output.** An adversary at a higher model tier checks the tree against the
PRD in both directions: is anything in the PRD missing from the tickets, and is anything in the
tickets not in the PRD? Gold-plating and silent omissions both fail. It loops until the adversary
passes, then stops at gate **G-tickets** for you to approve before anything is written to your
ticket system.

This should run hands-free. If it cannot resolve a gap on its own, it stops and asks.

```
/slopstop:tickets left-handed-store-20260816-0930
```

Omit the run id and it lists the available runs and asks. It will not guess.

### Four other things it can do

These do not take a run id. Each cuts tickets for a situation where you have no PRD, and each
exists because `:run` needs a ticket and you do not have a usable one.

| | Use it when |
|---|---|
| `--retrofit <TICKET>` | A ticket exists but was written by someone else, or written fast. Brings it up to the five-section standard so `:run` can accept it. |
| `--rewrite <TICKET>` | `:run` stopped a ticket twice and diagnosed a **ticket defect** — the code was not the problem, the ticket was. Rewriting is authoring work, so it is yours. |
| `--refactor <fn> [<fn>…]` | You want to reduce complexity in named functions. The contract is *nothing broke*. Feed it the exempt list from a `complexity-check` report — that list is a work queue. |
| `--backfill <what to cover>` | You want tests over behaviour that already works. The deliverable is the tests themselves. |

`--refactor` and `--backfill` are mirrors. Refactor changes production code and may not touch a
test. Backfill writes tests and may not touch production code. Both skip the pipeline stages that
make no sense for them, which is why they are markedly cheaper than a normal ticket.

---

<a id="slopstoprun"></a>
## `/slopstop:run <TICKET> [TICKET...]`

**When:** You have tickets and you want them built. This is the command you will type most.

**Why:** Because it is the entire lifecycle. It takes a ticket from open to merged and closed
without you: it explores the code, writes tests that fail for what the ticket requires, proves
each one fails for the *right* reason, attacks the plan adversarially, implements without being
allowed to weaken the tests, runs three mechanical gates, gets the diff reviewed by a context that
never saw the conversation that wrote it, opens the PR, merges it, scores the Definition of Done,
and closes the ticket.

```
/slopstop:run BILL-501
/slopstop:run BILL-501 BILL-502 BILL-503
```

**Give it more than one ticket when you have more than one.** It reads each ticket's predicted file
map and runs the ones that do not collide side by side. Handing it tickets one at a time forfeits
that.

### It runs unattended, and that is the point

`:run` is autonomous by default. It stops to ask you roughly **1.6 times per run**, and the
question is usually answered in a few minutes. That is what makes it practical to have several
projects going at once — see [REPORT.md](REPORT.md) for the measurements.

It stops when judgment is genuinely required: an adversary finds a gap whose fix is a decision
rather than a test, a complexity gate blocks and the honest fix is out of scope, a Definition of
Done item cannot be met because the ticket was wrong, or a rule has to be broken and only you can
authorise that.

### The gates never soften

Three mechanical gates run after implementation — slop detection, a vacuity check that proves each
test would have failed before the branch existed, and a complexity bound. **None of them has a
permissive setting.** There is no flag that makes a gate lenient because the change looked small or
because nobody is watching. A gate that waves through the cases it exists to police is worse than
no gate, because it reports clean.

### Arguments

| | |
|---|---|
| `<TICKET>…` | One or more ticket keys. Empty → it asks. It will not infer a list from your branch or backlog. A malformed key is refused by name and the rest still run. |
| `--constraint "<phrase>"` | Applies to every ticket in the list. Passed verbatim to the investigator and treated as a hard scope everywhere else. |
| `--interactive` | Stop at every gate and ask. |

> **`--interactive` is specified but not built.** The ask-and-wait paths have not been implemented
> or exercised. Autonomous is what actually runs today. Do not report an interactive run as having
> gated on a human.

---

<a id="slopstopgrill"></a>
## `/slopstop:grill [plan]`

**When:** You have a plan — in your head or in a document — and you want it stress-tested before
you commit to it. Typically just before breaking something into tickets.

**Why:** Because it is much cheaper to find out that your plan has an unresolved branch now than
after three tickets have been built on top of it. `:design` runs this internally; you can also run
it on its own against anything.

```
/slopstop:grill we should move session storage from redis to postgres
```

It interviews you until the decision tree is resolved. Expect it to be persistent. It is not
trying to be agreeable.

Prefix the plan with `--autonomous` to have it resolve its own questions and report the
recommendations rather than asking you.

---

<a id="slopstopgh-init"></a>
## `/slopstop:gh-init`

**When:** The first time you use slopstop in a GitHub-backed repo. Once, then never again.

**Why:** slopstop tracks ticket state with labels and needs to know your ticket prefix and
workflow shape. This creates the labels and writes `.project-conf.toml` so nothing downstream has
to guess.

```
/slopstop:gh-init --workflow 3 --prefix STORE
```

Idempotent — safe to re-run. It preserves any config sections already in the file.

For Linear or JIRA there is no equivalent command: write `.project-conf.toml` by hand. See
[CONFIG.md](CONFIG.md).

### Arguments

| | |
|---|---|
| `--workflow {3,4}` | 3-state or 4-state workflow. Skips the question. |
| `--prefix PREFIX` | 2–8 uppercase characters, filesystem-safe. Skips the question. |
| `--in-progress-label`, `--in-review-label` | Override the default label names. |
| `--in-progress-color`, `--in-review-color` | Override the default hex colours. |

Pass `--workflow` and `--prefix` to make it fully non-interactive.

---

<a id="slopstopdoc-sync"></a>
## `/slopstop:doc-sync`

**When:** You have changed files in `design/` and want your ticket system's documentation store to
match.

**Why:** `design/` is the source of truth and lives in git, but the people reading it may be
looking at a GitHub wiki or Linear Docs. This pushes one to the other so they do not drift.

```
/slopstop:doc-sync
```

No arguments. One-way push: `design/` is never modified, the doc-store copy is overwritten, and
orphaned pages are pruned. The backend comes from `.project-conf.toml`.

**Do not run this in the same turn as editing `design/` files.** Finish the edits, then sync.

---

## What is not a command

The eleven workers — `investigate`, `red-tests`, `mutation-check`, `adversary`, `implement`,
`review`, `slop-check`, `vacuity-check`, `complexity-check`, `create-ticket`, `archive` — are
agents the three orchestrators launch. You do not invoke them and there is no slash command for
any of them. They are documented where they are defined, in `skills/<name>/SKILL.md`.

You will still see their verdicts quoted at you in a report — `ADVERSARY GOAL DEFECT`,
`REVIEW BLOCKED`, `VIOLATIONS: …`, `VACUITY VACUOUS: 2`. Those came from a worker.

## See also

- **[REPORT.md](REPORT.md)** — what this produces, measured.
- **[walkthrough/](walkthrough/)** — six real defects, each caught by a different check.
- **[CONFIG.md](CONFIG.md)** — every `.project-conf.toml` setting these commands read.
- **[SETUP-GUIDE.md](SETUP-GUIDE.md)** — installation, MCP servers, project initialization.
- **[QUICKSTART.md](QUICKSTART.md)** — one bug from ticket to merged PR, start to finish.
- **`skills/run/SKILL.md`** — the fifteen stages, in full, if you need the internals.
