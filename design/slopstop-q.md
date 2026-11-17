# slopstop-q

A leaner ticket loop. Question it answers: **can we get slopstop-grade results for
far fewer tokens?** It drops the multi-agent fleet and the handoff-blessing
machinery; it keeps the one thing that matters — a clean-context review the
author session did not write.

Derived from [slopstop](https://github.com/iansmith/slopstop) (sophie, 2026-09). **The orchestrator is one
interactive session, moved into a worktree, doing everything itself — RED test,
investigation, implementation, PR, merge, cleanup — except the review.** Several
such sessions run different tickets in parallel; each owns its worktree and
branch and shares only `master`, the remote, and the ticket system. The review is the one thing that must run in contexts that
did not write the code, so it is the only place the loop launches agents: eight
review angles and one verifier (step 5). Two rules bind the orchestrator and
those agents:

- the **reuse ladder** — keep generated code small (our version of the idea in
  [DietrichGebert/ponytail](https://github.com/DietrichGebert/ponytail); see
  "Provenance" at the end for what to compare against);
- the **graph-for-discovery directive** — `MUST`, not "prefer", because "prefer"
  was measured to be ignored every time.

A run that gets a clean review carries itself through the merge and cleanup on
its own — the human is handed the merge only when something went wrong along the
way (see step 5).

## Prerequisites

Five things must be in place before a session runs this loop:

| prerequisite | what it is | where it lives | which steps need it |
|---|---|---|---|
| **codebase-memory-mcp** | MCP server providing `search_graph`, `trace_path`, `get_code_snippet`, `query_graph`, `get_architecture`, `search_code`, `index_repository`, `check_index_coverage` | user-scope MCP config: `mcpServers` in `<config dir>/.claude.json`, where the config dir is `$CLAUDE_CONFIG_DIR` if set, else `~` (so `~/.claude.json`). Register it in **every** config dir you run sessions under: `CLAUDE_CONFIG_DIR=<dir> claude mcp add --scope user codebase-memory-mcp -- ~/.local/bin/codebase-memory-mcp`. `~/.claude/mcp.json` is not read. Check with `claude mcp list`. Missing registration shows up as agents reporting the graph tools are absent and grepping with `# content:` markers instead | Rule A (every step), step 1 (`--index`), step 6 cleanup |
| **`/simplify`** | Claude Code skill (slopstop plugin) | installed via slopstop plugin | step 4 simplify loop |
| **the 8-angle review** | eight review agents and one verifier, each with a fresh context, launched by the orchestrator itself; defined in "Launching the review" | this file | step 5 review gate |
| **`graph-first-hook.py`** | PreToolUse hook enforcing Rule A — blocks grep-as-discovery | `~/ticket-plugin/tools/graph-first-hook.py`, registered in each repo's `.claude/settings.local.json` | every step (passive) |
| **`gh`** | GitHub CLI, used over the REST API only (`gh pr diff`, `gh api …`). GraphQL-backed commands (`gh pr view --json`, `gh pr merge`) are blocked in Claude Code cloud sessions | installed locally; in cloud sessions the environment's setup script installs it, and it authenticates from the session's own `GH_TOKEN` | step 6 merge |

**`/simplify` is the only slopstop skill this loop uses.** No other `/slopstop-*`
commands, no tier carriers, no fleet agents. The adopting repo's `CLAUDE.md`
says so explicitly (see "Running it").

## Two rules that bind everywhere

These apply to the orchestrator in every step, and to the review agents it
launches. Section "Launching the review" says how they get them.

### Rule A — graph for discovery, grep/Read for content (MANDATORY)

```
MANDATORY — graph for discovery, grep/Read for content.

Before any code discovery, run list_projects to confirm graph tools work.
If it succeeds, you MUST use graph tools for ALL discovery queries:

  DISCOVERY (graph tools — MUST use):
  - search_graph: find functions/classes/symbols by name or keyword
  - trace_path: find callers and callees
  - get_code_snippet: read a symbol's source
  - query_graph: multi-hop patterns
  - get_architecture: module layout and package boundaries
  - search_code: text search with structural context

  CONTENT (grep/Read — always correct):
  - Reading/editing file content, checking exact values
  - Non-code files (config, YAML, markdown, .toml, .json)
  - Test output, build logs, runtime artifacts
  - Files check_index_coverage reports as uncovered

grep for content is the right tool. grep for discovery (finding callers, locating
definitions, tracing dependencies) when graph tools are available is wrong — state
why if you do it.
```

The line is not "never grep". The graph answers *where is it / who uses it / does
it exist*; grep and Read answer *what exactly does it say*.

| you want to… | tool | why |
|---|---|---|
| find the function a new test will target | `search_graph` | discovery |
| find who calls the function you are about to change | `trace_path` | discovery |
| check whether a helper like the one you are about to write already exists (ladder rung 1) | `search_graph` / `search_code` | discovery |
| locate every implementation of an interface | `search_graph` with `relationship` / `query_graph` | discovery |
| see the module layout before deciding where a file goes | `get_architecture` | discovery |
| read a symbol's body once you have its qualified name | `get_code_snippet` | content, and the graph has it |
| read a whole file's exact text — imports, comments, the lines around a function | `Read` | content; the graph returns symbols, not files |
| read `.project-conf.toml`, YAML, JSON, markdown, a Makefile | `Read` / grep | non-code, not indexed |
| read test output, a build log, a stack trace | `Read` / grep | not code |
| read back a file **you edited moments ago** | `Read` | the index refreshes in the background; the graph may be stale for your own change |
| find anything in a file `check_index_coverage` reports as skipped or parse-partial | grep | the graph cannot see it, and says so |
| find a literal string, a TODO marker, a log message | `search_code` | text search, but the graph-aware form ranks by structure |

Two failure modes, one on each side. Grepping for `func Foo(` to locate a
definition is discovery by grep — the violation. Calling `get_code_snippet`
twenty times to reconstruct a file you should have Read once is the mirror
image: content by graph, slower and lossier, and just as wrong.

**Why MUST.** Measured runs showed 1,262+ grep/Read discovery calls and **zero**
graph calls with every repo indexed. On the first lean run the worker launched *with*
the directive still made 1 graph call against 37 grep/Read calls: the directive
at the top of a long prompt did not survive into the steps. So it is stated
twice in every review agent's prompt — once in the preamble and once at the head of
the task — and the orchestrator, which reads this document rather than a
prompt, re-reads Rule A at the start of steps 2, 3, and 4.

**Enforced by a hook, not by this paragraph.** Measured on the first six
slopstop-q runs: 18 graph calls
against 243 greps and 33 Reads, a 6% graph share, with the text above in every
session's context. Prose moved nothing. So each consuming repo registers
`~/ticket-plugin/tools/graph-first-hook.py` as a `PreToolUse` hook on `Bash`,
`Grep`, and `Glob` in its gitignored `.claude/settings.local.json`. The hook:

- **blocks** `Grep` and `Glob` outright, and any Bash command where `grep`,
  `rg`, `ug`, `ag`, `find`, or `git grep` *starts* a pipeline segment — that is
  a search over the tree, which is discovery;
- **allows** those same commands when fed by a pipe (`go test ./... | grep
  FAIL`, `ls | grep`) — that is filtering output, which is content;
- **allows** a tree search that carries a trailing marker,
  `<command>  # content: <why the graph cannot answer this>`;
- **logs** every block and every marked call as one JSON line to
  `.slopstop/graph-first.log` in the repo (or `~/.claude/graph-first.log`
  when no `.slopstop/` exists).

The marker is the escape hatch and it is still the model's claim; the log is
what makes the claim countable. The measure of Rule A from now on is that
log, not the transcript: blocked count, marked count with reasons, and graph
calls from the transcript alongside. A session that reads this and reaches
for `grep -rn "func Foo"` gets the block message naming `search_graph` and
`trace_path`, which is the reminder at the moment it matters instead of at
the top of a document.

### Rule B — the reuse ladder (keep generated code small)
#### Stolen almost in its entirety from [DietrichGebert/ponytail](https://github.com/DietrichGebert/ponytail)

For each change, before writing new code, stop at the **first rung that holds**:

1. **Does the codebase already have this?** `search_graph` / `search_code` → call it.
2. **Does the stdlib do it?** → use it.
3. **Does the platform or framework provide it natively?** → use it.
4. **Does an installed dependency already cover it?** → use it.
5. **Can it be done in one expression?** → one expression.
6. **Only then:** write the minimum new code that satisfies the tests.

A new helper, class, or dependency that duplicates something on the ladder is a
**defect**, not a style choice. The tests define the contract; the ladder decides
how little code satisfies it.

**Lazy about the solution, never about understanding.** The ladder runs *after*
you have read the code the change touches and traced the real flow — not instead
of it. Skipping a rung because you did not look is not the same as checking and
finding nothing. Rung 1 is a graph query (Rule A), never a grep.

**Safety is never on the ladder.** Trust-boundary validation, error handling,
data-loss guards, security checks, and accessibility are never candidates for
"does this need to exist?" Cutting them is a defect regardless of line count.

**The reviewer checks the ladder too.** Over-engineering is a review finding: a
wrapper around a stdlib or framework call that adds no behaviour; a class where
a function suffices; a new dependency where stdlib or an installed dep already
covers it; an abstraction layer with exactly one implementation and no
documented reason to expect a second. The reviewer verifies with `search_graph`
/ `search_code` before flagging — and flags when it finds one.

## The loop

Rule A governs every discovery in every step; Rule B governs every line written
in step 4.

1. **Worktree, and move the session into it.** From the primary checkout:
   ```
   git -C <primary> fetch origin
   git -C <primary> worktree add .claude/worktrees/<TICKET> -b <prefix>/<TICKET> origin/master
   EnterWorktree(path: "<primary>/.claude/worktrees/<TICKET>")
   ```
   Prefix per CLAUDE.md (`fix/`, `feat/`, …). Branch from `origin/master`, not
   local `master`: with several sessions merging in parallel, the local branch
   is behind more often than not. Create the worktree with git, not
   `EnterWorktree(name:)`, so the branch carries the ticket name and cleanup
   stays in your hands (`ExitWorktree` never removes a worktree entered by
   `path`). After entry the session's cwd *is* the worktree: relative paths and
   file tools resolve there, and the cwd guardrail no longer applies
   inside the session. The primary checkout stays on `master` and is never
   edited. Then do the repo's worktree setup (see "Worktree setup gotchas").
   **Graph index — default: share the primary's.** A single-ticket branch
   rarely changes enough structure to need its own graph; the primary's index
   (which tracks `master`) is accurate at the branch point and stays close
   enough for discovery. Skipping the per-worktree index also avoids the
   indexer lock, which blocks parallel sessions: a session that holds the lock
   starves every other `index_repository` call until it finishes (measured
   four parallel slopstop-q sessions, three retries failed on
   every one). So by default, **do not call `index_repository`**; Rule A's
   `list_projects` check passes when the primary's project is present, and
   graph queries answer about `master`, which is the branch point.

   **`--index`: per-worktree graph when the branch needs it.** If the
   invocation says `run slopstop-q on <TICKET> --index`, create a named
   project for the worktree:
   ```
   index_repository(repo_path: "<primary>/.claude/worktrees/<TICKET>", name: "<repo>-<TICKET>", mode: "fast")
   ```
   Measured 6 s on sophie. The watcher keeps it fresh as you commit. When
   `--index` was used, step 6's cleanup must call
   `delete_project("<repo>-<TICKET>")` — stale projects are never cleaned up
   on their own. Without `--index`, step 6 skips that call.

   Use `--index` when the ticket adds, moves, or renames symbols that the
   review angles or ladder rung 1 need to find on the branch — not on `master`.
   Most bug fixes and small features do not qualify.

   Helpful, not compulsory: mark the ticket **In Progress** in the ticket
   system now, so a parallel session can see it is taken.
2. **RED test.** Locate the target with `search_graph`, not grep. Write the
   phase-0 test(s). Prove red **for the right reason** (fails on the real defect,
   not a guard or a typo). Commit as the RED commit.
3. **Investigate + plan.** Run `list_projects`; if the repo is indexed, map the
   change with the graph — `get_architecture` for layout, `search_graph` for the
   symbols, `trace_path` for the callers of anything whose signature moves,
   `get_code_snippet` to read them. Read whole files with `Read` only once the
   graph has named them. Decide the change. Keep it in your head or a scratch
   note — no ceremony.
4. **Implement → simplify → PR.** Walk the ladder for each piece before writing
   it. Make it green. Commit (RED then implementation = two commits; more only if
   warranted). Run the project's build and the targeted tests before each commit.
   **Before pushing**, run the simplify loop:

   **Simplify loop (max 3 rounds).** Invoke `Skill(skill: "simplify")`. If it
   returns findings, evaluate each: a finding that is exclusively about prose
   (comment wording, doc files, naming in a docstring) counts as clean — apply
   the ones you agree with and skip the rest. A finding about code, tests,
   config, or build files is a real finding: fix it, re-run build + targeted
   tests, commit the fix, and run `/simplify` again. Three rounds is the cap;
   if round 3 still has non-prose findings, proceed anyway — the review in
   step 5 is the gate, not simplify. A round with zero findings, or only
   prose findings, exits the loop immediately.

   After the simplify loop, verify topology — `git log master..<branch>` lists
   only this ticket's commits — then push and open the PR.
5. **Review: eight clean angles, all back, then verify; repeat.** Launch the
   eight review angles in "Launching the review" — **eight `Agent()` calls in a
   single message**. Never review inline, because this session wrote the code;
   never with `isolation: "worktree"`; each angle is pointed at the ticket
   worktree from step 1 and starts with a fresh context. The orchestrator
   launches them itself because nothing else can: a subagent has no Agent tool,
   so a review wrapper cannot fan out, and a skill that fans out internally
   (`/code-review`) hands back one combined result whose angle count cannot be
   checked. **Wait for all eight before reading any of them, and do not touch the
   worktree, the branch, or the PR meanwhile.** Results may arrive as background
   notifications; count them as they land. The gate is **LAUNCHED 8, RETURNED 8**,
   counted by this session from the results it actually received — never taken
   from anyone's report. Then launch the **verifier**, a ninth fresh agent, with
   the eight reports: it checks every finding against the code and returns the
   ones that hold. Act on the verifier's output only — the session that wrote the
   code never decides for itself which criticisms of it are valid. Apply the
   confirmed findings — including over-engineering findings, which are ladder
   violations — and run the whole review again, all eight angles, until CLEAN.
   **Prose-only findings count as CLEAN.** A round whose every finding is about
   text rather than behaviour — comment wording, doc files, commit or PR
   prose, naming in a docstring — clears the gate: apply the ones you agree
   with, skip the rest, and proceed to step 6 without another round and
   without asking the human. A finding about code, a test, config, or a build
   file is never prose, however small.
   **A round with no behaviour defect ends the review loop (adopted
   2026-09-28, SOP-651).** If every confirmed finding in a round is a test
   gap (a surviving mutant, a missing test) or prose, apply the fixes, re-run
   build + targeted tests, and proceed to the full-suite gate without
   another review round. A behaviour defect is code doing the wrong thing
   for some input. Basis: in the Jev ledger, rounds 2+ on sophie#457 and
   #478 found only test gaps; the rule is Ian's call, not a fitted
   threshold, and SOP-661 measures it against a Jev predictor.
   **A scope gap is not a stop.** If the work reveals that the ticket, as
   written, does not reach the user — a producer never wired to a path, a
   value stored but never read, a consumer that does not exist — merge what
   was built as-is, file a new ticket for the missing piece with the gap
   stated in one paragraph, and say so in the PR description and the ticket
   comment. Do not ask the human whether to merge. The human sees the gap in
   the new ticket, which is the right place to decide its priority.
   **The full suite gates the merge.** Before merging, merge current `master`
   into the branch, run the project's full test command (sophie: `task test`),
   and push. Merge only if it is green on that head. The targeted tests run
   before each commit are not enough: they cannot see a break that `master`
   brought in, or one this branch causes in a package it never touched.
   **A clean review and a green suite mean proceed** — go straight to step 6
   without asking. Hand the merge to the human only when something went wrong:
   the review would not come clean, a finding needs a judgement call you cannot
   make, the suite is red, the branch topology is off, or fewer than eight angles
   came back. "Clean review → merge" is the default; stopping is the exception
   that needs a reason.
6. **Merge and clean up.** Merge with a real merge commit, never squash or
   rebase (rule 3):
   ```
   gh api -X PUT repos/<owner>/<repo>/pulls/<PR#>/merge -f merge_method=merge
   ```
   or the GitHub tool's merge with `merge_method: merge`. Not `gh pr merge`: it
   uses GitHub's GraphQL API, which Claude Code cloud sessions cannot reach, and
   the REST call works in both places. Then, in order:
   ```
   delete_project("<repo>-<TICKET>")                  # only if --index was used; graph projects are never cleaned up on their own
   ExitWorktree(action: "keep")                       # back to the primary; keep = we remove it ourselves
   git -C <primary> worktree remove .claude/worktrees/<TICKET>
   git -C <primary> branch -d <prefix>/<TICKET>
   git -C <primary> push origin --delete <prefix>/<TICKET>   # skip if the merge already deleted it
   git -C <primary> pull --ff-only origin master      # may fail if a sibling session just merged; re-run
   ```
   Push `master` to every other remote the project has. Helpful, not
   compulsory: advance the ticket **one state** — in a three-state workflow that
   is Done; in a four-state workflow it is the third state (review/verify), not
   Done. `ExitWorktree` comes first because removing the directory the session
   is standing in leaves it nowhere. The `--ff-only` pull is the only step that
   can collide with a parallel session; it fails cleanly rather than merging,
   so re-run it.

## Launching the review — eight angles and a verifier

Each agent starts with no context. It will not follow a rule it cannot see, and
it will not follow a rule it saw only once at the top of a long prompt. And it
must not be handed the author's account of the code: the prompt carries the
rules, the location and the one angle, never this session's view of what the
code does or why.

**The eight angles.** Each covers one kind of defect and stays in it; the other
seven cover the rest.

| # | angle | what it looks for |
|---|---|---|
| 1 | **logic** | control flow and conditions: wrong branch, off-by-one, a return that skips work, unreachable or dead code |
| 2 | **failure paths** | error handling and partial failure: what the caller sees when a dependency fails, silent drops, an empty or nil result reported as success |
| 3 | **concurrency, time and lifetime** | races, deadlocks, leaked goroutines, connections or timers, context and deadline handling, ordering assumptions |
| 4 | **contracts and callers** | every caller of a changed signature or behaviour, interface implementations, wire formats, protocol frames, config keys |
| 5 | **data and state** | persistence, schema and migrations, invariants, idempotency, a value stored but never read or read but never written |
| 6 | **security and trust boundaries** | input validation, auth, secrets in logs, injection, what untrusted input can reach |
| 7 | **tests** | whether each test fails without the change (red for the right reason), asserts the behaviour it names, and would catch a plausible regression; changed behaviour with no test |
| 8 | **ladder and project rules** | Rule B over-engineering, and the repository's own `CLAUDE.md` rules |

**Each angle's `Agent()` call:**

```
Agent(
  description: "Review angle <n>/8 (<angle>) — <TICKET> PR <N>",
  # No subagent_type, no model, no effort: the angle inherits the model and
  # effort of the session that launched it.
  # NO isolation: "worktree" — the angle reads the ticket worktree itself.
  prompt: <the block below>
)
```

The prompt, top to bottom:

1. **Rule A**, verbatim (the fenced block, not a paraphrase).
2. The worktree path, the branch, the PR number, and `cd <worktree> &&` on every
   shell command (see "Guardrails").
3. **Rule B's over-engineering paragraph** ("The reviewer checks the ladder
   too…"), verbatim.
4. **The angle**: its name and its row from the table above, and "stay in this
   angle; seven others cover the rest."
5. **Read-only, verbatim:**
   ```
   Eight reviewers read this worktree at the same time, so you must not change
   it. To try anything -- a mutation, a probe test, a flipped assertion -- work
   in a private copy:
     git -C <worktree> worktree add --detach /tmp/review-<angle> HEAD
   and remove it when you are done:
     git -C <worktree> worktree remove --force /tmp/review-<angle>
   ```
6. **Rule A again**, immediately above the task line.
7. The task: review `git diff origin/master...HEAD` in the worktree for this
   angle only.
8. **The return format, verbatim:**
   ```
   The FIRST line of your return is:
     ANGLE: <name>   FINDINGS: <n>
   Then one block per finding:
     <file:line> -- <the defect, one sentence> -- <a concrete failure: inputs
     -> wrong output> -- CONFIRMED (you ran code) | PLAUSIBLE (from reading)
   No findings: FINDINGS: 0 and nothing else.
   ```

**The count.** The orchestrator counts the eight results it received. An angle
that errors or returns nothing usable is relaunched once; if it is still
missing, the round is short, and a short round hands the merge to the human.

**The verifier**, launched once all eight are in: a ninth `Agent()` call, the
same form, whose prompt carries Rule A, the location, the read-only block, Rule
A again, and the eight reports verbatim, with the task:

```
For each finding in the eight reports, check it against the code in the
worktree -- run it wherever you can -- and mark it CONFIRMED, REFUTED (say why)
or PLAUSIBLE (could not run it). Merge duplicates. Add nothing new.
The FIRST line of your return is:
  REVIEW: CLEAN | FINDINGS (<count of CONFIRMED and PLAUSIBLE>)
```

The orchestrator applies CONFIRMED findings, weighs PLAUSIBLE ones, and states in
the PR which it refuted and why. The prose-only rule in step 5 applies to the
verifier's output.

## History — why the review is no longer a wrapped `/code-review`

**What actually happened on an early run, from the transcript** (read with `review-angle-audit.py`, a transcript reader — not from anyone's
report):

| time (UTC) | event |
|---|---|
| 22:49:16 | orchestrator launches the review wrapper with `isolation: "worktree"` |
| 22:50:38–22:51:40 | wrapper's `/code-review` spawns 8 angles; they inherit the wrapper's isolation worktree |
| 22:51:46 | **wrapper returns** with "I'll wait for the background agents to complete before continuing." — the orchestrator receives that sentence as the review result |
| 22:52:13 | **orchestrator removes the wrapper's worktree** ("worktree removed … Deleted branch worktree-agent-a1cdf…"), 27 s after the wrapper returned, following the handoff cleanup rule |
| 22:52:04–22:53:59 | **all 8 angles finish anyway**; their completion notifications land in the orchestrator's session, not the wrapper's |
| | 6 of 8 report the worktree vanished under them mid-read; 2 had finished before removal |

So the story as initially recorded ("four of eight lost") is imprecise in both
directions. No angle was killed: all eight completed, and every one produced a
final report. But six were cut off from the code partway and finished from
memory, and none of the eight results ever reached the wrapper, because the
wrapper had already returned. The two bugs are:

- **The wrapper ended its turn while its background agents were running.** The
  harness did not force this; the wrapper chose to.
- **The orchestrator treated the wrapper's return as "review done" and ran
  cleanup.** Nobody deleted the worktree by hand; the `:run` orchestrator did,
  on schedule, because nothing told it the return was not a result.

**Neither bug can recur under the eight-angle review.** There is no wrapper to
return early, and the eight results arrive at the orchestrator directly, so the
count is observed, not reported. The transcript reader that measured the wrapped
form, `review-angle-audit.py`, is no longer part of the loop. The wrapped form
was also unverifiable in Claude Code cloud sessions, where `/code-review` ran as
one combined job and never exposed how many angles ran.

## Running it — how a repo adopts this, and running tickets in parallel

**Adopt.** Add to the consuming repo's `CLAUDE.md` (project-specific section,
below the universal rules):

```markdown
## Ticket loop (slopstop-q trial)

For any ticket, follow `~/ticket-plugin/docs/slopstop-q.md` exactly. Invoke as:
"run slopstop-q on <TICKET>". Rules A and B in that file bind this session.
Nothing else slopstop is installed here: no `/slopstop-*` commands, no
`.claude/skills/slopstop-*`, no `.claude/rules/universal.md`, no tier-carrier
agents. The file is self-contained and carries the universal rules itself.
```

That is a path to a gitignored file on one machine, which is fine for the
trial; if it survives, the doc moves to a tracked location (rule 10).

**Start a ticket.** Open a new session in the primary checkout and say
`run slopstop-q on <TICKET>`. The session reads this file, runs step 1, and is
thereafter inside the worktree for the rest of the loop.

**Parallel tickets.** One session per ticket, each started the same way. What
they share and what keeps them apart:

| shared | how it stays safe |
|---|---|
| `origin/master` | every branch is cut from it at step 1; the merge in step 6 is a real merge commit, and the `--ff-only` pull retries on collision |
| the primary checkout | read-only for every session except the step-6 pull; nobody edits it |
| `.claude/worktrees/` | one directory per ticket, named by ticket; no session touches another's |
| the ticket tracking dir | `$TRACKING_DIR/<TICKET>/` is per ticket (rule 8) |
| the review bot's rate limit | opportunistic anyway (rule 9); parallel PRs just make silence more likely |
| the codebase-memory index | by default all sessions share the primary's project (which tracks `master`); no lock contention. With `--index`, each session creates its own named project (`<repo>-<TICKET>`) — these contend on the indexer lock, so only use `--index` when the branch's structural changes require it. The primary's project refreshes on the step-6 merge without any hook |

Not shared: branch, worktree, PR, session context. Two sessions cannot review
each other's code by accident because neither launches anything into the
other's worktree.

**Rule A is enforced by the hook in `.claude/settings.local.json`** (see
Rule A). Adopting the loop in a new repo means adding that hook entry; without
it the loop runs but Rule A is prose again.

**Settled by probing the server (v0.10.8):** `list_projects` does
not report a worktree unless `index_repository` was run on it by name; the
primary project's `not_indexed` list includes `.claude`; a fast-mode index of a
sophie worktree takes 6 s; stale projects for removed worktrees are never
cleaned up. The README documents no git hook or CI step, and none is needed —
the watcher polls git state per registered project. **Addendum:**
the indexer holds a per-project lock for the duration of the run. Parallel
sessions calling `index_repository` contend on it — three retries failed
across four concurrent slopstop-q sessions. This is why the default is now to
share the primary's index and only call `index_repository` with `--index`.

## Guardrails

- **The cwd guardrail, now narrowed.** In slopstop-light the session stayed in the
  primary and `cd`-ed into the worktree on every command; the shell cwd
  silently reset to the primary mid-session and relative `go test`/`grep` ran
  against `master`, returning bogus passes (`[no tests to run]` matches a naive
  `^ok ` grep). `EnterWorktree` removes that for the orchestrator: the session's
  cwd is the worktree. It does **not** remove it for the review agents — a subagent
  without `isolation` inherits the cwd at launch but its shell can still reset —
  so every angle's prompt keeps `cd <worktree> &&` on every shell command and
  absolute paths to file tools. And any command run against the primary
  (step 6) uses `git -C <primary>` explicitly.
- **After every review round, verify the worktree is clean.** The angles are
  read-only on your worktree and experiment in private copies. Confirm it:
  `git -C <worktree> status --short` empty, HEAD unmoved, in sync with origin,
  and no `/tmp/review-*` worktrees left (`git -C <worktree> worktree list`).
  (Related known hazard: a review subagent once left a checkout in detached HEAD.)
- **The graph can be stale for your own edits.** The index refreshes in the
  background. Read back a file you just changed with `Read`; do not trust
  `get_code_snippet` to reflect an edit made seconds ago.

## Worktree setup gotchas (per repo)

Repo-specific setup — `GOWORK=off`, exported env vars, gitignored assets that
`go:embed` needs copied in — lives in each consuming repo's own copy of this
doc or its `CLAUDE.md`. sophie and aatoolkit both need `GOWORK=off` on every go
command; sophie additionally needs `SOPHIE_DB_URL` and the two demo `.ulaw`
clips copied into the worktree. Record any new one where it
was found, not here.

## What's dropped vs full slopstop

The fleet, mutation/vacuity/slop/complexity gate skills, the stage-10b handoff
blessing bound to a tip SHA, and adversary rounds. Re-add a specific gate only
when a ticket's risk earns it. The non-negotiables that stay: **a clean-context
review of eight angles, all eight back, verified, until CLEAN; a green full
suite before merge; graph for discovery; the reuse ladder before every new
line.**

## Universal rules this loop runs under

slopstop-q is self-contained: the rules below are the ones from Ian's universal
project rules that bind this loop, restated here so nothing depends on another
file being loaded. Where a rule and this loop disagree, the disagreement is
named rather than papered over. Section numbers match the universal file.

### 1. Pre-commit

- **Quality review happens once, at PR time — not before every commit.** The
  review in step 5 reads the whole branch diff, so nothing escapes by being
  committed early. Commit freely; the gate is at the merge. (Measured
  a multi-agent cleanup pass before every commit cost 13–30 min and
  missed the most serious defect in its own diff, which a single review pass
  found in ~4 min.)
- Run the project's build and targeted tests (the package or area you touched)
  before each commit. Run the full suite only when touching shared or
  cross-cutting code.
- Commit, then push — only after the above are clean. **If the project has
  multiple remotes, push to all of them.**
- A project with no test suite is a deliberate, documented exception, never a
  default. It must say so in its own `CLAUDE.md` and state what it validates
  with instead.

### 2. Tests

- **Tests-first for new behaviour and for fixes.** Write the test describing the
  contract; confirm it is red **for the right reason** before implementing. For a
  bug fix the test must reproduce the bug: red before, green after. Trivial
  tweaks, copy changes, and pure refactors are exempt.
- **A failing test is signal, not chore.** Investigate the root cause before
  changing anything. Never delete a test, narrow an assertion, skip it, or cite
  an unverified "flake" to silence it.
- Rule B's ladder decides how little *code* satisfies the tests. It never
  licenses touching the tests to need less code.

### 3. Git

- **Never squash-merge or rebase-merge.** A real merge commit (step 6's
  `gh api … /merge -f merge_method=merge`). Squash and rebase lose fixup context
  and break `git bisect`.
- Always name the branch: `git push origin <branch>`.
- Never `git push --force`, `git reset --hard`, `git commit --no-verify`,
  `git push --no-verify`, or an admin-override merge unless the user explicitly
  asks. When a hook or check fails, fix the cause; do not bypass.
- New commits rather than amending. Sole exception: one fresh commit on a solo
  branch nobody has pulled.
- **One ticket, one branch, one PR, cut from `master`.** Never branch off
  another feature branch: the PR then carries a different ticket's work and the
  review and test evidence cover two tickets at once. If you need something on
  an unmerged branch, wait or raise the dependency; do not stack.
- **Expected shape: two commits — the RED test commit, then the
  implementation.** More is fine when warranted, but every commit belongs to
  this ticket. A cleanup noticed in passing goes on its own branch, even a
  one-line deletion.
- **Verify topology before opening the PR:** `git log master..<branch>` must
  list only this ticket's commits. If it shows a parent's work, rebase onto
  `master` and re-run the tests; results gathered on a stacked branch proved
  nothing about this ticket alone.

### 4. Refactoring scope

- **Dedupe is in scope.** Two or more near-identical code paths found while
  working → extract the helper and migrate the duplicates in the same PR. This is
  ladder rung 1 seen from the other side.
- **Structural changes are out of scope without discussion.** Renaming exported
  symbols, altering public signatures, moving files, reshaping module
  boundaries: raise them separately.
- Study the existing types and patterns first; mirror existing vocabulary. This
  is the ladder's "lazy about the solution, never about understanding" clause.
- "Nearly passing" is failing. Do not declare done by cherry-picking the easy
  cases.

### 5. Source of truth

- One definition per value. No duplicate constants, aliases, or parallel names.
  Rename by updating every reference, never by adding an alias.
- Never edit generated files by hand.
- **Applied to this document:** Rules A and B and the graph table are copies of
  text that also lives in slopstop's `worker-launch.md`, `stages-lean.md`, and
  the `implement` and `review` skills. While this file is a gitignored local
  doc that is tolerable; the day it is tracked, one of the two must become the
  reference and the other a pointer.

### 6. Agents and worktrees

Coordinator side:

- **Commit and push before launching the review** — it reviews the PR, and
  the PR is what was pushed.
- The orchestrator's own worktree is entered with `EnterWorktree(path:)`, which
  the universal rule permits because a project instruction (this file, via the
  consuming repo's `CLAUDE.md`) directs it.
- Fine-grained milestones: a check-in every few minutes of work, not every ten
  seconds and not every twenty minutes.
- Parallelise only where merge-back cannot conflict. Small tasks stay on your
  own plate.
- **Never use `open` to display files** unless the user explicitly asks.

Every agent prompt carries:

- Run on a separate branch in a separate directory; prepare it first if the
  project needs it (symlink large untracked dependency dirs, copy gitignored
  assets — see "Worktree setup gotchas").
- Commit only to the worktree's branch. Never touch `master` from a worktree.
- Commit and report at every milestone, not just at the end.
- Never use `open`.
- **Restate the relevant project rules verbatim.** Agents start with no prior
  context and will not follow rules they do not see. This is why "Launching the
  review" above carries Rules A and B in full, and Rule A twice.

### 8. Documentation layout

- `docs/` is gitignored — personal notes, scratch, drafts. This file lives there
  for now.
- `design/` is tracked; nothing is added to it without explicit user
  confirmation.
- Ticket-specific notes (continuation prompts, mid-flight notes, each review
  round's angle count and verifier report) go in the ticket's
  tracking directory `$TRACKING_DIR/<TICKET>/`, resolved in order: explicit
  `tracking_dir` in `.project-conf.toml`; else `.slopstop/ticket-active` when
  `.slopstop/` exists at the worktree root; else `~/.claude/ticket-active`.

### 9. Automated PR review

- **The gate is a review by a context that did not write the code, and every PR
  gets one.** The session that wrote the code never reviews it and never decides
  which criticisms of it are valid. Isolation
  comes from the launch form — a subagent has its own context window and no
  access to the conversation that wrote the code. A review run inline in the
  authoring session is not isolated, whatever skill it uses.
- **The gate is eight clean-context angles and a verifier, launched by the
  orchestrator** (step 5). Isolation comes from the launch form; completeness
  comes from counting the eight results this session received. Neither is
  taken on any reviewer's word.
- **`/code-review` is not the gate.** It fans out internally and returns one
  combined result, so how many angles ran cannot be checked; a subagent cannot
  fan out at all, having no Agent tool; and a wrapped `/code-review` lost six of
  eight angles' access to the code in an early run (see History).
- **Bot reviews are opportunistic: read them if already there, never wait.**
  Before merging, look once. A real review: work its findings, verifying each
  against the code and stating which you refuted and why. A non-review notice
  (`Review limit reached`, `auto reviews are disabled`) or silence: proceed on
  the step-5 verdict. Do not post `@coderabbitai review` to force one.
- With multiple remotes, prefer the GitHub remote for any hosted review bot.

### 10. Where a new rule lives

- Project-specific tip or bug record → that project's memory dir, indexed in
  `MEMORY.md`.
- Project-specific rule every session must follow → that project's `CLAUDE.md`.
- Universal rule → the reference copy in the slopstop repo
  (`.claude/rules/universal.md`), then propagate with `setup-project.py`. Never
  edit a mirror. A project overrides with a section headed
  `## <Topic> (overrides universal §N)` in its own `CLAUDE.md`.
- **Consequence for Rules A and B:** today they bind only workers launched by
  slopstop's `:run`, and this loop's orchestrator and review agents. If they are to bind every agent in every
  project, they go into the universal file by this route, and this document
  becomes a pointer (rule 5).

Omitted as not bearing on this loop: 7 (never modify PATH by hand).

## Provenance — what to compare against ponytail

The ladder was added to slopstop's `implement` worker,
"inspired by DietrichGebert/ponytail's approach to reducing unnecessary code
generation", and the matching over-engineering signal went into the `review`
worker in the same commit. Our differences from the ponytail idea, for anyone
lining the two up:

- **Rung 1 is a graph query.** Ponytail's "does it already exist?" check is a
  search; ours is `search_graph` / `search_code` against an indexed repo, and a
  grep there is a Rule A violation.
- **The ladder is gated behind understanding.** It runs after the code is read
  and the flow traced, never as a substitute for reading.
- **Safety is carved out explicitly**, by category, rather than left to
  judgement.
- **The reviewer enforces it**, not just the author: over-engineering is a
  named review finding with a verification step.
- **Frozen tests still bind.** The ladder decides how little code satisfies the
  tests; it never licenses changing the tests to need less code.
