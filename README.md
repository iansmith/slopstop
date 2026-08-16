# slopstop

**Ticket-anchored AI development, built on one idea: stop slop before it goes in, instead of
reviewing it out afterwards.**

Work starts from a ticket, not a prompt. `/slopstop:run` takes one or more tickets and carries
each from "open" to "merged and archived" by itself — investigate, write failing tests for what
the *ticket* requires, prove each fails for the right reason, attack the plan adversarially,
implement without weakening the tests, run three mechanical gates, review the diff in a context
that never saw the conversation that wrote it, open the PR, merge, close the ticket, archive the
notes.

It is **autonomous by default.** An unattended run that stalls waiting for someone is the failure
mode the default exists to avoid.

---

## Does it work?

Over four days in August 2026 it delivered **3,888 lines of production code and 13,332 lines of
tests across four repositories**, for **2.4 hours of human attention** — a median of three and a
half minutes per question asked.

That is about **3.9x** what a very generously-defined strong engineer produces, and it was
achieved with one of its two parallelism multipliers switched off entirely.

**[REPORT.md](REPORT.md)** is the full measurement, including the method, the arithmetic, and a
section on what would make the comparison wrong.

**[walkthrough/](walkthrough/)** is the other half of the answer: six real defects from those
runs, each caught by a *different* check, each quoted from the log that recorded it. Five of the
six would have survived a fully green test suite.

---

## The commands

Six, and that is the whole list. Full reference with when and why each is used:
**[COMMANDS.md](COMMANDS.md)**.

| Command | Use it when |
|---|---|
| `/slopstop:design <topic>` | You have an idea and no plan. Produces a PRD. |
| `/slopstop:tickets <run-id>` | You have a PRD and no tickets. Produces a ticket tree. |
| `/slopstop:run <TICKET>…` | You have tickets. Produces merged pull requests. |
| `/slopstop:grill [plan]` | You want a plan attacked before you commit to it. |
| `/slopstop:gh-init` | First time in a GitHub repo. Run once. |
| `/slopstop:doc-sync` | You changed `design/` and want the wiki to match. |

The normal path is `:design` → `:tickets` → `:run`. If you already have tickets, go straight to
`:run`.

Everything else — eleven single-purpose workers — is an internal agent the orchestrators launch.
You never invoke one, and there is no slash command for any of them.

---

## Why prevention rather than recovery

Most "AI code review" tooling is recovery: it hunts for slop once it is already in the diff.
slopstop puts the weight earlier. The work is scoped and test-anchored *before* the implementation
exists, so there is less slop to catch.

Three properties hold whether or not anyone is watching:

**The tests are written first and then frozen.** The agent whose code must satisfy them cannot
edit them. A gate checks this at every subsequent stage, and it checks by attribution — every
change to a frozen test is traced to the commit that made it.

**The mechanical gates have no permissive setting.** Slop detection, a vacuity check that proves
each test would have failed before the branch existed, and a complexity bound. There is no flag
that softens a gate because the change looked small. A gate that waves through the cases it exists
to police is worse than no gate, because it reports clean.

**The session that wrote the code never reviews it.** Reviewers and adversaries run as subagents
with their own context and no access to the conversation that produced the work. This has an
incident behind it — a PR once recorded a clean review the authoring session had performed on its
own code.

The argument at length: **[Prevention, Not
Recovery](https://iansmith.github.io/slopstop/what_is_slopstop.html)**.

---

## Install

### Claude Code (CLI) — recommended

```
/plugin marketplace add iansmith/slopstop
/plugin install slopstop@slopstop
```

Commands are then namespaced: `/slopstop:run`, `/slopstop:design`, and so on.

(The repo, the marketplace it hosts, and the plugin inside it all share the name `slopstop` —
hence the doubled-up second command.)

### Claude Desktop — manual install

Claude Desktop has no `/plugin` manager and cannot install from a marketplace. It *does* load
standalone slash commands from `~/.claude/commands/`, so this installer drops them there directly.
A stopgap until Desktop ships plugin support.

```bash
curl -fsSL https://raw.githubusercontent.com/iansmith/slopstop/master/install-for-claude-desktop.sh | bash
```

Commands then appear un-namespaced: `/slopstop-run`, `/slopstop-design`. The installer drops every
skill, workers included, since an orchestrator has to be able to invoke them.

Pinning to a tag, uninstalling, and the MCP details are in
**[SETUP-GUIDE.md](SETUP-GUIDE.md)**.

---

## What you need

slopstop is a **wrapper around a ticket-system MCP and a GitHub backend.** It has no API client of
its own.

**Required**

- **Claude Code** with the plugin manager, or Claude Desktop via the installer above.
- **A ticket system** — GitHub Issues (needs no extra MCP), or Linear, or JIRA:
  ```
  /plugin install linear@claude-plugins-official
  /plugin install atlassian@claude-plugins-official
  ```
- **A `.project-conf.toml`** in each project. See below.

**Required for the PR and merge stages**

- **The GitHub MCP** (`/plugin install github@claude-plugins-official`), or **the `gh` CLI**, or
  both. Two things still prefer `gh`: reading bot comments, and the merge itself — `:run` uses
  `gh pr merge --merge --delete-branch`, and the MCP's merge tool does not delete the branch.

> **Known limitation.** `mcp__plugin_github_github__create_pull_request` returns 403 on some repos
> due to the plugin's PAT scope. `:run` falls back to `gh pr create` on a 403, so without `gh`
> installed PR creation will fail.

**Recommended**

- **A test command** the workers can invoke. Auto-detected from `Taskfile.yml`, `package.json`,
  `Makefile`, `Cargo.toml`, `go.mod`, or `pyproject.toml`, then threaded to every worker that
  needs one.
- **A PR review bot**, if you want a second opinion on top of the `review` worker. It is read
  **once** and never waited for.

Full detail, including MCP tool namespaces and troubleshooting: **[SETUP-GUIDE.md](SETUP-GUIDE.md)**.

---

## Configuration

Every project needs `.project-conf.toml` at its repo root. Minimal versions:

**GitHub Issues**

```toml
system = "github"
key    = "owner/repo"
prefix = "MYPREFIX"

[status_labels]
in_progress = "status:in-progress"
```

`/slopstop:gh-init` writes this for you and creates the labels. Run it once.

**Linear**

```toml
system = "linear"
key    = "MAZ"      # Linear team key
prefix = "MAZ"
```

**JIRA**

```toml
system = "jira"
key    = "PLTF"     # JIRA project key
prefix = "PLTF"
```

The plugin reads this on every invocation and **only operates on tickets whose key matches the
cwd's `prefix`** — so a session in one project can never touch another project's ticket.

Every available key, with defaults: **[CONFIG.md](CONFIG.md)**.

---

## Where to go next

| | |
|---|---|
| **[QUICKSTART.md](QUICKSTART.md)** | One real bug from ticket to merged PR, in about 15 minutes. |
| **[COMMANDS.md](COMMANDS.md)** | The six commands — when and why to use each. |
| **[REPORT.md](REPORT.md)** | What it produces, measured. |
| **[walkthrough/](walkthrough/)** | Six defects, six different checks, quoted from the logs. |
| **[SETUP-GUIDE.md](SETUP-GUIDE.md)** | Installation, MCP servers, project layout. |
| **[CONFIG.md](CONFIG.md)** | Every `.project-conf.toml` setting. |
| **[PRIVACY.md](PRIVACY.md)** | What leaves your machine, and what does not. |

---

## License

CC-BY-SA-4.0. See [LICENSE](LICENSE).

## Author

Ian Smith — [github.com/iansmith](https://github.com/iansmith)
