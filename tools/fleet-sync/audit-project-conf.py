#!/usr/bin/env python3
"""
Audit every project's .project-conf.toml against the agreed fleet-wide target.

    python3 tools/fleet-sync/audit-project-conf.py          # table + per-repo remediation
    python3 tools/fleet-sync/audit-project-conf.py --quiet  # table only

Exit 0 only when every repo passes every REQUIRED check.

TARGET (agreed 2026-08-01):
  * tiers        huge=opus 5, large=opus 5, medium=sonnet 5, small=sonnet 5
  * autonomous   enabled = true
  * branch_type  ABSENT -> automatic heuristic choice (the default)

WHY THE VERSION PINS ARE REQUIRED, NOT COSMETIC:
  A pinned `version` must be a dotted prefix of the SESSION model's version.
  So `version = "4.6"` can never be satisfied by an opus-5 session -- the tier
  gate hard-stops, and :design / :tickets / :single-ticket refuse to run.
  A stale pin does not silently downgrade; it takes the stage offline.

This script READS ONLY. Per Ian's standing rule, config changes belong to the
project -- this writes the audit, each project applies it.
"""

import argparse
import pathlib
import sys
import tomllib

from fleet import HOME, REPOS, TARGET_TIERS, TIER_DEFAULTS


def tier_of(conf, name):
    """-> (model, version) as configured, or the documented default."""
    t = conf.get("tiers", {}).get(name)
    if not isinstance(t, dict):
        return TIER_DEFAULTS[name] + ("default",)
    return t.get("model"), t.get("version"), "set"


def fmt_tier(model, version):
    return f"{model}" + (f" {version}" if version else " —")


def audit(path):
    """-> (conf|None, required_failures, review_items, review_pairs).

    Always a 4-tuple.  It briefly returned 3 on error paths and 4 on success,
    which forced main() to branch on len() before it could unpack.
    """
    f = path / ".project-conf.toml"
    if not path.is_dir():
        return None, ["directory does not exist"], [], []
    if not f.is_file():
        return None, ["no .project-conf.toml"], [], []
    try:
        conf = tomllib.loads(f.read_text())
    except Exception as exc:
        return None, [f"INVALID TOML: {exc}"], [], []

    fails, review = [], []

    for name, (want_m, want_v) in TARGET_TIERS.items():
        got_m, got_v, origin = tier_of(conf, name)
        if (got_m, got_v) != (want_m, want_v):
            src = "unset, using default" if origin == "default" else "set"
            fails.append(
                f"[tiers.{name}] is {fmt_tier(got_m, got_v)} ({src}); "
                f"want model=\"{want_m}\" version=\"{want_v}\"")

    auto = conf.get("autonomous", {})
    if not isinstance(auto, dict) or auto.get("enabled") is not True:
        fails.append("[autonomous] enabled is not true "
                     f"({'table absent' if not auto else auto.get('enabled')!r})")
    if "branch_type" in auto:
        fails.append(f"[autonomous] branch_type = {auto['branch_type']!r} is set; "
                     "remove it so the branch prefix is chosen automatically")

    # ---- consistency items: real divergence, but no ruling given yet --------
    pr = conf.get("pr_review", {})
    if pr.get("backend") != "claude":
        review.append(f"[pr_review] backend = {pr.get('backend')!r} (fleet uses \"claude\")")
    review_pairs = [
        ("[pr_review] fix", pr.get("fix")),
        ("[autonomous] merge_target_state", auto.get("merge_target_state")),
        ("[autonomous] merge_strategy", auto.get("merge_strategy")),
        ("[workflow] skip_confirm", conf.get("workflow", {}).get("skip_confirm")),
        ("[fleet.router] enabled", conf.get("fleet", {}).get("router", {}).get("enabled")),
        ("[fleet.monitoring] filemap_violation",
         conf.get("fleet", {}).get("monitoring", {}).get("filemap_violation")),
        ("[autonomous] metrics_emit_path", auto.get("metrics_emit_path")),
        ("tracking_dir", conf.get("tracking_dir")),
    ]
    if pr.get("backend") == "claude" and "greptile_fix" in pr:
        review.append("[pr_review] greptile_fix is set but backend is \"claude\" — dead key")
    td, ad = conf.get("tracking_dir"), conf.get("archive_dir")
    # Both must be set explicitly. Unset falls back to the resolution ladder,
    # which for a headless fleet agent lands on the protected ~/.claude default
    # its Write tool refuses -- and it silently differs from every other repo.
    # catherine was the one repo in this state (fixed 2026-08-01); nothing
    # checked for it, which is why it drifted unnoticed.
    for key, val in (("tracking_dir", td), ("archive_dir", ad)):
        if not val:
            fails.append(f"{key} is unset; want the project-local "
                         f"\".slopstop/{'ticket-active' if key.startswith('tracking') else 'ticket-archive'}\"")
    if td and ad and (ad.startswith(td.rstrip("/") + "/")):
        fails.append(f"archive_dir ({ad!r}) is INSIDE tracking_dir ({td!r}) — "
                     "archived tickets land under the active-ticket tree")
    if conf.get("fleet", {}).get("agents", {}).get("model"):
        review.append(
            f"[fleet.agents] model = "
            f"{conf['fleet']['agents']['model']!r} overrides the tier ladder; "
            "redundant once [tiers.small] is sonnet 5")
    return conf, fails, review, review_pairs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--quiet", action="store_true", help="table only")
    args = ap.parse_args()

    rows, details, pairs_by_repo = [], {}, {}
    for r in REPOS:
        conf, fails, review, pairs = audit(HOME / r)
        rows.append((r, conf, fails))
        details[r] = (fails, review)
        pairs_by_repo[r] = pairs

    # ---- tier table --------------------------------------------------------
    print("=== TIERS — target: huge=opus 5  large=opus 5  medium=sonnet 5  small=sonnet 5 ===\n")
    print(f"{'repo':<20} {'huge':<12} {'large':<12} {'medium':<12} {'small':<12} auto  branch_type")
    print("-" * 92)
    for r, conf, fails in rows:
        if conf is None:
            print(f"{r:<20} {'— unreadable —':<52} {fails[0][:30]}")
            continue
        cells = []
        for t in ("huge", "large", "medium", "small"):
            m, v, origin = tier_of(conf, t)
            s = fmt_tier(m, v) + ("*" if origin == "default" else "")
            ok = (m, v) == TARGET_TIERS[t]
            cells.append(("" if ok else "!") + s)
        auto = conf.get("autonomous", {})
        en = "yes" if auto.get("enabled") is True else "NO!"
        bt = auto.get("branch_type", "auto")
        bt = bt if bt == "auto" else f"!{bt}"
        print(f"{r:<20} {cells[0]:<12} {cells[1]:<12} {cells[2]:<12} {cells[3]:<12} {en:<5} {bt}")
    print("\n  ! = differs from target      * = tier table absent, showing CONFIG.md default")

    # ---- consistency spread ------------------------------------------------
    if not args.quiet:
        print("\n=== CONSISTENCY — same key, different values across the fleet ===\n")
        keys = [k for k, _ in (pairs_by_repo.get("ticket-plugin") or [])]
        for i, key in enumerate(keys):
            spread = {}
            for r in REPOS:
                p = pairs_by_repo.get(r) or []
                if i < len(p):
                    spread.setdefault(repr(p[i][1]), []).append(r.split("/")[-1])
            if len(spread) > 1:
                print(f"  {key}")
                for val, who in sorted(spread.items()):
                    print(f"      {val:<22} {', '.join(who)}")

    # ---- per-repo remediation ---------------------------------------------
    if not args.quiet:
        print("\n=== REQUIRED FIXES, per repo ===")
        for r in REPOS:
            fails, review = details[r]
            if not fails and not review:
                print(f"\n  ~/{r}: clean")
                continue
            print(f"\n  ~/{r}")
            for f in fails:
                print(f"      FAIL   {f}")
            for v in review:
                print(f"      review {v}")

    bad = sum(1 for r in REPOS if details[r][0])
    print(f"\n{'=' * 60}\n{len(REPOS) - bad}/{len(REPOS)} repos pass the required checks.")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
