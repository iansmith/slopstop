#!/usr/bin/env python3
"""Inventory every git worktree across the fleet, and say which ones hold work.

    python3 tools/fleet-sync/worktree-inventory.py                  # whole fleet
    python3 tools/fleet-sync/worktree-inventory.py --repos mazzy    # one repo, relative to $HOME
    python3 tools/fleet-sync/worktree-inventory.py --json           # machine-readable

Exit 0 always: this REPORTS. It removes nothing, and it is not a gate.

WHY THIS FILE EXISTS (BILL-536).  Worktrees accumulate and nobody owns them.  Measured before
`:run` had created a single one: mazzy carried three (one ten weeks old, one on a detached
HEAD), this repo had leaked one into a session scratchpad, and two lyos repos use a
sibling-directory convention instead.  Claude Code's own periodic sweep will not touch any of
them -- it only removes worktrees IT created, only past `cleanupPeriodDays`, and it skips any
that still hold work.  So the ones that matter are exactly the ones nothing is watching.

THE ONE JUDGEMENT THIS TOOL MAKES, and the one it refuses to make.  It decides `holds_work`,
because that is mechanical.  It does NOT decide what to delete: BILL-536 is explicit that a
worktree on a detached HEAD is the highest-risk case rather than the easiest, and that several
of these repos are shared with another contributor.  The output is a report a human acts on.

HOLDS_WORK IS NOT "HAS UNPUSHED COMMITS VS MASTER".  A feature-branch worktree legitimately
sits ahead of master; that is not lost work, it is a branch.  The question is whether anything
here exists ONLY here:

  * uncommitted or untracked files, or
  * commits not reachable from ANY remote-tracking ref.

Getting this wrong in the safe-looking direction is what makes an inventory dangerous: a first
pass using `master..HEAD` flagged mazzy's `brave-lumiere-028d32` as holding an unpushed commit,
when `6397e2ab` was sitting on `origin/chore/MAZ-180` the whole time.

PATHS RESOLVE FROM THE REPO, NEVER FROM THE CWD.  Every worktree has a different working
directory by definition, so every git call here is explicitly `-C`'d at a known root and no
result is interpreted relative to wherever this was launched from.
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import subprocess
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
try:
    from fleet import REPOS  # type: ignore
except Exception:  # pragma: no cover - fleet.py is the source of truth when present
    REPOS = []


def git(root, *args):
    try:
        r = subprocess.run(
            ["git", "-C", str(root), *args],
            capture_output=True, text=True, timeout=60,
        )
        return r.stdout.strip() if r.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        return ""


def worktrees(root):
    """Parse `git worktree list --porcelain`, skipping the main checkout."""
    out, cur, found = git(root, "worktree", "list", "--porcelain"), {}, []
    for line in out.splitlines() + [""]:
        if not line:
            if cur:
                found.append(cur)
            cur = {}
            continue
        key, _, val = line.partition(" ")
        if key == "worktree":
            cur = {"path": val}
        elif key == "branch":
            cur["branch"] = val.replace("refs/heads/", "")
        elif key == "detached":
            cur["branch"] = None
        elif key == "locked":
            cur["locked"] = val or True
        elif key == "HEAD":
            cur["head"] = val
    return found[1:]  # [0] is the main checkout


def classify(path, branch, root):
    """slopstop-owned / harness-created / manual — by shape, never by guessing intent."""
    p = pathlib.Path(path)
    inside = ".claude/worktrees" in str(p)
    if branch and "/" in branch and branch.split("/")[0] in {
        "feat", "fix", "chore", "docs", "refactor", "test", "perf",
    }:
        return "slopstop" if inside else "slopstop (outside .claude/worktrees)"
    if branch and branch.startswith("claude/"):
        return "harness"
    if inside:
        return "harness-dir, manual name"
    return "manual"


def holds_work(path, root):
    """Only-here work: dirty tree, or commits on no remote-tracking ref."""
    if not os.path.isdir(path):
        return None, ["path is gone — the registration is stale"]
    reasons = []
    dirty = [l for l in git(path, "status", "--porcelain").splitlines() if l.strip()]
    if dirty:
        reasons.append(f"{len(dirty)} uncommitted/untracked file(s)")
    head = git(path, "rev-parse", "HEAD")
    if head:
        remotes = git(root, "branch", "-r", "--contains", head)
        if not remotes.strip():
            reasons.append(f"HEAD {head[:8]} is on no remote ref — exists only here")
    return bool(reasons), reasons


def age_days(path):
    try:
        return int((time.time() - os.path.getmtime(path)) / 86400)
    except OSError:
        return None


def main():
    ap = argparse.ArgumentParser(description="Inventory fleet git worktrees. Reports; removes nothing.")
    ap.add_argument("--repos", help="comma-separated, relative to $HOME (default: the fleet)")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    args = ap.parse_args()

    home = pathlib.Path.home()
    names = args.repos.split(",") if args.repos else list(REPOS)
    if not names:
        print("no repos: pass --repos, or ensure fleet.py defines REPOS", file=sys.stderr)
        return 0

    rows, missing = [], []
    for name in names:
        root = (home / name.strip()).resolve()
        if not (root / ".git").exists():
            missing.append(str(root))
            continue
        for wt in worktrees(root):
            work, reasons = holds_work(wt["path"], root)
            rows.append({
                "repo": name.strip(),
                "path": wt["path"],
                "branch": wt.get("branch"),
                "detached": wt.get("branch") is None,
                "locked": bool(wt.get("locked")),
                "age_days": age_days(wt["path"]),
                "origin_class": classify(wt["path"], wt.get("branch"), root),
                "holds_work": work,
                "why": reasons,
            })

    if args.json:
        print(json.dumps({"worktrees": rows, "unreadable_repos": missing}, indent=2))
        return 0

    if not rows:
        print("no worktrees found in any inspected repo")
    for r in rows:
        flag = "HOLDS WORK" if r["holds_work"] else ("STALE REG" if r["holds_work"] is None else "removable")
        branch = r["branch"] or "(detached HEAD)"
        age = f"{r['age_days']}d" if r["age_days"] is not None else "?"
        print(f"{r['repo']:22} {branch:42} {age:>5}  {r['origin_class']:28} "
              f"{'LOCKED ' if r['locked'] else ''}{flag}")
        print(f"  {r['path']}")
        for why in r["why"]:
            print(f"    - {why}")
    if missing:
        print("\nnot a git repository (skipped, never guessed at):")
        for m in missing:
            print(f"  {m}")

    held = [r for r in rows if r["holds_work"]]
    print(f"\n{len(rows)} worktree(s); {len(held)} hold work and must not be removed.")
    print("This tool removes nothing. Every removal needs a human and a recorded reason (BILL-536).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
