#!/usr/bin/env python3
"""
Audit every project's .project-conf.toml against the agreed fleet-wide target.

    python3 tools/fleet-sync/audit-project-conf.py          # table + per-repo remediation
    python3 tools/fleet-sync/audit-project-conf.py --quiet  # table only

Exit 0 only when every repo passes every REQUIRED check.

TARGET (tiers agreed 2026-08-01; the rest updated for the 2026-08-06 reorg):
  * tiers        huge=opus 5, large=opus 5, medium=sonnet 5, small=sonnet 5
  * [autonomous] ABSENT ENTIRELY -> the table was retired; gate thresholds moved
                 to [complexity], and :run is autonomous by default with an
                 --interactive flag instead of a config switch.

WHY THE VERSION PINS ARE REQUIRED, NOT COSMETIC:
  A pinned `version` must be a dotted prefix of the SESSION model's version.
  So `version = "4.6"` can never be satisfied by an opus-5 session -- the tier
  gate hard-stops, and :design / :tickets / :single-ticket refuse to run.
  A stale pin does not silently downgrade; it takes the stage offline.

NOTE (BILL-462): this reads `.project-conf.toml` ONLY. A sibling
`.project-conf-local.toml` may exist and override values for one developer on one
machine; it is gitignored and must never be audited or synced. Auditing it would report
a personal choice as fleet drift; syncing it would push one developer's fork URL to
everyone. Do not add it here.

This script READS ONLY. Per Ian's standing rule, config changes belong to the
project -- this writes the audit, each project applies it.
"""

import argparse
import pathlib
import sys
import tomllib

from fleet import HOME, REPOS, RETIRED_KEYS, RETIRED_TABLES, TARGET_TIERS, TIER_DEFAULTS


def tier_of(conf, name):
    """-> (model, version) as configured, or the documented default."""
    t = conf.get("tiers", {}).get(name)
    if not isinstance(t, dict):
        return TIER_DEFAULTS[name] + ("default",)
    return t.get("model"), t.get("version"), "set"


def fmt_tier(model, version):
    return f"{model}" + (f" {version}" if version else " —")


# Dead keys. Nothing reads them; a repo carrying one is carrying a config that
# describes behavior that does not exist. (The original reason was that
# `tools/metrics/conventions.load()` raised on them -- that collector was deleted in
# the 2026-08-06 reorg, so the keys are simply unread now rather than fatal.)
# slopstop must never edit another project's .project-conf.toml (universal §5), which
# makes this audit the entire delivery mechanism: it reports, the maintainer deletes.


def removed_key_failures(conf):
    """Hard failures, not review items -- nothing reads these."""
    out = []
    for table in sorted(RETIRED_TABLES):
        node = conf
        for part in table.split("."):
            node = node.get(part, {}) if isinstance(node, dict) else {}
        if node:
            out.append(f"[{table}] was RETIRED in v4.0.0 — delete the table; nothing reads it")
    for table, keys in RETIRED_KEYS.items():
        for key in keys:
            if key in conf.get(table, {}):
                out.append(f"[{table}] {key} was REMOVED — delete the line; no step reads it")
    return out


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

    # ---- consistency items: real divergence, but no ruling given yet --------
    pr = conf.get("pr_review", {})
    if pr.get("backend") != "claude":
        review.append(f"[pr_review] backend = {pr.get('backend')!r} (fleet uses \"claude\")")
    review_pairs = [
        ("[workflow] skip_confirm", conf.get("workflow", {}).get("skip_confirm")),
        ("[workflow] post_merge_done", conf.get("workflow", {}).get("post_merge_done")),
        ("[complexity] cc_reject_threshold",
         conf.get("complexity", {}).get("cc_reject_threshold")),
        ("tracking_dir", conf.get("tracking_dir")),
    ]
    fails.extend(removed_key_failures(conf))
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
    ap.add_argument(
        "--conf",
        help="audit ONE .project-conf.toml instead of the fleet, and exit non-zero "
             "if it has hard failures. For checking a single repo, or a candidate "
             "config, without walking every entry in fleet.py.",
    )
    args = ap.parse_args()

    if args.conf:
        given = pathlib.Path(args.conf)
        # --conf points AT a .project-conf.toml; audit() works from its directory.
        # Say so when the name is wrong, instead of reporting "no .project-conf.toml"
        # at a path the caller just handed us -- which reads as "your file is missing"
        # when the real answer is "that is not the file I look for".
        if given.name != ".project-conf.toml":
            print(f"FAIL   --conf must point at a file named .project-conf.toml; "
                  f"got {given.name!r}. (Its directory is what gets audited.)")
            return 1
        conf, fails, review, _ = audit(given.parent)
        for f in fails:
            print(f"FAIL   {f}")
        for r in review:
            print(f"review {r}")
        if not fails and not review:
            print("clean")
        return 1 if fails else 0

    rows, details, pairs_by_repo = [], {}, {}
    for r in REPOS:
        conf, fails, review, pairs = audit(HOME / r)
        rows.append((r, conf, fails))
        details[r] = (fails, review)
        pairs_by_repo[r] = pairs

    # ---- tier table --------------------------------------------------------
    print("=== TIERS — target: huge=opus 5  large=opus 5  medium=sonnet 5  small=sonnet 5 ===\n")
    print(f"{'repo':<20} {'huge':<12} {'large':<12} {'medium':<12} {'small':<12} [autonomous]")
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
        # The table is retired; its presence at all is the finding now.
        auto = conf.get("autonomous", {})
        en = "RETIRED!" if auto else "absent"
        bt = ""
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
