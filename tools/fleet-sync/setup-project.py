#!/usr/bin/env python3
"""One command to bring a repo to the full slopstop setup, and to verify it stayed there.

    python3 tools/fleet-sync/setup-project.py --repos sophie/sophie,sophie/aatoolkit
    python3 tools/fleet-sync/setup-project.py --repos sophie/sophie --apply

Dry run by default: it prints what it WOULD change and exits non-zero if anything is out of
form.  `--apply` performs the changes, then re-runs every check and reports the after-state,
so a run that claims success has proved it rather than asserted it.

WHY THIS FILE EXISTS (charter C13).  Five parts make up a slopstop setup and no single tool
covered them.  `install-for-project.sh` does skills only; `sync-project-conf.py` does config
only; the rules copy had no owner at all once `migrate-universal-block.py` was deleted on
2026-08-07 for still writing the pre-2026-08-06 layout, so this file owns it now.  Two more
parts — the `.gitignore` shape and the state directories — were covered by
nothing at all, which is how a repo ends up blanket-ignoring `.claude/` and silently not
committing the skills that pin its slopstop version.

It DELEGATES rather than reimplements: skills to `install-for-project.sh`, config to
`sync-project-conf.py`.  Only the parts nothing else owns are implemented here.
"""

import argparse
import json
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

    This is the only propagation path. migrate-universal-block.py, which used to own it,
    was deleted on 2026-08-07: it still wrote the pre-2026-08-06 root `CLAUDE-universal.md`
    plus an `@import`, so running it against a migrated repo reverted the migration and
    reported success.
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
_REF_DIRTY = None


def _reference_dirty(recheck=False):
    """Was the reference dirty WHEN THIS RUN STARTED — cached, deliberately.

    Re-checking per repo makes the run order-dependent in the worst way. The reference is a
    slopstop project too, so `--apply` over a list that includes it syncs its own
    `.project-conf.toml`; that dirties the tree, and every repo processed AFTER it then had its
    skills install refused with "REFERENCE TREE IS DIRTY". Observed exactly once, on the run
    that added this comment: ticket-plugin, lyos/server-v2, sophie/sophie -- the first
    succeeded and the two behind it were blocked by the first one's own side effect.

    The guard's real question is "did a human leave uncommitted work here", and that is a fact
    about the moment the run began, not about what the run has since done to itself. Seeded in
    main() before anything is written, so the answer cannot be self-inflicted.
    """
    global _REF_DIRTY
    if _REF_DIRTY is None or recheck:
        _REF_DIRTY = bool(subprocess.run(["git", "-C", str(SLOPSTOP), "status", "--porcelain"],
                                         capture_output=True, text=True).stdout.strip())
    return _REF_DIRTY


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

# Leading-slash form, deliberately: these are repo-root directories, and the bare `scratch/`
# would also ignore a `scratch/` anywhere deeper in the tree, which is not the intent.
STATE_DIR_COMMENT = (
    "# slopstop local state. `.slopstop/` holds the ticket tracking and archive dirs;\n"
    "# `scratch/` holds :design run output. Both are working state rather than source —\n"
    "# an unignored `.slopstop/` puts live run state into every diff."
)

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
        # Strip every line this script has ever written here -- the block's COMMENTS as well
        # as its patterns -- before re-appending it.  Stripping only the patterns made the
        # rewrite non-idempotent in the least visible way possible: the rules stayed correct
        # (one `.claude/*`, so `git check-ignore` kept passing and the verifier kept saying
        # ok) while the comment paragraph accumulated one fresh copy per run.  Found at three
        # copies in the one repo that got re-applied while being debugged.
        #
        # Whole-line matching, deliberately, rather than a BEGIN/END delimited region: this
        # repo has a scar from marker-delimited splicing (see CLAUDE.md) where a loose match
        # silently terminated at the wrong line.  There is no region to mis-delimit here.
        block_lines = {l.strip() for l in GITIGNORE_BLOCK.splitlines() if l.strip()}
        keep = [l for l in lines
                if l.strip() not in block_lines
                and l.strip() not in (".claude/", "/.claude/", ".claude")
                and not l.strip().startswith((".claude/*", "!.claude/"))]
        gi.write_text("\n".join(keep).rstrip() + "\n\n" + GITIGNORE_BLOCK + "\n")
        still = [rel for rel, got, want, _ in state() if got != want]
        res.add(repo, ".gitignore", FIXED if not still else BAD,
                "rewrote the .claude block" + (f"; STILL WRONG: {still}" if still else ""))

    # Probe a path INSIDE the directory, never the bare name. A trailing-slash pattern
    # (`scratch/`) is directory-only, and `git check-ignore scratch` returns NO MATCH when the
    # directory does not exist yet — git cannot know it is a directory. That produced a false
    # FAIL on a repo that had the rule all along, which then "fixed itself" once check_dirs
    # created the directory: a wrong report that self-corrects for the wrong reason is worse
    # than a stable wrong one, because it looks like the tool repaired something.
    def unignored():
        return [p for p in GITIGNORE_SHOULD_IGNORE
                if not _ignored(repo, p.strip("/") + "/__probe__")]

    missing = unignored()
    if not missing:
        res.add(repo, "ignored state dirs", OK, "both ignored")
    elif not apply:
        res.add(repo, "ignored state dirs", BAD, f"not ignored: {', '.join(missing)}")
    else:
        # Until BILL-491 this branch did not exist: GITIGNORE_SHOULD_IGNORE was read by the
        # check above and nowhere else, so the tool reported the same fault on every run and
        # could never repair it. On a new project that is not cosmetic -- an unignored
        # `.slopstop/` puts live ticket-tracking state into every diff.
        #
        # Appends ONLY what git says is missing, so a repo already ignoring these by another
        # spelling (a bare `.slopstop/` rather than `/.slopstop/`) gains no redundant second
        # rule. That is also what makes this idempotent: once the probe passes, `missing` is
        # empty and nothing is written.
        gi = repo / ".gitignore"
        head = (gi.read_text().rstrip("\n") + "\n\n") if gi.exists() else ""
        gi.write_text(head + STATE_DIR_COMMENT + "\n" + "\n".join(missing) + "\n")
        still = unignored()
        res.add(repo, "ignored state dirs", FIXED if not still else BAD,
                f"appended {', '.join(missing)}"
                + (f"; STILL WRONG: {still}" if still else ""))


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


# ---------------------------------------------------------------- part 5: the subagent recorder
HOOK_EVENTS = ("SubagentStart", "SubagentStop", "StopFailure")
HOOK_SCRIPT = SLOPSTOP / "tools/hooks/slopstop_hook.py"
HOOK_MARKER = "slopstop_hook.py"


def check_hooks(repo: pathlib.Path, apply: bool, res: Result):
    """`.claude/settings.json` wires the deterministic subagent recorder (BILL-496).

    PER PROJECT, not user level. A user-level block would cover the fleet in one write, but it
    would also fire in every unrelated repo and could not vary per project. Per project is what
    makes a test install a real install.

    ONE SCRIPT, referenced by absolute path. Copying it per repo would be N copies of one
    definition (universal §5), and `.claude/hooks/` is not among the paths the fleet's
    `.gitignore` un-ignores, so the copies would be untracked anyway.

    THIS FILE IS GITIGNORED, and that is deliberate rather than an oversight. `.gitignore`
    un-ignores only `.claude/{rules,skills,agents}`, so settings stay machine-local -- correct
    for two repos shared with another contributor, where committing this would push slopstop's
    tooling onto someone who did not ask for it, and correct for an absolute path that is only
    true on this machine.

    The consequence is that git cannot tell you whether a repo has the recorder, which is the
    same shape as every silent-absence bug this script exists to catch. That is exactly why the
    check is here: an invisible config needs a verifier, or a repo quietly runs without it.
    """
    want = {"type": "command", "command": f"python3 {HOOK_SCRIPT}", "async": True, "timeout": 10}
    settings = repo / ".claude" / "settings.json"
    try:
        cfg = json.loads(settings.read_text() or "{}") if settings.exists() else {}
    except json.JSONDecodeError as e:
        res.add(repo, "subagent hooks", BAD, f"{settings.name} is not valid JSON ({e}) — not touched")
        return

    def installed(c):
        return [ev for ev in HOOK_EVENTS
                if sum(1 for g in c.get("hooks", {}).get(ev, [])
                       for h in g.get("hooks", []) if HOOK_MARKER in str(h.get("command", ""))) == 1]

    have = installed(cfg)
    if len(have) == len(HOOK_EVENTS):
        res.add(repo, "subagent hooks", OK, f"recorder wired for {', '.join(HOOK_EVENTS)}")
        return
    missing = [e for e in HOOK_EVENTS if e not in have]
    if not apply:
        res.add(repo, "subagent hooks", BAD, f"not wired: {', '.join(missing)}")
        return
    hooks = cfg.setdefault("hooks", {})
    for ev in HOOK_EVENTS:
        # Idempotent by CONTENT: drop any group already pointing at this script, then re-add.
        # Appending blindly is how a settings file grows one duplicate per install and fires
        # the recorder N times.
        groups = [g for g in hooks.get(ev, [])
                  if not any(HOOK_MARKER in str(h.get("command", "")) for h in g.get("hooks", []))]
        hooks[ev] = groups + [{"hooks": [dict(want)]}]
    settings.parent.mkdir(parents=True, exist_ok=True)
    settings.write_text(json.dumps(cfg, indent=2) + "\n")
    still = [e for e in HOOK_EVENTS if e not in installed(cfg)]
    res.add(repo, "subagent hooks", FIXED if not still else BAD,
            f"wired {', '.join(missing)}" + (f"; STILL WRONG: {still}" if still else ""))


# ---------------------------------------------------------------- part 6: on disk != in git
def check_tracked(repo: pathlib.Path, apply: bool, res: Result):
    """Installed is not the same as committed, and every other check here conflates them.

    The stamp this script writes into each skill is a version freeze -- a claim about which
    slopstop produced the file. A stamp nobody can read out of the repository freezes
    nothing. This check exists because the script reported a confident 8/8 for a repo whose
    seventeen skills were entirely uncommitted: every content check passed, `git check-ignore`
    agreed they were committable, and a worktree cut from that repo's master would still have
    had no slopstop in it at all. Green for exactly the failure the freeze exists to prevent.

    Staged-but-uncommitted is called out separately from untracked on purpose. `git ls-files`
    reports the index, so staged files look tracked to any check built on it -- which is how
    that repo showed 29 "tracked" files and zero commits at the same time.

    Deliberately NOT repaired by --apply. Committing is the human's call, and at least one
    repo in this fleet carries a `## Pre-commit (overrides universal §1)` forbidding commits
    by default; a setup script that committed on its behalf would break the rule it had just
    finished installing.
    """
    dirs = [".claude/skills", ".claude/rules", ".claude/agents"]
    on_disk = {str(f.relative_to(repo))
               for rel in dirs if (repo / rel).is_dir()
               for f in (repo / rel).rglob("*") if f.is_file()}
    if not on_disk:
        res.add(repo, "committed", BAD, "nothing installed yet — see the skills check above")
        return

    def _git(*a):
        p = subprocess.run(["git", "-C", str(repo), *a], capture_output=True, text=True)
        return set(p.stdout.splitlines()) if p.returncode == 0 else set()

    # Presence in HEAD is NOT enough, and checking only that reproduced this check's own bug
    # one layer down: right after a re-apply, every skill is tracked by path while carrying a
    # stamp newer than anything committed. The file says 8874d87, git says cd91635, and the
    # freeze is a lie again. So compare CONTENT against HEAD, not just paths.
    #
    # Both signals are needed. `git diff HEAD` cannot see a file git does not track, and the
    # path comparison cannot see a tracked file whose contents drifted -- and the ignored-and-
    # uncommitted case is invisible to `git status` entirely, which is why this does not use it.
    committed = _git("ls-tree", "-r", "HEAD", "--name-only")
    indexed = _git("ls-files")
    absent = on_disk - committed
    modified = (_git("diff", "HEAD", "--name-only", "--", *dirs) & on_disk) - absent
    if not absent and not modified:
        res.add(repo, "committed", OK, f"all {len(on_disk)} installed files match HEAD")
        return
    staged, untracked = len(absent & indexed), len(absent - indexed)
    parts = [f"{n} {label}" for n, label in
             ((staged, "staged"), (untracked, "untracked"), (len(modified), "modified")) if n]
    res.add(repo, "committed", BAD,
            f"{len(absent | modified)} of {len(on_disk)} installed files differ from HEAD "
            f"({', '.join(parts)}) — commit them; an uncommitted version freeze freezes nothing")


PARTS = [check_universal, check_skills, check_gitignore, check_dirs, check_hooks,
         check_tracked]


def _toplevel(path: pathlib.Path):
    """The git work-tree root containing `path`, or None if there is not one.

    `capture_output` is load-bearing, not tidiness: outside a repository git writes
    `fatal: not a git repository` to stderr, and letting that through is what made the
    original failure look like ordinary noise above an authoritative-looking table.
    """
    p = subprocess.run(["git", "-C", str(path), "rev-parse", "--show-toplevel"],
                       capture_output=True, text=True)
    return pathlib.Path(p.stdout.strip()).resolve() if p.returncode == 0 else None


def run(rel: str, apply: bool, res: Result):
    """Guard the target BEFORE any check runs, and refuse rather than score it.

    `--repos` resolves any name against $HOME and used to hand it straight to the checks.
    Free-form names are deliberate -- setting up a project not yet in REPOS is the point --
    but nothing verified the result was a repository, so `--repos sophie` (a container
    directory holding two unrelated repos) produced a confident `2/8 checks pass -- 6
    FAILING`. It reads as a project needing setup. It is not a project.

    Under --apply that would have written universal.md, seventeen skills, `scratch/` and
    `.slopstop/` into a directory git does not manage: unrecoverable by `git checkout`, and
    invisible to every later verification, because `check_gitignore` asks `git check-ignore`
    -- which cannot answer outside a repository, so its verdict there is meaningless rather
    than merely wrong. The tool printed six `fatal: not a git repository` lines and rendered
    the table anyway.

    The three outcomes are reported distinctly because they need different fixes: a typo, a
    directory that is not a repository, and a path inside one but not at its root.
    """
    repo = HOME / rel
    if not repo.is_dir():
        res.add(repo, "repo", BAD, "path does not exist under $HOME — check the name")
        return
    top = _toplevel(repo)
    if top is None:
        res.add(repo, "repo", BAD,
                "not a git repository — refusing to install slopstop into a directory git "
                "does not manage")
        return
    if top != repo.resolve():
        res.add(repo, "repo", BAD,
                f"not a repository ROOT — it sits inside {top}; name that instead")
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
    ap.add_argument("--repos", help="comma-separated, relative to $HOME; each must be the ROOT "
                                    "of a git repository (default: whole fleet)")
    ap.add_argument("--apply", action="store_true", help="perform changes, then re-verify")
    args = ap.parse_args()
    repos = args.repos.split(",") if args.repos else REPOS

    _reference_dirty(recheck=True)   # seed BEFORE anything is written
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
