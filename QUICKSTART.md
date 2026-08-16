# slopstop — Quickstart

**slopstop** is a Claude Code plugin that makes AI work *ticket-first* and
*tests-first*, and then drives it **autonomously**: you hand `/slopstop:run` a
ticket, and it investigates, writes the failing tests, proves they fail for the
right reason, adversaries them, implements, runs the gates, reviews the diff in a
clean context, opens the PR, merges it, closes the ticket, and archives the
notes. The point is to catch the slop *before* it lands — including when nobody
is watching.

This quickstart takes about **15 minutes**, most of it setup. You'll copy a tiny
example repo and watch one real bug go from ticket to merged PR under a single
command. When you're done you'll have three more bugs and a feature to practice
on.

> Everything here assumes you're running **Claude Code in a terminal**. Commands
> shown as `/slopstop:…` are typed into Claude Code's prompt; everything else is
> your shell.

---

## Before you start

You'll need these on your `PATH`:

- [ ] **git**
- [ ] **[GitHub CLI](https://cli.github.com/) (`gh`)**, authenticated — run `gh auth login` if you haven't
- [ ] **[Claude Code](https://code.claude.com/docs)**, signed in — `npm install -g @anthropic-ai/claude-code`
- [ ] **one of:** Python 3.11+ (plus `pip install pytest`) **or** Go 1.21+

You do **not** need Docker, a database, or a review-bot subscription. slopstop's
own clean-context `review` worker is what gates the merge; a bot's comments are
read if they happen to be there and never waited for.

---

## 1. Install the slopstop skills

Launch Claude Code (`claude`) anywhere and run these two commands at its prompt:

```
/plugin marketplace add iansmith/slopstop
/plugin install slopstop@slopstop
```

The first command registers the marketplace; the second installs the plugin from
it (`<plugin>@<marketplace>`). That gives you six commands — `:run`, `:design`,
`:tickets`, `:grill`, `:gh-init`, `:doc-sync` — of which this quickstart uses
one. You can quit Claude Code for now.

---

## 2. Get your own copy of the example

The example lives at **https://github.com/iansmith/slopstop-example**. It's a
GitHub *template*, so you make your own independent copy:

1. Open the repo and click **“Use this template” → “Create a new repository.”**
2. Name it `slopstop-example` (or anything you like) under your account.
3. Clone your new copy and go into it:

```bash
git clone https://github.com/YOUR-USERNAME/slopstop-example.git
cd slopstop-example
```

The repo has a small **word-frequency** command-line tool — it prints the most
common words in a text file — with three bugs and one missing feature waiting in
[`TICKETS.md`](https://github.com/iansmith/slopstop-example/blob/master/TICKETS.md).
The same program is in both `python/` and `go/`; pick whichever language you're
more comfortable with and use it for all four tickets.

---

## 3. Point the config at your copy

Open **`.project-conf.toml`** — this is the one file slopstop reads to know what
project it's working on. The only line you must change is `key`:

```toml
system = "github"
key    = "YOUR-USERNAME/slopstop-example"   # <- change this line
prefix = "WORD"

[status_labels]
in_progress = "status:in-progress"

[pr_review]
backend = "claude"          # whose bot comments to look for, if any are there
```

`system`/`key`/`prefix` tell slopstop this is a GitHub project whose tickets are
called `WORD-1`, `WORD-2`, …; `[status_labels]` is how a GitHub project encodes
“in progress” (GitHub has no built-in status field); `[pr_review]` only selects
*whose* review-bot comments `:run` reads once before merging — it never waits for
one. Nothing configures where working notes go — a `.slopstop/` directory is
enough on its own (see [§8](#8-where-your-work-is-tracked)). Commit the change so
it's part of your repo:

```bash
git add .project-conf.toml
git commit -m "Point slopstop at my repo"
git push
```

---

## 4. Create the in-progress label

GitHub projects mark work-in-progress with a label. Create it once:

```bash
gh label create "status:in-progress" --color fbca04 --description "Actively being worked on"
```

(That's the same label name you set in `[status_labels]` above.)

---

## 5. Create your four tickets

The example repo describes four tickets in `TICKETS.md` but doesn't ship them as
issues, so create them from the shell — **in order, WORD-1 first**:

```bash
gh issue create --title "WORD-1: The and the counted separately" --body-file - <<'EOF'
Paste WORD-1's section from TICKETS.md here.
EOF
```

Repeat for WORD-2, WORD-3 and WORD-4, or open `TICKETS.md` and create the four in
GitHub's web UI. Order matters, and only here.

**A note on numbering:** GitHub gives issues *and* pull requests numbers from one
shared counter. slopstop's central invariant is that **`WORD-N` *is* GitHub issue
`#N`** — that's how every later step resolves a ticket key to an issue without
searching. Creating your four issues first on an empty repo makes them #1–#4, so
`WORD-1`…`WORD-4` line up. Your first pull request will therefore be **#5** —
expected, not a mistake.

> **In a real project you would not do this by hand.** Tickets are created by
> `/slopstop:tickets`, which cuts an adversary-approved tree from a PRD and hands
> the approved drafts to its `create-ticket` worker — the thing that actually
> assigns `WORD-N = #N`, links umbrellas to leaves, and refuses to double-create
> on a partial failure. This quickstart starts from tickets someone already wrote,
> which is the other legitimate entry point.

---

## 6. The workflow at a glance

There is one command, and it does the whole lifecycle:

```
/slopstop:run WORD-1
```

Inside it, per ticket, it explores the code, writes tests for what the **ticket**
requires and commits them frozen, proves each one fails for the *right* reason,
lets a fresh reader hunt for the cases those tests missed, implements without
being allowed to weaken a test, runs three mechanical gates, reviews the diff in a
context that never saw the conversation that wrote it, then opens the PR, merges,
scores the Definition of Done, closes the ticket and archives the notes.

Fifteen stages in total. You do not need to know them to use it — but if you want
them, `skills/run/SKILL.md` has the full table.

**You don't drive any of it.** `:run` is autonomous by default — it exists to take
tickets unattended, and a run that stalls waiting for someone is the failure it's
built to avoid. (There is a `--interactive` flag in its contract for stopping at
each judgment gate, but it is **not implemented yet**.)

Hand it several tickets at once — `/slopstop:run WORD-1 WORD-2 WORD-3` — and it
interleaves them, running tickets with non-overlapping file maps concurrently and
merging serially. **If one ticket hits a gate it can't clear, only that ticket
stops:** its branch and notes are left intact, the rest keep going, and everything
that stopped is reported together at the end with what it needs from you.

---

## 7. Fix your first bug, end to end

Let's fix **WORD-1** — the word counter treats `The` and `the` as different
words. First, see the bug yourself:

```bash
# Python:
cd python && python3 wordfreq.py ../data/sample.txt --top 3 && cd ..
# Go:
cd go && go run . ../data/sample.txt --top 3 && cd ..
```

You'll see `the` and `The` counted as two separate words. (You'll also notice
only 2 rows instead of 3 — that's WORD-3's off-by-one bug; you'll fix it later.)
Now let slopstop fix it. Launch Claude Code **from the repo root** (this is where
`.project-conf.toml` lives):

```bash
claude
```

and run:

```
/slopstop:run WORD-1
```

Then read. The interesting part is not the fix — lowercasing words before
counting — it's the order things happen in. The test that says `The` and `the`
count as one word is written and **committed before any fix exists**, and it is
confirmed red first. Nothing downstream is allowed to edit it: if the
implementation can't make it pass, that's a finding, not an invitation to adjust
the test.

> **If slopstop can't work out how to run your tests,** it will settle the command
> once and thread it to every worker that needs it:
> - Python → `cd python && python3 -m pytest`
> - Go → `cd go && go test ./...`

When it finishes you'll have a merged PR (#5), a closed `WORD-1` with the plan and
findings posted as comments, and your tracking notes archived. That's the whole
loop. 🎉

**If it stops instead**, read what it says. A stopped ticket means a gate held —
an adversary found a gap, a test came up green when it should have been red, a
review couldn't converge — and the branch is still sitting there for you to look
at. That's the tool working, not failing.

---

## 8. Where your work is tracked

While a ticket is active, slopstop keeps working notes **inside the project**,
under `.slopstop/` — no config needed; the directory's presence is what puts them
there, and it's gitignored so they never land in a diff:

```
.slopstop/ticket-active/WORD-1/
├── task_plan.md    the plan + the Definition of Done (the contract for "done")
├── findings.md     what Claude learned while investigating
└── run.jsonl       every stage transition, timestamped, append-only
```

`.slopstop/` is **gitignored**, so these notes never clutter the repo or a diff —
but they live next to the code, travel with the clone, and (unlike the old
`~/.claude` location) are writable by the agents `:run` launches. Open
`task_plan.md` while a ticket is in flight: it's the clearest window into what
Claude is doing.

`run.jsonl` is the one to know about. It's the run's state machine, its resume
point, and its timing record all at once — one JSON object per line, one
`started` and one `finished` per stage, and the orchestrator is its only writer.
Because it also brackets the times it's blocked on *you*, machine time and
"someone went to bed" are separable rather than lumped into wall clock. If a run
is interrupted, `:run` replays that file rather than trusting anything it
remembers; if a span was never closed, it says so and reports no timing numbers
at all, because a broken record shouldn't be able to produce a plausible summary.

When the ticket lands, its notes are posted as comments on the issue and the
folder moves to `.slopstop/ticket-archive/WORD-1/` — `run.jsonl` travels with it,
so an archived ticket carries its own history.

> **Want the full picture?** [HOW-IT-WORKS.md](https://github.com/iansmith/slopstop-example/blob/master/HOW-IT-WORKS.md)
> in the example repo walks through every building block — the tracking dir, the
> frozen red test, and the committed-`design/` vs gitignored-`.slopstop/`/`scratch/`
> split — for the reader who wants to understand the machine, not just drive it.

---

## 9. Now do the rest

You've got three more tickets:

- **WORD-2** (bug) — punctuation isn't stripped (`dog,` counted separately from `dog`)
- **WORD-3** (bug) — `--top N` returns one row too few
- **WORD-4** (feature) — add a `--stopwords` flag to filter out common words

Hand them over in one go:

```
/slopstop:run WORD-2 WORD-3 WORD-4
```

They're interleaved, not queued: `investigate` runs for all three first, and the
predicted file maps decide what's safe to run concurrently. Merges are always
serial, one PR at a time — and if two of them do collide, the loser gets `master`
merged **into** it and its tests re-run, never a rebase of a pushed branch.

---

## Where to go next

- **`/slopstop:design <topic>`** — this quickstart started from tickets someone
  had already written. The other entry point starts from an idea: `:design`
  grills you into a PRD and charter, `:tickets` cuts an adversary-approved ticket
  tree from it, and `:run` builds the tree. That's the full three-command path.
- **[The walkthrough](walkthrough/)** — six real defects from real runs, each
  caught by a *different* check, each quoted from the log that recorded it. Read
  it when you want to know what the adversarial parts of slopstop actually do.
  Five of the six would have survived a fully green test suite.
- **[REPORT.md](REPORT.md)** — what slopstop produces, measured over four days
  and four repositories, with the method and the caveats.
- **[COMMANDS.md](COMMANDS.md)** — the six commands, with when and why to use each.
- **[HOW-IT-WORKS.md](https://github.com/iansmith/slopstop-example/blob/master/HOW-IT-WORKS.md)**
  (in the example repo) — the building blocks explained one primitive at a time,
  for the reader who wants to understand the machine, not just drive it. The
  natural next read after this quickstart.
- **[SETUP-GUIDE.md](SETUP-GUIDE.md)** — the full setup guide: Linear/JIRA backends,
  the file-size pre-commit gate, workflow shapes, and every setup step.
- **[CONFIG.md](CONFIG.md)** — a reference for every setting in `.project-conf.toml`.
