#!/usr/bin/env python3
"""One command to bring a repo to the full slopstop setup, and to verify it stayed there.

    python3 tools/fleet-sync/setup-project.py --repos sophie/sophie,sophie/aatoolkit
    python3 tools/fleet-sync/setup-project.py --repos sophie/sophie --apply

Dry run by default: it prints what it WOULD change and exits non-zero if anything is out of
form.  `--apply` performs the changes, then re-runs every check and reports the after-state,
so a run that claims success has proved it rather than asserted it.

WHY THIS FILE EXISTS (charter C13).  Five parts make up a slopstop setup and no single tool
covered them.  `install-for-project.sh` does skills only; `sync-project-conf.py` does config
only; `migrate-universal-block.py` is dead against the current layout (it looks for the
pre-2026-08-06 root `CLAUDE-universal.md` + marker region and reports the reference itself as
`unblocked`).  Two parts — the `.gitignore` shape and the state directories — were covered by
nothing at all, which is how a repo ends up blanket-ignoring `.claude/` and silently not
committing the skills that pin its slopstop version.

It DELEGATES rather than reimplements: skills to `install-for-project.sh`, config to
`sync-project-conf.py`.  Only the parts nothing else owns are implemented here.
"""

import argparse
import filecmp
import pathlib
import re
import shutil
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from fleet import HOME, REFERENCE, REPOS  # noqa: E402

SLOPSTOP = REFERENCE
UNIVERSAL_REL = pathlib.Path(".claude/rules/universal.md")

OK, BAD, FIXED = "  ok  ", " FAIL ", " fixed"


class Result:
    def __init__(self):
        self.rows = []

    def add(self, repo, part, status, detail=""):
        self.rows.append((repo, part, status, detail))

    def failures(self):
        return [r for r in self.rows if r[2] == BAD]


# ---------------------------------------------------------------- part 1: universal rules
def check_universal(repo: pathlib.Path, apply: bool, res: Result):
    """`.claude/rules/universal.md` byte-identical to the reference, and no stale root copy.

    migrate-universal-block.py is not used: it targets the pre-2026-08-06 layout.
    """
    src = SLOPSTOP / UNIVERSAL_REL
    dst = repo / UNIVERSAL_REL
    name = "universal.md"

    if not dst.exists():
        if apply:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            res.add(repo, name, FIXED, "created from reference")
        else:
            res.add(repo, name, BAD, "missing — would copy from reference")
    elif not filecmp.cmp(src, dst, shallow=False):
        if apply:
            shutil.copy2(src, dst)
            res.add(repo, name, FIXED, "re-synced to reference")
        else:
            res.add(repo, name, BAD, "differs from reference — would overwrite")
    else:
        res.add(repo, name, OK, "byte-identical to reference")

    # the pre-reorg layout, if it is still lying around
    legacy = repo / "CLAUDE-universal.md"
    claude_md = repo / "CLAUDE.md"
    stale_import = False
    if claude_md.exists():
        stale_import = any(l.strip() == "@CLAUDE-universal.md"
                           for l in claude_md.read_text().splitlines())
    if legacy.exists() or stale_import:
        what = []
        if legacy.exists():
            what.append("root CLAUDE-universal.md")
        if stale_import:
            what.append("@CLAUDE-universal.md import")
        res.add(repo, "legacy layout", BAD,
                f"{' + '.join(what)} still present — pre-2026-08-06 layout, migrate by hand")
    else:
        res.add(repo, "legacy layout", OK, "none")


# ---------------------------------------------------------------- part 2: skills
def _reference_dirty():
    return bool(subprocess.run(["git", "-C", str(SLOPSTOP), "status", "--porcelain"],
                               capture_output=True, text=True).stdout.strip())


def check_skills(repo: pathlib.Path, apply: bool, res: Result):
    """`.claude/skills/slopstop-*` regenerated at the reference's current HEAD.

    The REFERENCE is exempt, and the reason is a fixed point rather than laziness: its own
    `.claude/skills` is its own install of itself, and the GENERATED marker records the sha the
    generation ran at — which is always the commit BEFORE the one that commits the regeneration.
    Committing it dirties it again. It can never be simultaneously clean and current, so chasing
    it is an infinite loop, and one attempt at it stamped three consumers `-dirty`.
    """
    head = subprocess.run(["git", "-C", str(SLOPSTOP), "rev-parse", "--short", "HEAD"],
                          capture_output=True, text=True).stdout.strip()
    if repo == SLOPSTOP:
        res.add(repo, "skills", OK, "reference — self-install lags one commit by construction")
        return
    if _reference_dirty():
        res.add(repo, "skills", BAD,
                "REFERENCE TREE IS DIRTY — install refused; the skills would be stamped "
                "`-dirty` and correspond to no commit, so the version freeze would be a lie")
        return
    marker = repo / ".claude/skills/slopstop-run/SKILL.md"
    have = ""
    if marker.exists():
        m = re.search(r"GENERATED from slopstop (\S+)", marker.read_text())
        have = m.group(1) if m else "unparseable"

    if have == head:
        res.add(repo, "skills", OK, f"at {head}")
        return
    # `-dirty` is the installer stamping a generation from an uncommitted tree. That is a
    # different defect from a version lag — the skills correspond to no commit at all — and
    # reporting it as "at X, reference is Y" reads as merely stale.
    if have.rstrip("-dirty") == head and have.endswith("-dirty"):
        res.add(repo, "skills", BAD,
                f"generated from a DIRTY tree at {head} — re-install after committing")
        return
    if not apply:
        res.add(repo, "skills", BAD, f"at {have or 'ABSENT'}, reference is {head}")
        return
    p = subprocess.run(["bash", str(SLOPSTOP / "install-for-project.sh"), str(repo)],
                       capture_output=True, text=True)
    if p.returncode != 0:
        res.add(repo, "skills", BAD, f"installer failed: {p.stderr.strip()[:120]}")
        return
    n = len(list((repo / ".claude/skills").glob("slopstop-*")))
    res.add(repo, "skills", FIXED, f"{have or 'ABSENT'} -> {head} ({n} skills)")


# ---------------------------------------------------------------- part 3: .gitignore shape
#
# git cannot re-include a path whose PARENT DIRECTORY is excluded.  So `.claude/` (the
# directory) makes `!.claude/skills` inert, and the skills silently never get committed —
# which defeats the whole point of installing them (the version freeze).  The contents form
# `.claude/*` is the only one where the negations work.
GITIGNORE_WANT = [".claude/*", "!.claude/rules", "!.claude/skills", "!.claude/agents"]
GITIGNORE_SHOULD_IGNORE = ["/.slopstop/", "/scratch/"]

# `.gitignore` has NO trailing-comment syntax: `#` only starts a comment at the START of a
# line.  `.claude/*   # why` is a literal pattern containing spaces and a hash, and it matches
# nothing — proved with a control repo, where it failed to ignore `.claude/other.json` that the
# bare pattern ignores.  Comments go on their own lines; patterns are written bare.
GITIGNORE_BLOCK = """
# slopstop: exclude .claude CONTENTS, not the directory. git cannot re-include a path whose
# parent directory is excluded, so `.claude/` would make the negations below inert and the
# generated skills would never be committed — defeating the version freeze they exist for.
#
# agents/ is exempted ahead of BILL-486, which may ship per-tier subagent definitions there.
# Cost if that ticket closes wontfix: nothing, the directory simply stays absent. Cost of
# adding it late: definitions land on disk, never get committed, and effort silently inherits
# while the config reads as configured — the same silent shape that left one repo with zero
# tracked skills.
.claude/*
!.claude/rules
!.claude/skills
!.claude/agents
""".strip()


def _ignored(repo, rel):
    """Ask git, not the file. The text is a proxy; `check-ignore` is the authority."""
    return subprocess.run(["git", "-C", str(repo), "check-ignore", "-q", rel]).returncode == 0


def check_gitignore(repo: pathlib.Path, apply: bool, res: Result):
    """Verified BEHAVIOURALLY: the three questions that actually matter, asked of git.

    A textual check missed a broken pattern this script itself wrote; git did not.
    """
    probes = [(".claude/skills/slopstop-run/SKILL.md", False, "skills must be committable"),
              (".claude/rules/universal.md",           False, "rules must be committable"),
              (".claude/agents/slopstop-probe.md",     False, "agents must be committable (BILL-486)"),
              (".claude/__slopstop_probe__.json",      True,  "other .claude state stays ignored")]

    def state():
        return [(rel, _ignored(repo, rel), want, why) for rel, want, why in probes]

    bad = [(rel, got, want, why) for rel, got, want, why in state() if got != want]
    if not bad:
        res.add(repo, ".gitignore", OK, "git agrees: skills+rules tracked, other .claude ignored")
    elif not apply:
        res.add(repo, ".gitignore", BAD,
                "; ".join(f"{rel} is {'ignored' if got else 'NOT ignored'} ({why})"
                          for rel, got, want, why in bad))
    else:
        gi = repo / ".gitignore"
        lines = gi.read_text().splitlines() if gi.exists() else []
        keep = [l for l in lines
                if l.strip() not in (".claude/", "/.claude/", ".claude")
                and not l.strip().startswith((".claude/*", "!.claude/"))]
        gi.write_text("\n".join(keep).rstrip() + "\n\n" + GITIGNORE_BLOCK + "\n")
        still = [rel for rel, got, want, _ in state() if got != want]
        res.add(repo, ".gitignore", FIXED if not still else BAD,
                "rewrote the .claude block" + (f"; STILL WRONG: {still}" if still else ""))

    unignored = [p for p in GITIGNORE_SHOULD_IGNORE if not _ignored(repo, p.strip("/"))]
    res.add(repo, "ignored state dirs", OK if not unignored else BAD,
            "both ignored" if not unignored else f"not ignored: {', '.join(unignored)}")


# ---------------------------------------------------------------- part 4: state directories
def check_dirs(repo: pathlib.Path, apply: bool, res: Result):
    """`.slopstop/` drives tier-2 tracking-dir resolution; `scratch/` holds :design runs."""
    for rel in (".slopstop", "scratch"):
        d = repo / rel
        if d.is_dir():
            res.add(repo, f"{rel}/", OK, "present")
        elif apply:
            d.mkdir(parents=True, exist_ok=True)
            res.add(repo, f"{rel}/", FIXED, "created")
        else:
            res.add(repo, f"{rel}/", BAD, "missing — would create")


# ---------------------------------------------------------------- part 5: .project-conf.toml
def check_conf(repo: pathlib.Path, rel: str, apply: bool, res: Result):
    """Delegated to sync-project-conf.py, which owns retired tables/keys and tier targets."""
    conf = repo / ".project-conf.toml"
    if not conf.exists():
        res.add(repo, ".project-conf.toml", BAD, "missing — run /slopstop:gh-init or create by hand")
        return
    cmd = [sys.executable, str(SLOPSTOP / "tools/fleet-sync/sync-project-conf.py"),
           "--repos", rel] + (["--apply"] if apply else [])
    p = subprocess.run(cmd, capture_output=True, text=True)
    body = p.stdout + p.stderr
    changed = [l.strip() for l in body.splitlines()
               if re.search(r"(retired|removed|would|set |comment)", l, re.I) and rel.split("/")[-1] in body]
    if apply:
        res.add(repo, ".project-conf.toml", FIXED if changed else OK,
                f"sync-project-conf --apply ({len(changed)} lines of action)" if changed else "clean")
    else:
        res.add(repo, ".project-conf.toml", BAD if changed else OK,
                f"{len(changed)} pending change(s) — see sync-project-conf.py" if changed else "clean")


PARTS = [check_universal, check_skills, check_gitignore, check_dirs]


def run(rel: str, apply: bool, res: Result):
    repo = HOME / rel
    if not repo.is_dir():
        res.add(repo, "repo", BAD, "path does not exist")
        return
    for fn in PARTS:
        fn(repo, apply, res)
    check_conf(repo, rel, apply, res)


def report(res: Result, title: str):
    print(f"\n=== {title} ===")
    cur = None
    for repo, part, status, detail in res.rows:
        if repo != cur:
            print(f"\n  {repo}")
            cur = repo
        print(f"    [{status}] {part:22s} {detail}")
    n = len(res.failures())
    print(f"\n  {len(res.rows) - n}/{len(res.rows)} checks pass"
          + (f" — {n} FAILING" if n else ""))
    return n


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repos", help="comma-separated, relative to $HOME (default: whole fleet)")
    ap.add_argument("--apply", action="store_true", help="perform changes, then re-verify")
    args = ap.parse_args()
    repos = args.repos.split(",") if args.repos else REPOS

    before = Result()
    for r in repos:
        run(r, False, before)
    n_before = report(before, "BEFORE" if args.apply else "CHECK (dry run)")

    if not args.apply:
        print("\n  dry run — nothing written. Re-run with --apply to fix.")
        return 1 if n_before else 0

    doing = Result()
    for r in repos:
        run(r, True, doing)
    report(doing, "APPLY")

    after = Result()
    for r in repos:
        run(r, False, after)
    n_after = report(after, "AFTER (re-verified)")
    if n_after:
        print("\n  *** some checks still fail — see above; these need a human ***")
    return 1 if n_after else 0


if __name__ == "__main__":
    sys.exit(main())
