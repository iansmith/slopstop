#!/usr/bin/env python3
"""
Grand synchronization: bring every project's .project-conf.toml to the agreed
fleet target.  (2026-08-01)

    python3 tools/fleet-sync/sync-project-conf.py           # dry run — prints unified diffs
    python3 tools/fleet-sync/sync-project-conf.py --apply   # write (backs up to *.bak)

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

  [autonomous] enabled = true          (table appended when absent)
  [autonomous] branch_type             REMOVED -> :start picks the prefix itself
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

Never removes a key a repo already has, except branch_type (explicitly asked).
"""

import argparse
import difflib
import pathlib
import re
import shutil
import sys
import tomllib

from fleet import HOME, REPOS, TARGET_TIERS as TARGET

STAMP = "  # set 2026-08-01 (grand synchronization)"


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
        trailing = f'  # was {old!r}; set 2026-08-01 (grand synchronization)'
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
    seen_tiers, seen_auto, seen_pr = set(), False, False
    auto_has_enabled = False
    # Tier tables that exist but never declare `version` need one INSERTED --
    # rewriting only the lines that happen to be present leaves the tier
    # unpinned, which is not the target (gaston had this on all four tiers).
    pending_tier = None          # tier name whose section we are inside
    tier_saw_version = False
    tier_model_idx = None        # index in `out` of that tier's model line

    def close_tier():
        nonlocal pending_tier, tier_saw_version, tier_model_idx
        if pending_tier and not tier_saw_version and tier_model_idx is not None:
            _, want_v = TARGET[pending_tier]
            out.insert(tier_model_idx + 1, f'version  = "{want_v}"{STAMP}')
            notes.append(f"[tiers.{pending_tier}] version inserted (was unpinned) -> {want_v!r}")
        pending_tier, tier_saw_version, tier_model_idx = None, False, None

    for line in lines:
        sec = section_of(line)
        if sec is not None:
            close_tier()
            cur = sec
            if cur.startswith("tiers.") and cur.split(".", 1)[1] in TARGET:
                pending_tier = cur.split(".", 1)[1]
            if cur.startswith("tiers."):
                seen_tiers.add(cur.split(".", 1)[1])
            if cur == "autonomous":
                seen_auto = True
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

        # ---- autonomous ----------------------------------------------------
        if cur == "autonomous":
            if re.match(r"\s*branch_type\s*=", line):
                notes.append("[autonomous] branch_type removed (automatic prefix)")
                out.append("# branch_type intentionally unset 2026-08-01 — :start picks"
                           " the prefix per ticket")
                continue
            if re.match(r"\s*enabled\s*=", line):
                auto_has_enabled = True
                if not re.match(r"\s*enabled\s*=\s*true", line):
                    notes.append("[autonomous] enabled -> true")
                    line = "enabled = true" + STAMP

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
            m, v = TARGET[tier]
            notes.append(f"[tiers.{tier}] table appended (was absent -> CONFIG.md default)")
            add += ["", f"[tiers.{tier}]{STAMP}", 'provider = "anthropic"',
                    f'model    = "{m}"', f'version  = "{v}"']
    if not seen_auto:
        notes.append("[autonomous] table appended with enabled = true (was absent -> false)")
        add += ["", f"[autonomous]{STAMP}", "enabled = true"]
    elif not auto_has_enabled:
        notes.append("[autonomous] enabled = true (key was missing)")
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
            shutil.copy2(f, f.with_suffix(".toml.bak"))
            f.write_text(after)
        print()

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
