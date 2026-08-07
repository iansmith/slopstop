"""The fleet: one definition of who is in it and what they should be set to.

Imported by every script in this directory.  Before this module existed, `REPOS`
was declared three times in three different shapes and the tier target twice
under two different names -- which is the duplicate-constant failure universal §5
prohibits, and the same drift-by-copy bug class the fleet-sync tools exist to
eliminate for `CLAUDE.md`, just not yet applied to themselves.

Adding a repo is a one-line edit HERE and nowhere else.
"""

import pathlib

HOME = pathlib.Path.home()

# Paths relative to $HOME.  Order is cosmetic (it drives report ordering only),
# except that the reference repo is conventionally first.
REPOS = [
    "ticket-plugin",        # slopstop itself — the reference copy
    "lyos/mobile-v2",
    "lyos/server-v2",
    "louis14",
    "mazzy",
    "sophie/sophie",
    "sophie/aatoolkit",
    "catherine",
    "gaston",
]

#: Absolute paths, for callers that want them directly.
REPO_PATHS = [HOME / p for p in REPOS]

#: The reference copy of the universal rules.  Every other repo mirrors it.
REFERENCE = HOME / "ticket-plugin"

#: Repos where the universal rules file is deliberately MACHINE-LOCAL (gitignored).
#:
#: These are shared with another contributor, and Ian's universal rules are his
#: working process, not a company standard to impose on a shared repository.  The
#: file still exists on disk and still loads — it is simply never committed.
#: `.project-conf.toml` is gitignored in exactly these same two repos and for the
#: same reason; they were the only two left after louis14 and gaston were un-ignored
#: on 2026-08-01, so the two sets coincide -- but they are separate decisions and a
#: future divergence is legitimate.  (`.project-conf.toml` is expected to leave this
#: arrangement: the plan is to track it and move personal overrides into a gitignored
#: `.project-conf-local.toml`.  That change does NOT remove a repo from this set,
#: which governs the rules file only.)
#:
#: The two are NOT on the same layout, and this set does not imply they are.  As of
#: 2026-08-07 server-v2 has migrated to `.claude/rules/universal.md`, while mobile-v2
#: is still on the pre-2026-08-06 root `CLAUDE-universal.md` + `@import` and is being
#: held off for the other contributor.  Consequence on mobile-v2, stated so nobody
#: rediscovers it as a bug: its tracked CLAUDE.md carries an @import for a file a
#: fresh clone does not have, and the import silently resolves to nothing for anyone
#: but Ian.  That is intended.
#:
#: Suppression of the "a gitignored rules file is a hard error" check belongs to
#: whichever tool performs it; everywhere outside this set, that condition is a fault.
LOCAL_RULES_REPOS = {
    "lyos/mobile-v2",
    "lyos/server-v2",
}

#: Config retired in v4.0.0.  ONE definition, imported by both audit- and
#: sync-project-conf.py.  They lived apart until 2026-08-06, and drifted exactly the
#: way universal §5 predicts: audit failed on `[pr_review] fix` and told the maintainer
#: to delete the line, while sync -- whose entire job is deleting such lines -- did not
#: know the key existed.  An audit that reports what the sync cannot fix is worse than
#: no audit: it sends you to hand-edit a file a tool is supposed to own.
#:
#: RETIRED_TABLES: gone wholesale.  Every key inside is commented out, header included.
RETIRED_TABLES = {
    "autonomous",        # `enabled` + seven on_* knobs -> one --interactive flag on :run;
                         # CC thresholds -> [complexity]; merge_* read only by :merge
    "fleet.agents",      # headless `claude -p` launch config
    "fleet.monitoring",  # poll loop and kill triggers
    "fleet.budget",      # attempt and escalation caps
    "fleet.router",      # the metering router
}

#: RETIRED_KEYS: individual keys inside tables that SURVIVE.
RETIRED_KEYS = {
    "pr_review":  ("fix", "coderabbit_fix", "greptile_fix"),
    "stage_tiers": ("run",),   # :run has no tier gate; the gate is an exact family
                               # match, so run="medium" would hard-stop :run on opus
}

#: tier -> (model family, pinned version).  Agreed 2026-08-01.
#:
#: The version pins are load-bearing, not cosmetic: a pinned version must be a
#: dotted PREFIX of the session model's version, so a stale pin like "4.6" can
#: never be satisfied by an opus-5 session and the tier gate HARD-STOPS --
#: :design / :tickets / :single-ticket refuse to run.  Five repos were in that
#: state on 2026-08-01.
TARGET_TIERS = {
    "huge":   ("opus", "5"),
    "large":  ("opus", "5"),
    "medium": ("sonnet", "5"),
    "small":  ("sonnet", "5"),
}

#: The reasoning effort every tier defaults to.  Agreed 2026-08-07 (Ian): all four tiers at
#: "high".  Deliberately ONE value rather than per-tier -- the tier already selects the model,
#: and a second per-tier dial with no stated reason to differ is a knob nobody can calibrate.
#:
#: This is the tier's CEILING, not a fixed level.  A stage may request LOWER where the risk
#: surface is narrower -- see :run's 10b rule for invariant tickets, which drops to "medium"
#: because a refactor and a backfill each have one of the two tier-above checks skipped
#: entirely and the survivor is looking at a mechanically fenced diff.
TARGET_EFFORT = "high"

#: CONFIG.md's documented defaults, applied when a tier table is absent entirely.
TIER_DEFAULTS = {
    "huge":   ("fable", None),
    "large":  ("opus", None),
    "medium": ("sonnet", None),
    "small":  ("haiku", None),
}


# A name here that is not in REPOS would silently do nothing -- the membership test
# would simply never match. Fail loudly at import instead.
assert LOCAL_RULES_REPOS <= set(REPOS), (
    f"LOCAL_RULES_REPOS names repos absent from REPOS: "
    f"{LOCAL_RULES_REPOS - set(REPOS)}"
)
