#!/usr/bin/env python3
"""
Grand synchronization: bring every project's .project-conf.toml to the agreed
fleet target.  (2026-08-01)

    python3 tools/fleet-sync/sync-project-conf.py           # dry run — prints unified diffs
    python3 tools/fleet-sync/sync-project-conf.py --apply   # write in place (no backup — see below)

WHAT IT CHANGES — deliberately a SHORT list.  Everything else in each file is
left exactly as it is, comments included.

  [tiers.huge]   model="opus"    version="5"
  [tiers.large]  model="opus"    version="5"
  [tiers.medium] model="sonnet"  version="5"
  [tiers.small]  model="sonnet"  version="5"
      A missing tier table is appended.  Stale pins are the reason this exists:
      a pinned version must be a dotted PREFIX of the session model's version,
      so version="4.6" can never be satisfied by an opus-5 session and the tier
      gate HARD-STOPS.  :design / :tickets / :single-ticket go offline.

  [autonomous]                         REMOVED ENTIRELY (v4.0.0).  The whole table
      went: `enabled` and the seven on_* gate knobs were replaced by one
      --interactive flag on :run (autonomous is now the DEFAULT, so a master
      switch would be backwards); the CC thresholds moved to [complexity];
      merge_strategy and merge_target_state were read only by :merge, which no
      longer exists; archive_immediately was read by nothing.  The keys are
      commented out rather than deleted, so a maintainer sees what was dropped.

  [fleet.agents] [fleet.monitoring] [fleet.budget] [fleet.router]
                                       REMOVED ENTIRELY (v4.0.0).  They configured
      the fleet launcher -- headless `claude -p` processes, a polling monitor,
      attempt caps, the metering router.  :run launches worker agents now, so
      there is no launch model, poll interval, tool grant or router URL.

  [stage_tiers] run                    REMOVED.  :run has no tier gate, and the
      gate is an EXACT family match, so run = "medium" would hard-stop :run on an
      opus session -- forbidding the higher tier, not the lower.

  [pr_review]  backend = "claude"      (universal §9 requires it explicitly)

  Plus two outright bugs:
    - mobile-v2:  fix = yes   -> fix = true   (`yes` is not valid TOML; the
                                               whole file fails to parse)
    - aatoolkit:  tracking_dir ".slopstop" -> ".slopstop/ticket-active"
                  (archive_dir sits INSIDE tracking_dir otherwise)

WHAT IT DELIBERATELY DOES NOT CHANGE
  system / key / prefix / pr-repo / remotes / base-branch / status_labels
      -- per-project identity, explicitly out of scope.
  [pr_review] fix, merge_target_state, merge_strategy, skip_confirm,
  [fleet.*], [stage_tiers], effort
      -- these diverge across the fleet, but no target was given for them and
         several are real per-project behavior choices (`fix = true` auto-commits
         review findings).  The audit script reports the spread; changing them is
         a separate, explicit decision.

NOTE (BILL-462): this reads `.project-conf.toml` ONLY. A sibling
`.project-conf-local.toml` may exist and override values for one developer on one
machine; it is gitignored and must never be audited or synced. Auditing it would report
a personal choice as fleet drift; syncing it would push one developer's fork URL to
everyone. Do not add it here.

Never removes a key a repo already has, except branch_type (explicitly asked).
"""

import argparse
import difflib
import pathlib
import datetime as _dt
import re
import sys
import tomllib

# Tables v4.0.0 retired outright. Every key inside them is commented out.
RETIRED_TABLES = {"autonomous", "fleet.agents", "fleet.monitoring",
                  "fleet.budget", "fleet.router"}

from fleet import (HOME, REPOS, RETIRED_KEYS, RETIRED_TABLES, TARGET_EFFORT,
                   TARGET_TIERS as TARGET)

# The stamp records WHEN a value was set, so it is computed at run time. It was hardcoded to
# "2026-08-01 (grand synchronization)" until 2026-08-07, which meant every line this tool wrote
# on any later day carried a date it was not set on -- false provenance in a file whose comments
# exist to be trusted. A no-op run writes nothing (rewrites fire only on a difference, inserts
# only on absence), so a live date cannot churn an already-synced file.
STAMP = f"  # set {_dt.date.today().isoformat()} (fleet sync)"


# A complete tier table, defined once.  There are two writers -- close_tier() fills in keys
# missing from a table already in the file, and the append path below writes whole tables that
# were absent -- and they disagreed: the append emitted provider/model/version and no `effort`,
# so a freshly appended table was immediately incomplete.  The next run then inserted the
# missing effort, which is why a new project needed TWO --apply passes to converge and why the
# tool's own re-verify reported FAILING right after it had finished writing (BILL-491).
def tier_version_line(tier):
    return f'version  = "{TARGET[tier][1]}"{STAMP}'


def tier_effort_line():
    return f'effort   = "{TARGET_EFFORT}"{STAMP}'


def tier_table(tier):
    """Every line of a `[tiers.<name>]` table, in the canonical order."""
    return [f"[tiers.{tier}]{STAMP}", 'provider = "anthropic"',
            f'model    = "{TARGET[tier][0]}"', tier_version_line(tier), tier_effort_line()]


def section_of(line):
    m = re.match(r"\s*\[([^\]]+)\]\s*(?:#.*)?$", line)
    return m.group(1) if m else None


def restamp(prefix, value, trailing, tier, key, old):
    """Rewrite a key line, replacing any trailing comment that now contradicts it.

    A comment like `# pinned back to 4.6, 2026-07-28` sitting next to
    `version = "5"` is worse than no comment: the next reader cannot tell which
    one is stale.  Keep the old value in the replacement so nothing is lost.
    """
    if "#" in trailing:
        trailing = f'  # was {old!r}; set {_dt.date.today().isoformat()} (fleet sync)'
    return f'{prefix}"{value}"{trailing}'


def nested_tracking_fix(text):
    """-> (old, new) when archive_dir sits INSIDE tracking_dir, else None.

    General rule, not a repo special case: audit-project-conf.py already detects
    this shape (`ad.startswith(td + "/")`) for the whole fleet, so the repair uses
    the same predicate.  Found first on aatoolkit (tracking_dir ".slopstop",
    archive_dir ".slopstop/ticket-archive" — archived tickets landing under the
    active tree); keying the fix to that repo's name would have let the next repo
    ship the same bug silently.
    """
    def top_level(key):
        m = re.search(rf'^\s*{key}\s*=\s*"([^"]*)"', text, re.M)
        return m.group(1) if m else None

    td, ad = top_level("tracking_dir"), top_level("archive_dir")
    if td and ad and ad.startswith(td.rstrip("/") + "/"):
        return td, td.rstrip("/") + "/ticket-active"
    return None


def sync(text, repo_name):
    lines = text.split("\n")
    out, cur, notes = [], None, []
    nest = nested_tracking_fix(text)
    seen_tiers, seen_pr = set(), False
    # Tier tables that exist but never declare `version` need one INSERTED --
    # rewriting only the lines that happen to be present leaves the tier
    # unpinned, which is not the target (gaston had this on all four tiers).
    pending_tier = None          # tier name whose section we are inside
    tier_saw_version = False
    tier_saw_effort = False
    tier_model_idx = None        # index in `out` of that tier's model line

    def close_tier():
        nonlocal pending_tier, tier_saw_version, tier_saw_effort, tier_model_idx
        if pending_tier and tier_model_idx is not None:
            # Insert after the model line, version first so the order stays model/version/effort.
            if not tier_saw_effort:
                out.insert(tier_model_idx + 1, tier_effort_line())
                notes.append(f"[tiers.{pending_tier}] effort inserted (was absent) "
                             f"-> {TARGET_EFFORT!r}")
            if not tier_saw_version:
                out.insert(tier_model_idx + 1, tier_version_line(pending_tier))
                notes.append(f"[tiers.{pending_tier}] version inserted (was unpinned) "
                             f"-> {TARGET[pending_tier][1]!r}")
        pending_tier, tier_saw_version, tier_saw_effort, tier_model_idx = None, False, False, None

    for line in lines:
        sec = section_of(line)
        if sec is not None:
            close_tier()
            cur = sec
            if cur.startswith("tiers.") and cur.split(".", 1)[1] in TARGET:
                pending_tier = cur.split(".", 1)[1]
            if cur.startswith("tiers."):
                seen_tiers.add(cur.split(".", 1)[1])
            if cur == "pr_review":
                seen_pr = True

        # ---- tier model/version -------------------------------------------
        if cur and cur.startswith("tiers."):
            tier = cur.split(".", 1)[1]
            if tier in TARGET:
                want_m, want_v = TARGET[tier]
                m = re.match(r"(\s*model\s*=\s*)\"([^\"]*)\"(.*)$", line)
                if m:
                    if m.group(2) != want_m:
                        notes.append(f"[tiers.{tier}] model {m.group(2)!r} -> {want_m!r}")
                        line = restamp(m.group(1), want_m, m.group(3), tier, "model", m.group(2))
                    tier_model_idx = len(out)
                    out.append(line)
                    continue
                v = re.match(r"(\s*version\s*=\s*)\"([^\"]*)\"(.*)$", line)
                if v:
                    tier_saw_version = True
                    if v.group(2) != want_v:
                        notes.append(f"[tiers.{tier}] version {v.group(2)!r} -> {want_v!r}")
                        line = restamp(v.group(1), want_v, v.group(3), tier, "version", v.group(2))
                    out.append(line)
                    continue
                e = re.match(r"(\s*effort\s*=\s*)\"([^\"]*)\"(.*)$", line)
                if e:
                    tier_saw_effort = True
                    if e.group(2) != TARGET_EFFORT:
                        notes.append(f"[tiers.{tier}] effort {e.group(2)!r} -> {TARGET_EFFORT!r}")
                        line = restamp(e.group(1), TARGET_EFFORT, e.group(3),
                                       tier, "effort", e.group(2))
                    out.append(line)
                    continue

        # ---- retired tables (v4.0.0) ---------------------------------------
        # Comment the keys out rather than delete them: a maintainer reading the
        # diff should see WHAT was dropped, and an uncommented stray key would be
        # silently ignored by a tool that no longer reads the table at all.
        _retired_key = any(
            cur == tbl and re.match(rf"\s*{k}\s*=", line)
            for tbl, keys in RETIRED_KEYS.items() for k in keys)
        if cur in RETIRED_TABLES or _retired_key:
            # Comment the HEADER too. Leaving it uncommented parses as an empty
            # table, which reads as "configured, deliberately blank" rather than
            # "retired" -- and audit-project-conf.py flags its mere presence.
            if section_of(line) in RETIRED_TABLES:
                notes.append(f"[{cur}] table retired in v4.0.0")
                out.append(f"# {line.rstrip()}   # retired v4.0.0")
                continue
            if re.match(r"\s*[A-Za-z_][A-Za-z0-9_]*\s*=", line):
                key = line.split("=", 1)[0].strip()
                notes.append(f"[{cur}] {key} commented out — retired in v4.0.0")
                out.append(f"# {line.rstrip()}   # retired v4.0.0")
                continue

        # ---- pr_review -----------------------------------------------------
        if cur == "pr_review":
            b = re.match(r"(\s*backend\s*=\s*)\"([^\"]*)\"(.*)$", line)
            if b and b.group(2) != "claude":
                notes.append(f"[pr_review] backend {b.group(2)!r} -> 'claude'")
                line = f'{b.group(1)}"claude"{b.group(3)}'
        # ---- bare yes/no is not valid TOML, anywhere -----------------------
        # Deliberately NOT scoped to [pr_review].fix, which is where it was first
        # found (mobile-v2).  TOML has no bare yes/no token at all, so any key in
        # any section carrying one makes the whole file unparseable — and an
        # unparseable config is invisible to every check downstream of it.
        y = re.match(r"(\s*[A-Za-z_][\w-]*\s*=\s*)(yes|no)\s*(#.*)?$", line)
        if y:
            good = "true" if y.group(2) == "yes" else "false"
            key = y.group(1).split("=")[0].strip()
            sect = f"[{cur}] " if cur else ""
            notes.append(f"{sect}{key} = {y.group(2)} -> {good}  (INVALID TOML fixed)")
            line = f"{y.group(1)}{good}{('  ' + y.group(3)) if y.group(3) else ''}"

        # ---- archive_dir nested inside tracking_dir ------------------------
        if nest and cur is None:
            t = re.match(rf'(\s*tracking_dir\s*=\s*)"{re.escape(nest[0])}"(.*)$', line)
            if t:
                notes.append(f"tracking_dir {nest[0]!r} -> {nest[1]!r} "
                             "(archive_dir was nested inside it)")
                line = f'{t.group(1)}"{nest[1]}"{t.group(2)}'

        out.append(line)

    close_tier()   # flush a tier table that ran to end-of-file

    # ---- append anything missing ------------------------------------------
    add = []
    for tier in ("huge", "large", "medium", "small"):
        if tier not in seen_tiers:
            notes.append(f"[tiers.{tier}] table appended (was absent -> CONFIG.md default)")
            add += [""] + tier_table(tier)
    # [autonomous] is retired in v4.0.0 — never appended, and its keys are
    # commented out above wherever a repo still carries them.
    if not seen_pr:
        notes.append('[pr_review] table appended with backend = "claude"')
        add += ["", f"[pr_review]{STAMP}", 'backend = "claude"', 'effort  = "high"']

    if add:
        while out and out[-1].strip() == "":
            out.pop()
        out += add + [""]

    return "\n".join(out), notes


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--repos")
    args = ap.parse_args()
    repos = args.repos.split(",") if args.repos else REPOS

    print(f"=== .project-conf.toml sync — {'APPLY' if args.apply else 'DRY RUN'} ===\n")
    failed = 0

    for r in repos:
        f = HOME / r / ".project-conf.toml"
        if not f.is_file():
            print(f"  [SKIP]  ~/{r} — no .project-conf.toml\n")
            failed += 1
            continue

        before = f.read_text()
        after, notes = sync(before, r)

        if not notes:
            print(f"  [OK]    ~/{r} — already at target\n")
            continue

        # Must parse AFTER, always.  A repo whose file was already broken
        # (mobile-v2) is the whole reason this check is unconditional.
        try:
            tomllib.loads(after)
        except Exception as exc:
            print(f"  [FAIL]  ~/{r} — result would be INVALID TOML: {exc}\n")
            failed += 1
            continue

        print(f"  [{'WROTE' if args.apply else 'WOULD':<5}] ~/{r}")
        for n in notes:
            print(f"            - {n}")
        if not args.apply:
            diff = difflib.unified_diff(before.split("\n"), after.split("\n"),
                                        "before", "after", lineterm="", n=1)
            for d in list(diff)[2:]:
                if d.startswith(("+", "-")) and d.strip() not in ("+", "-"):
                    print(f"            {d}")
        else:
            # No `.bak`. It used to write one here, and the backup was worse than nothing:
            # created on every --apply that changed anything, never cleaned up, and not in
            # any repo's .gitignore -- so it sat in `git status` forever, one careless
            # `git add -A` from being committed. Found in six of seven fleet repos at once.
            #
            # It also was not needed. `.project-conf.toml` is tracked in every repo but the
            # two that deliberately gitignore it, so `git checkout` already restores the
            # previous version; and for those two, a backup silently overwritten by the next
            # run is not a recovery story anyway. Run without --apply first -- the dry run
            # prints the full diff -- and rely on git for the rest.
            f.write_text(after)
        print()

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
