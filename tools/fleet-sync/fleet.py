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
