---
description: Retrofit an existing ticket to the five-section leaf-ticket standard so it can be handled by :plan --ticket-driven or a fleet run. Interviews toward the missing structure with /slopstop:grill, drafts the five sections, runs the huge-tier adversary loop, then confirms and pushes — preserving the original ticket verbatim below a separator. Interactive only. Invoke as /slopstop:single-ticket <TICKET-ID>.
disable-model-invocation: true
---

# /slopstop:single-ticket

A raw ticket — a bug report, a one-line ask, anything not written through the slopstop
process — usually lacks the structure `:plan --ticket-driven` or a fleet run needs:
observable behaviors, a file map, a Definition of Done, out-of-scope fences, test
expectations (`skills/tickets/references/ticket-standard.md`). `/slopstop:tickets`
produces that structure, but only for new tickets cut from a PRD. This skill retrofits
**one existing ticket** to the same standard, using the same two pieces of machinery
`:tickets` uses per leaf — `/slopstop:grill` to interview toward the missing structure,
and the huge-tier adversary loop to verify the result — applied to a single ticket
instead of a whole tree.

**The original ticket is never discarded.** The rewritten description always ends with
the untouched original content below a `---- ORIGINAL TICKET BELOW ----` separator.

**Interactive only.** No `[autonomous]` path — this rewrites content a human filed, and
the confirm step is not optional.

## Project scope

Read `.project-conf.toml` from cwd; if absent, fall back to the main worktree at
`dirname "$(git rev-parse --git-common-dir)"`. Extract `system`, `$PREFIX` (`prefix`
field), `[tiers]` (defaults fable/opus/sonnet/haiku), `[fleet.router]` (default
disabled). Stop with a clear error if `prefix` is absent; stop if it doesn't match
`^[A-Za-z][A-Za-z0-9]*$`. Missing config file: stop with the standard gh-init message.
Missing tables → defaults.

For the **GitHub backend**, also read `pr-repo` (optional): `$OWNER` and `$REPO` =
`pr-repo` if present, else parse from `key` (e.g. `"iansmith/slopstop"` →
`$OWNER=iansmith`, `$REPO=slopstop`).

## Arguments

`$ARGUMENTS` — the ticket to retrofit, e.g. `BILL-1234`. **Mandatory** — there is no
"current ticket" fallback (no branch to infer from; this isn't tied to an in-flight
`:start`/`:plan` session). Empty → stop: `"Usage: /slopstop:single-ticket <TICKET-ID>"`.
Must match `^$PREFIX-\d+$`; a different prefix → stop: `"$ARGUMENTS doesn't match this
project's prefix ($PREFIX)."`

## Step 1 — Tier gate

Resolve the required model in two hops, reusing `:tickets`' own tiers — no dedicated
`single-ticket` tier: `[stage_tiers].tickets` names the authoring tier (default
`large`), then read `[tiers].<that tier>` for `provider`, `model` (family, `$MODEL`),
and optional `version` (`$VERSION`). **`provider` is never gated on** (router-only). If
`[tiers].<tier>` is still the old bare-string form, **hard stop**: `"[tiers].$TIER is
the old string form; use the table form [tiers.$TIER] with provider/model (+ optional
version). Migrate .project-conf.toml."`

Match the session model: family `$MODEL` must appear in the session model; a pinned
`$VERSION` must be a dotted prefix of the session model's version; an omitted version
passes any version of the family.

- **Match** → proceed. **Mismatch** → hard stop: `"Tier gate: /slopstop:single-ticket
  requires the $TIER tier ('$MODEL', version $VERSION when pinned); this session is
  running '<session model>'. Relaunch on the right model."`
- **Cannot determine** → ask the user to confirm the tier; never proceed silently.

Also resolve `[stage_tiers].ticket_adversary` (default `huge`) → `[tiers].<that tier>`
for `$ADV_MODEL` (the family value — `opus`/`sonnet`/`haiku`/`fable` — matches the
Agent tool's `model` parameter directly). This is for Step 5; no gate on it here, since
it governs a spawned subagent, not this session.

## Step 2 — Fetch the ticket (the artifact boundary)

The existing ticket is the *only* input — no local plan or PRD is read.

```
ToolSearch(query="select:mcp__atlassian__getJiraIssue,mcp__atlassian__getAccessibleAtlassianResources", max_results=8)
ToolSearch(query="select:mcp__linear-server__get_issue,mcp__linear-server__list_comments", max_results=8)
ToolSearch(query="select:mcp__github__get_issue,mcp__github__list_issue_comments", max_results=8)
```

Set `$SYSTEM` from `.project-conf.toml`'s `system` field:

- **JIRA** — JIRA ToolSearch must be non-empty (else stop: `"system='jira' in
  .project-conf.toml but no Atlassian MCP found."`). Get cloudId via
  `mcp__atlassian__getAccessibleAtlassianResources`, then
  `mcp__atlassian__getJiraIssue($TICKET, cloudId, fields=["status","description","summary"])`.
  Comments via the Atlassian comment-list tool (or comment-expanding field on the same
  call).
- **Linear** — Linear ToolSearch must be non-empty (else stop: `"system='linear' in
  .project-conf.toml but no Linear MCP found."`). `mcp__linear-server__get_issue($TICKET)`
  + `mcp__linear-server__list_comments(issueId=$TICKET)`.
- **GitHub** — resolve `$GH_BACKEND`/`$GH_MCP_NS`: canonical `mcp__github__*` ToolSearch
  non-empty → MCP, `$GH_MCP_NS = "mcp__github__"`. Else fallback ToolSearch for
  `mcp__plugin_github_github__*`; non-empty → MCP with that namespace. Both empty → CLI:
  find `gh`, verify auth, stop if absent. `$N` = numeric suffix of `$TICKET`. MCP:
  `${GH_MCP_NS}get_issue(owner=$OWNER, repo=$REPO, issueNumber=$N)` (read `body`) +
  `${GH_MCP_NS}list_issue_comments(...)`. CLI: `$GH issue view $N --json body,title` +
  `$GH api repos/$OWNER/$REPO/issues/$N/comments`.

Store the fetched title + body as `$ORIGINAL_BODY` — this is preserved verbatim (Step 4)
and is the primary raw material for the grill (Step 3). Store comments as
`$ORIGINAL_COMMENTS` — context for the grill only (triage discussion, repro notes often
live there), never duplicated into the pushed description; they already persist as their
own comments on the ticket, untouched by this skill.

## Step 3 — Grill toward the missing structure

```
Skill({skill: "slopstop:grill", args: "Raw ticket $TICKET needs to be rewritten to the
five-section standard (observable behaviors, file map, definition of done, out of
scope, test expectations). Interview toward whatever the original doesn't already
answer — explore the codebase first where that resolves a question instead of asking.
Original ticket:\n\n$ORIGINAL_BODY\n\nComments (context only):\n\n$ORIGINAL_COMMENTS"})
```

Same calling convention `:design` Step 4 uses for the same skill. One question at a
time, recommended answers argued, codebase exploration substituted for questions where
possible. The grill ends when no unresolved branches remain; its consolidated summary
is the raw material for Step 4.

## Step 4 — Draft the five-section body

Author from the grill's consolidated summary, using the standard's template:
→ Read `~/.claude/commands/slopstop-tickets-refs/ticket-standard.md`

Provenance header uses the standard's stage-label escape hatch (no run-id, no PRD — a
single-ticket retrofit has neither):

```
> Provenance: <model> · <UTC date> · single-ticket rewrite · source: $TICKET
```

**No `Parent:` line.** Tickets retrofitted by this skill are a documented exception to
the "leaf tickets always live under an umbrella" structural rule — freestanding leaves
(see the note in `ticket-standard.md`). If the ticket already has a real parent
(umbrella/epic) on the ticket system, preserve that relationship as-is; do not invent
one and do not require one.

Run the standard's mechanical structural checklist yourself first (five sections
non-empty, 2–5 observable behaviors, concrete file map, provenance header) — free fixes
before spending the adversary on it.

Append the preserved original, unmodified, after the five sections:

```
---- ORIGINAL TICKET BELOW ----

$ORIGINAL_BODY
```

Set `$DRAFT` to the full assembled body (five sections + separator + original).

## Step 5 — The adversary loop (≤3 rounds)

Spawn a **fresh** adversary subagent — `Agent(subagent_type: "general-purpose", model:
$ADV_MODEL, description: "Adversary review of $TICKET retrofit", prompt: <template>)` —
fresh context, no conversation history. Fed **only** `$DRAFT` and the original ticket
content — never your narrative of the grill conversation. Adapted prompt template
(structural check kept verbatim minus the parent-link bullet; coverage/scope checks
reframed against the grill's understanding instead of a PRD):
→ Read `~/.claude/commands/slopstop-single-ticket-refs/single-ticket-adversary.md`

The adversary returns PASS, or FAIL with findings that are specific (section, defect,
what would fix it). On FAIL: apply the corrections to `$DRAFT`, then send the corrected
draft back to the **same** adversary for re-verification — it must re-read the file,
never trust the claim of correction. **At most 3 rounds** (initial + 2 corrections).

- PASS → Step 6.
- FAIL round 1/2 → apply every finding (one you disagree with is argued in the
  correction note, never silently ignored), re-verify.
- FAIL round 3 → stop; present the surviving findings and `$DRAFT` to the human. The
  human may overrule specific findings or send it back for a rethink. Nothing is
  pushed.

## Step 6 — Confirm with the user

Always interactive — no `[autonomous]` path skips this. Show `$DRAFT`'s five-section
body (not the preserved-original tail — nothing to review there, it's unmodified) and
the adversary outcome:

```
Retrofitted $TICKET — adversary: PASS after <n> round(s)

<the five-section body>

Push this to $TICKET? (yes / no / edit)
```

- `yes` → Step 7.
- `no` → stop. Nothing pushed, nothing changed on the ticket.
- `edit` → apply the requested changes to `$DRAFT`, re-show, re-ask. (No re-adversary
  pass on a human edit unless the edit is substantial enough that you judge it worth
  re-checking — use judgment, don't force a full extra round for a wording tweak.)

**No title-version bump** (`(V2)`, etc.). That convention (`ticket-standard.md` §
"Version convention — rewrites") is for Stage-3 failure-driven relaunches — a fresh
implementation contract after a failed attempt. This is a structural upgrade, not a
relaunch; the title is left as-is.

## Step 7 — Push

Update the ticket's description in place with `$DRAFT`. Reuse the existing per-backend
update primitives — do not reinvent them:
→ Read `~/.claude/commands/slopstop-document-refs/document-push-backends.md` (§6a)

**Do NOT touch ticket status.** Post a short comment noting the retrofit (§6b's
comment-posting primitives, reused for a one-off note, not the DoD-shape comment):

```
Ticket rewritten to the slopstop five-section standard via /slopstop:single-ticket.
Adversary: PASS after <n> round(s). Original content preserved below the description's
"---- ORIGINAL TICKET BELOW ----" separator.
```

On failure: warn (`"Could not push retrofit to $TICKET: <error>. $DRAFT is above —
retry manually or re-run /slopstop:single-ticket $TICKET."`) and stop — do not retry
automatically.

## Step 8 — Confirm and summarize

```
$TICKET retrofitted to the five-section standard.

Adversary:  PASS after <n> round(s)
Ticket:     <ticket URL>
Original:   preserved below the description's separator
```

## Rules

- Adversary always at the configured ticket-adversary tier (`[stage_tiers].ticket_adversary`,
  default `huge`), always fresh, always artifact-fed, ≤3 rounds — same discipline as
  `:tickets`' own loop.
- Original ticket content is never discarded, never silently edited — preserved
  verbatim below the separator, every time.
- Never transitions ticket status. Never bumps a title version — this isn't a
  failure-driven rewrite.
- Interactive only. No `[autonomous]` key has any effect on this skill.
- Nothing pushed until Step 6's explicit `yes`.
