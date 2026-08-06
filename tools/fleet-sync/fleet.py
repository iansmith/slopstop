"""The fleet: one definition of who is in it and what they should be set to.

Imported by every script in this directory.  Before this module existed, `REPOS`
was declared three times in three different shapes and the tier target twice
under two different names -- which is the duplicate-constant failure universal §5
prohibits, and the same drift-by-copy bug class `migrate-universal-block.py`
exists to eliminate for `CLAUDE.md`, just not yet applied to itself.

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

#: Repos where CLAUDE-universal.md is deliberately MACHINE-LOCAL (gitignored).
#:
#: These are shared with another contributor, and Ian's universal rules are his
#: working process, not a company standard to impose on a shared repository.  The
#: file still exists on disk and still loads via CLAUDE.md's @import here — it is
#: simply never committed.  `.project-conf.toml` is gitignored in exactly these same
#: two repos and for the same reason; they were the only two left after louis14 and
#: gaston were un-ignored on 2026-08-01, so the two sets coincide -- but they are
#: separate decisions and a future divergence is legitimate.
#:
#: Consequence, stated so nobody rediscovers it as a bug: on these repos the
#: tracked CLAUDE.md carries an @import for a file a fresh clone does not have.
#: The import silently resolves to nothing for anyone but Ian, which is intended.
#: migrate-universal-block.py's gitignore guard is suppressed for these repos --
#: everywhere else, a gitignored rules file is a hard error.
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
