# PR: Final Confirmation Summary (Step 8)

**Source this summary from `$TRACKING_DIR/$TICKET/` (`progress.md`, `gates.json`), not from
conversation.** Reconstructing it from conversation is the behavior this replaces — a
compacted or resumed session has no conversation to reconstruct from, but the tracking dir is
durable across both. Each gate's line below comes from its own `gates.json` entry (written at
Steps 0b, 0c, 2, 2d, 2e, 2f, 6 per `gates-json.md`); PR/commit identity comes from `progress.md`.

Every line is a report of what actually happened, including the skips — a gate that was
skipped and a gate that passed are different facts, and collapsing them hides which
protections were actually in force.

```
PR opened for $TICKET.

PR:         #$PR ($BRANCH → $BASE) — $PR_URL
Commit:     <sha> [$TICKET] <subject>
Simplify:   <"clean — no changes needed" | "applied N changes (user confirmed)" | "skipped (--no-simplify)" | "skipped (no uncommitted changes)" | "user aborted">
Tests:      <"passed — N tests" | "skipped (--no-test)" | "skipped (user said skip)" | "failed but user said commit-anyway">
Slop gate:  <"clean ✅" | "🔴 N finding(s) — override: <reason>" | "🟡 N warning(s) — proceeded" | "skipped (--no-adversary)" | "skipped (--no-test)" | "skipped (no uncommitted changes)" | "skipped (on_slop_findings=skip)">
CC gate:    <"clean (max CC=N)" | "N violation(s) blocked and fixed" | "N violation(s) — benchmark-continue override" | "N elevated (CC W–T) — noted in PR body" | "skipped (no changed source files)" | "skipped (lizard not installed)">
Backend:    <"MCP" | "CLI ($GH)">
Review:     <Bot (CodeRabbit/Greptile): "{Bot} — {outcome}" where outcome ∈ {"clean ✅ (1 round)" | "clean ✅ after N rounds" | "N ⚪ findings presented (no 🔴/🟡 to apply)" | "loop limit reached after 5 rounds, N finding(s) remain" | "timed out after 20 min" | "N 🔴/🟡 findings presented, not applied ({backend}_fix=false)"}. Claude: "Claude /code-review --effort $PR_EFFORT [--fix] — clean after N rounds" | "Claude /code-review --effort $PR_EFFORT — N findings posted (fix=false)". Or: "skipped (--no-poll)">
Ticket link: <"posted to $TICKET" | "skipped (--no-poll)" | "failed — <error> (continued)">
```

Note there is **no `Tamper gate:` line**, and that is deliberate: Step 2d has no *skip* to
report — no flag can bypass it. It reaches Step 8 in exactly two states: it passed silently,
or `[autonomous] on_redtest_tamper = "warn"` recorded a 🔴 to the ticket and `pipeline.json`
and continued. Under the default `hard-stop` the run never gets here. When it was `warn`,
say so in the `Slop gate:` line rather than staying silent — a recorded-and-continued tamper
finding is the one outcome a reader would otherwise never learn from this summary.

`Review:` names the backend that actually reviewed — the value Pre-flight resolved.
