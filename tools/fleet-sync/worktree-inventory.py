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
except ModuleNotFoundError:
    # Only a MISSING fleet.py is tolerated. A syntax or runtime error inside an existing one
    # must propagate: swallowing it sets REPOS = [] and the run exits 0 with "no repos",
    # which reads as "the fleet is clean" when the source of truth is broken.
    REPOS = []


class GitUnavailable(Exception):
    """A git command did not run, or failed. NEVER silently an empty result.

    The distinction is the whole safety of this tool. `git status --porcelain` returning ""
    means a clean worktree; a timeout, a permissions error, or a corrupt repo returning ""
    means *we do not know*. Collapsing the two makes an unreadable worktree report as
    holding no work, which is the one direction that loses somebody's files.
    """


def git(root, *args, required=True):
    try:
        r = subprocess.run(
            ["git", "-C", str(root), *args],
            capture_output=True, text=True, timeout=60,
        )
    except (OSError, subprocess.SubprocessError) as e:
        raise GitUnavailable(f"git {' '.join(args)}: {type(e).__name__}") from e
    if r.returncode != 0:
        if required:
            raise GitUnavailable(f"git {' '.join(args)}: exit {r.returncode} {r.stderr.strip()[:120]}")
        return ""
    return r.stdout.strip()


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


def dependency_link(path, entry):
    """True when an untracked entry is a symlink pointing outside the worktree.

    That is universal §6's pattern -- "symlink large, rarely-changing directories that
    aren't under git control from the worktree to their original location" -- and it is a
    dependency shim, never work product.

    It shows up as untracked for a reason worth knowing: a `.gitignore` rule written with a
    trailing slash (`fonts/`) matches DIRECTORIES ONLY. In the main checkout `fonts` is a
    directory and is ignored; in a worktree it is a symlink, which git records as a file, so
    the pattern misses it and the link lands in `git status` forever. Counting that as work
    made this tool report four of louis14's seven worktrees as HOLDS WORK when their only
    dirty entry was the fonts link -- a false positive in the safe-looking direction, on the
    exact judgement the tool exists to make.
    """
    name = entry[3:].strip().strip('"')
    full = os.path.join(path, name)
    if not os.path.islink(full):
        return False
    target = os.path.realpath(full)
    return not target.startswith(os.path.realpath(path) + os.sep)


def unregistered(root, registered):
    """Entries under .claude/worktrees/ that are NOT registered git worktrees.

    BILL-536's defect 3 lives here: `mazzy/.claude/worktrees/louis14` is a symlink to another
    repo, and `louis14/.claude/worktrees/mazzy` is a (dangling) symlink used to make a
    relative cross-repo `go.mod` replace resolve from inside a worktree. Neither is a
    worktree, so iterating `git worktree list` never sees them -- and Claude Code refuses to
    create a worktree when `.claude/worktrees/<name>` is a symlink, so they break the thing
    the directory is for. Report them; never guess what they are for.
    """
    d = root / ".claude" / "worktrees"
    if not d.is_dir():
        return []
    known = {os.path.realpath(p) for p in registered}
    out = []
    for entry in sorted(d.iterdir()):
        if os.path.realpath(entry) in known:
            continue
        kind = "symlink -> " + os.readlink(entry) if entry.is_symlink() else "directory"
        dangling = entry.is_symlink() and not entry.exists()
        out.append({"path": str(entry), "kind": kind, "dangling": dangling})
    return out


def holds_work(path, root):
    """Only-here work: dirty tree, or commits on no remote-tracking ref."""
    if not os.path.isdir(path):
        return None, ["path is gone — the registration is stale"]
    reasons, notes = [], []          # reasons decide holds_work; notes are context only
    try:
        entries = [l for l in git(path, "status", "--porcelain").splitlines() if l.strip()]
    except GitUnavailable as e:
        return None, [f"UNREADABLE — {e}. No removal judgement is possible."]
    links = [e for e in entries if e.startswith("??") and dependency_link(path, e)]
    dirty = [e for e in entries if e not in links]
    if dirty:
        reasons.append(f"{len(dirty)} uncommitted/untracked file(s)")
    if links:
        names = ", ".join(sorted(e[3:].strip() for e in links))
        notes.append(f"not counted as work: {len(links)} symlink(s) out of the worktree "
                     f"— {names}. Shape matches universal §6's dependency shim; this tool "
                     f"cannot tell a deliberate shim from a stray link, so verify.")
    try:
        head = git(path, "rev-parse", "HEAD")
    except GitUnavailable as e:
        return None, [f"UNREADABLE — {e}. No removal judgement is possible."]
    if head:
        # A commit on no branch at all makes --contains exit non-zero; that is not a failure.
        remotes = git(root, "branch", "-r", "--contains", head, required=False)
        if not remotes.strip():
            reasons.append(f"HEAD {head[:8]} is on no remote ref — exists only here")
    # `notes` never influences the verdict -- that separation is structural now. It used to
    # be a prefix match on the message text, which silently broke the first time the wording
    # changed and put four worktrees back into HOLDS WORK.
    return bool(reasons), reasons + notes


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

    rows, missing, strays = [], [], []
    for name in names:
        root = (home / name.strip()).resolve()
        if not (root / ".git").exists():
            missing.append(str(root))
            continue
        try:
            wts = worktrees(root)
        except GitUnavailable as e:
            missing.append(f"{root} — UNREADABLE: {e}")
            continue
        for s in unregistered(root, [w["path"] for w in wts]):
            strays.append({"repo": name.strip(), **s})
        for wt in wts:
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
        print(json.dumps({"worktrees": rows, "unreadable_repos": missing,
                          "unregistered_entries": strays}, indent=2))
        return 0

    if not rows:
        print("no worktrees found in any inspected repo")
    for r in rows:
        # NEVER "removable". holds_work == False means only that no local-only work was
        # found; it says nothing about whether the worktree is in use, wanted, or approved
        # for deletion -- and this tool refuses to make that call (see the header).
        flag = ("HOLDS WORK" if r["holds_work"]
                else "UNKNOWN — see reason" if r["holds_work"] is None
                else "no local-only work detected")
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

    if strays:
        print("\nIn .claude/worktrees/ but NOT a registered worktree "
              "(Claude Code refuses to create a worktree at a symlinked name):")
        for s in strays:
            print(f"  {s['repo']:14} {s['path']}")
            print(f"      {s['kind']}{'   *** DANGLING ***' if s['dangling'] else ''}")

    held = [r for r in rows if r["holds_work"]]
    print(f"\n{len(rows)} worktree(s); {len(held)} hold work and must not be removed.")
    print("This tool removes nothing. Every removal needs a human and a recorded reason (BILL-536).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
