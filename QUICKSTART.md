# slopstop — Quickstart

**slopstop** is a Claude Code plugin that makes AI work *ticket-first* and
*tests-first*: every change starts from a ticket, Claude writes the failing
tests before the code, and the work flows plan → test → code → review → merge
through a handful of slash commands. The point is to catch the slop *before* it
lands.

This quickstart takes about **15 minutes**. You'll copy a tiny example repo, and
take one real bug from ticket to merged PR — so you see the whole loop once with
your own hands. When you're done you'll have three more bugs and a feature to
practice on.

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

You do **not** need Docker, a database, or a CodeRabbit account. This quickstart
uses Claude's own code review.

---

## 1. Install the slopstop skills

Launch Claude Code (`claude`) anywhere and run these two commands at its prompt:

```
/plugin marketplace add iansmith/slopstop
/plugin install slopstop@slopstop
```

The first command registers the marketplace; the second installs the plugin from
it (`<plugin>@<marketplace>`). That gives you the `/slopstop:*` commands
(`:start`, `:plan`, `:pr`, `:merge`, …). You can quit Claude Code for now.

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

# Per-ticket notes live inside the project, under .slopstop/ (gitignored).
# Top-level keys — they must sit above [status_labels], not under it.
tracking_dir = ".slopstop/ticket-active"
archive_dir  = ".slopstop/ticket-archive"

[status_labels]
in_progress = "status:in-progress"

[pr_review]
backend = "claude"          # use Claude's code review, not CodeRabbit
effort  = "medium"
```

`system`/`key`/`prefix` tell slopstop this is a GitHub project whose tickets are
called `WORD-1`, `WORD-2`, …; `[status_labels]` is how a GitHub project encodes
“in progress” (GitHub has no built-in status field); `tracking_dir`/`archive_dir`
keep slopstop's working notes project-local under `.slopstop/` instead of in your
home directory (see [§8](#8-where-your-work-is-tracked)); `[pr_review]` picks the
review backend. Commit the change so it's part of your repo:

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

Launch Claude Code **from the repo root** (this is where `.project-conf.toml`
lives):

```bash
claude
```

Then paste this at Claude Code's prompt (the whole block is a single message to
Claude, not a shell command):

```
Read TICKETS.md, then create the four tickets it describes as GitHub issues —
run /slopstop:create-gh once for each, in order (WORD-1 first), so the issue
numbers line up. Use each ticket's heading as the title and its text as the body.
```

**A note on numbering:** GitHub gives issues *and* pull requests numbers from one
shared counter. `/slopstop:create-gh` makes the ticket key equal the issue number,
so your four issues become `WORD-1`…`WORD-4` (issues #1–#4). Your first pull
request will therefore be **#5** — that's expected, not a mistake.

---

## 6. The workflow at a glance

You'll drive one ticket through these commands. Each is a `/slopstop:*` command
you type into Claude Code:

| Command | What it does |
|---|---|
| `/slopstop:start WORD-1` | Marks the ticket in-progress, creates a `fix/WORD-1` branch, sets up tracking |
| `/slopstop:plan` | Writes a **failing test first**, commits it frozen, writes the plan — then **stops** |
| *(implement)* | You (or Claude, guided by the plan) write the fix until the test goes green. Leave it **uncommitted** |
| `/slopstop:pr` | Simplifies, runs tests, gets a **Claude code review**, commits, opens the PR |
| `/slopstop:merge` | Merges the PR, advances the ticket to Done, archives your notes |

> **`:plan` writes the test, not the fix.** In this interactive flow it stops
> after committing the failing test and writing the plan, and hands back to you
> for the implementation step. That's the `*(implement)*` row — don't skip it.

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
Now let slopstop fix it.
Back in Claude Code (launched from the repo root), run:

```
/slopstop:start WORD-1
```

Claude marks the issue in-progress and creates a `fix/WORD-1` branch. Then:

```
/slopstop:plan
```

`:plan` writes a **failing test** that pins down the expected behavior (`The` and
`the` should count as the same word), confirms it fails on the current code, and
**commits that test frozen** — then writes the plan and stops. It does *not* write
the fix yet.

> **When `:plan` asks for the test command,** paste the one for your language:
> - Python → `cd python && python3 -m pytest`
> - Go → `cd go && go test ./...`
>
> (slopstop remembers it for the rest of the ticket.)

Now **implement the fix.** `:plan` handed you a plan and a red test; the simplest
way forward is to ask Claude to carry it out — for example:

> Implement the WORD-1 fix per the plan, until the red test passes.

Claude edits the code (for WORD-1, lowercasing words before counting) and you
watch the test go from red to green. **Leave the change uncommitted** — the next
step needs it that way. Then open the PR:

```
/slopstop:pr
```

`:pr` tidies the code, runs the tests again, confirms the frozen test wasn't
tampered with, **makes the commit**, gets a Claude code review, and opens the pull
request. Read the review, then ship it:

```
/slopstop:merge
```

`:merge` merges the PR, closes `WORD-1`, and archives your tracking notes. That's
the full loop. 🎉

---

## 8. Where your work is tracked

While a ticket is active, slopstop keeps working notes **inside the project**,
under `.slopstop/` (the `tracking_dir` you set in §3):

```
.slopstop/ticket-active/WORD-1/
├── task_plan.md    the plan + the Definition of Done (the contract for "done")
├── findings.md     what Claude learned while investigating
└── progress.md     a session-by-session log
```

`.slopstop/` is **gitignored**, so these notes never clutter the repo or a diff —
but they live next to the code, travel with the clone, and (unlike the old
`~/.claude` location) work when slopstop runs headless agents. Open `task_plan.md`
while a ticket is in flight: it's the clearest window into what Claude is doing.
After `:merge`, the folder moves to `.slopstop/ticket-archive/WORD-1/`.

> **Want the full picture?** [HOW-IT-WORKS.md](https://github.com/iansmith/slopstop-example/blob/master/HOW-IT-WORKS.md)
> in the example repo walks through every building block — the tracking dir, the
> frozen red test, and the committed-`design/` vs gitignored-`.slopstop/`/`scratch/`
> split — for the reader who wants to understand the machine, not just drive it.

---

## 9. Now do the rest

You've got three more tickets — same loop each time:

- **WORD-2** (bug) — punctuation isn't stripped (`dog,` counted separately from `dog`)
- **WORD-3** (bug) — `--top N` returns one row too few
- **WORD-4** (feature) — add a `--stopwords` flag to filter out common words

Start each with `/slopstop:start WORD-2` and repeat.

---

## Where to go next

- **[HOW-IT-WORKS.md](https://github.com/iansmith/slopstop-example/blob/master/HOW-IT-WORKS.md)**
  (in the example repo) — the building blocks explained one primitive at a time,
  for the reader who wants to understand the machine, not just run the five
  commands. The natural next read after this quickstart.
- **[START-HERE.md](START-HERE.md)** — the full setup guide: Linear/JIRA backends,
  the file-size pre-commit gate, workflow shapes, and every setup step.
- **[CONFIG.md](CONFIG.md)** — a reference for every setting in `.project-conf.toml`.
