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

#: LOCAL_RULES_REPOS was DELETED on 2026-08-09.  Kept as a scar, because the reasoning
#: was sound and the exemption is the kind of thing that gets reinvented.
#:
#: It named the repos -- `lyos/mobile-v2` and `lyos/server-v2` -- where the universal
#: rules file was deliberately machine-local: both are shared with another contributor,
#: and Ian's universal rules are his working process, not a company standard to impose
#: on a shared repository.  So the file lived on disk, loaded, and was never committed.
#:
#: `.project-conf-local.toml` obviates it.  A per-developer override file that is itself
#: gitignored gives a colleague somewhere to deviate WITHOUT the shared file having to be
#: absent, so the shared file can simply be tracked.  mobile-v2 was migrated that way on
#: 2026-08-09 and server-v2's rules file was already tracked before that, which is the
#: second reason this set had to go: it had become false about both its members.
#:
#: THE SET NEVER DID ANYTHING.  `grep -rn LOCAL_RULES_REPOS tools/` found exactly two
#: hits -- this definition, and an assert that it is a subset of REPOS.  No tool ever
#: imported it.  Its own docstring said suppression "belongs to whichever tool performs
#: it", and no tool ever performed it: `setup-project.py` reported mobile-v2's ignored
#: rules file as a hard fault throughout, exactly as if the exemption did not exist.
#: A documented exemption that nothing honours is worse than none, because it is read as
#: protection and is not.
#:
#: If a repo ever genuinely needs machine-local rules again: implement the suppression in
#: the checking tool FIRST, then add the data.  Data without an enforcer is a comment.

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


# (The LOCAL_RULES_REPOS subset assertion lived here until 2026-08-09. It was the only
# code that ever touched that set -- see the note above it. Removed with the set.)
