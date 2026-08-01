#!/usr/bin/env python3
"""
Migrate the universal CLAUDE.md block from a spliced in-file region to a
standalone CLAUDE-universal.md + a one-line @import.  (slopstop #364)

WHAT IT DOES, per repo:
  1. Writes  <repo>/CLAUDE-universal.md   <- the REFERENCE block content
  2. Rewrites <repo>/CLAUDE.md            <- marked region replaced by:
                                              @CLAUDE-universal.md
  3. Leaves everything outside the markers untouched (project-specific
     sections, including deliberate overrides like mazzy's
     "## Pre-commit (overrides universal §1)").

This also RESOLVES THE CURRENT DRIFT: as of 2026-08-01 the reference block
(ticket-plugin, 137 lines) was 18 lines ahead of all five mirrors (119 lines).
Every repo ends on the reference content.

USAGE
  python3 migrate-universal-block.py             # dry run  (default, writes nothing)
  python3 migrate-universal-block.py --apply     # actually write
  python3 migrate-universal-block.py --verify    # check an already-migrated fleet

  Add --repos a,b,c  to override the list for one run.

SAFE TO RE-RUN.  Already-migrated repos are detected and verified rather than
re-migrated.  Nothing is committed — commit commands are printed at the end so
you review each repo's diff yourself.

The fleet list lives in fleet.py — one definition, imported by every script here.
A path that does not exist is reported and skipped, never guessed at.
"""

import argparse
import hashlib
import pathlib
import shutil
import sys

from fleet import HOME, LOCAL_RULES_REPOS, REFERENCE as REFERENCE_REPO, REPO_PATHS

# --------------------------------------------------------------------------
# Configuration
# --------------------------------------------------------------------------

REFERENCE = REFERENCE_REPO / "CLAUDE.md"   # the marked block / shared file to copy FROM
REPOS = REPO_PATHS                        # see fleet.py — one definition of the fleet

SHARED_NAME = "CLAUDE-universal.md"
IMPORT_LINE = f"@{SHARED_NAME}"

# What replaces the marked region: a short human-readable statement plus the
# import on its OWN line.  The import must not be backticked and must not sit
# inside a fence -- either makes it inert while still looking right.
POINTER_BLOCK = f"""## Universal Project Rules

These live in `{SHARED_NAME}` alongside this file — one mirrored copy per project,
byte-identical everywhere. **Edit them in the slopstop repo (the reference copy) and
propagate; never edit the copy in this repo.** Project-specific rules and deliberate
overrides go below, in this file, where they take precedence.

{IMPORT_LINE}"""

BEGIN = "<!-- BEGIN UNIVERSAL SECTION -->"
END = "<!-- END UNIVERSAL SECTION -->"

# Header prepended to the standalone file.  Block-level HTML comments are
# stripped before CLAUDE.md content is injected into context, so this costs
# zero tokens and is visible only to humans reading the file.
SHARED_HEADER = """<!-- This file is MIRRORED.  Do not edit it here unless this repo is the
     reference (slopstop / ticket-plugin).  Edit the reference copy, then run
     tools/fleet-sync/migrate-universal-block.py --apply to propagate.
     Imported by CLAUDE.md via a single `@CLAUDE-universal.md` line. -->
"""


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------

def md5(text: str) -> str:
    return hashlib.md5(text.encode()).hexdigest()


def marker_lines(text):
    """STUB — non-satisfying sentinel. Phase 0 only; replace with the real scan."""
    return [-1]


def bounds(lines, path):
    """Whole-line marker match, exactly one of each, in order.

    This strictness is the whole point.  The marker NAMES appear inside §10's
    own prose, so a loose match (awk '/BEGIN/,/END/', or str.index(END))
    terminates at the wrong place SILENTLY -- that is the documented trap that
    corrupted sophie on 2026-07-17.  A file with 0 or 2+ markers is a corrupted
    mirror and we refuse rather than guess.
    """
    b = [i for i, l in enumerate(lines) if l == BEGIN]
    e = [i for i, l in enumerate(lines) if l == END]
    if len(b) != 1 or len(e) != 1 or b[0] >= e[0]:
        raise ValueError(
            f"{path}: need exactly one BEGIN and one END line, in order "
            f"(got {len(b)} BEGIN / {len(e)} END)"
        )
    return b[0], e[0]


def import_line_count(lines):
    """Count whole-line @CLAUDE-universal.md occurrences.

    Whole-line so a backticked mention in prose is not miscounted.  Backticked
    text is inert as an import anyway (import parsing skips code spans).
    """
    return sum(1 for l in lines if l.strip() == IMPORT_LINE)


def in_fenced_block(lines, target_idx):
    """True if lines[target_idx] sits inside a ``` fence.

    An import inside a fence is silently inert -- it looks correct and does
    nothing.  Worth checking explicitly.
    """
    fence = False
    for i, l in enumerate(lines):
        if i == target_idx:
            return fence
        if l.lstrip().startswith("```"):
            fence = not fence
    return False


def shared_file_is_gitignored(repo):
    """True when git would refuse to track the shared file in this repo.

    This is the nastiest failure this tool can produce, and it bit for real on
    2026-08-01: three repos carry `/*.md` in .gitignore with per-file negations
    (`!/CLAUDE.md`). CLAUDE-universal.md matched the ignore, `git add` skipped it
    without complaint, and they committed a CLAUDE.md whose rules had been
    deleted and replaced with an import of a file git would never carry. A fresh
    clone got NO universal rules -- silently, and worse than the design this
    replaced. Refuse instead.

    Remedy is a negation line in .gitignore. Note it must be on its OWN line:
    .gitignore honours `#` only at the start of a line, so a trailing comment
    makes the whole thing a literal pattern that matches nothing (that also bit).
    """
    import subprocess
    r = subprocess.run(["git", "check-ignore", "-q", SHARED_NAME],
                       cwd=repo, capture_output=True)
    return r.returncode == 0


def repo_key(repo):
    """HOME-relative key identifying a repo, worktree-safe. None if outside HOME.

    Two reasons this is not `str(repo).replace(str(HOME) + "/", "")`:

    1. `str.replace` substitutes EVERY occurrence, not just a leading prefix. It
       happens to work only because HOME does not recur inside these paths --
       incidental, not structural.
    2. `--repos` is routinely pointed at a git WORKTREE (universal §6 tells
       agents to work in one, and this migration used three). A worktree lives
       outside HOME, so naive relativisation yields an absolute path that matches
       nothing -- LOCAL_RULES_REPOS would silently fail to engage and the run
       would hard-BLOCK on the very repo the exception was written for, with an
       error message about .gitignore that is not the real cause.

    Resolving through the common git dir maps a worktree back to the repo it
    belongs to, so the key is the same either way.
    """
    import subprocess
    if not repo.is_dir():
        return None
    try:
        r = subprocess.run(["git", "rev-parse", "--git-common-dir"],
                           cwd=repo, capture_output=True, text=True)
    except OSError:
        return None
    root = repo
    if r.returncode == 0 and r.stdout.strip():
        common = pathlib.Path(r.stdout.strip())
        if not common.is_absolute():
            common = (repo / common).resolve()
        root = common.parent
    try:
        return root.relative_to(HOME).as_posix()
    except ValueError:
        return None


def classify(repo):
    """-> (state, detail).

    states:
      missing   no CLAUDE.md at all
      unblocked CLAUDE.md exists but has never carried the universal block
      legacy    marked region present, not yet migrated
      migrated  @import + shared file present, shared file readable
      needs-shared  @import present but the shared file was never propagated
      broken    contradictory or corrupt

    Six states, all returned by this function -- main() invents none of its own.
    """
    cm = repo / "CLAUDE.md"
    if not cm.is_file():
        return "missing", f"no CLAUDE.md at {cm}"
    lines = cm.read_text().split("\n")
    has_markers = BEGIN in lines or END in lines
    n_import = import_line_count(lines)
    if not has_markers and n_import == 1:
        shared = repo / SHARED_NAME
        if not shared.is_file():
            # Not corruption: this is exactly the state right after a repo is
            # adopted by hand (import line added, file not yet propagated).
            # Repairable by writing the shared file -- which is what --apply does.
            return "needs-shared", f"imports {SHARED_NAME}; file not yet propagated"
        return "migrated", md5(shared.read_text())
    if has_markers and n_import == 0:
        try:
            bounds(lines, cm)
        except ValueError as exc:
            return "broken", str(exc)
        return "legacy", ""
    if not has_markers and n_import == 0:
        # A repo that never had the universal block -- newly adopted, not
        # corrupt.  Migration for it is "install", not "convert": append the
        # import and write the shared file.  Distinguished from `broken`
        # because the remedy is completely different.
        return "unblocked", "CLAUDE.md has no universal block (never adopted)"
    return "broken", (
        f"mixed state: markers={has_markers}, @import lines={n_import}"
    )


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true",
                    help="actually write files (default is a dry run)")
    ap.add_argument("--verify", action="store_true",
                    help="only check an already-migrated fleet; write nothing")
    ap.add_argument("--repos",
                    help="comma-separated repo paths, overriding the built-in list")
    args = ap.parse_args()

    repos = ([pathlib.Path(p).expanduser() for p in args.repos.split(",")]
             if args.repos else REPOS)

    mode = "VERIFY" if args.verify else ("APPLY" if args.apply else "DRY RUN")
    print(f"=== universal-block migration — {mode} ===\n")

    # ---- 1. extract the reference block -----------------------------------
    if not REFERENCE.is_file():
        sys.exit(f"FATAL: reference not found: {REFERENCE}")
    ref_lines = REFERENCE.read_text().split("\n")

    ref_state, _ = classify(REFERENCE.parent)
    if ref_state == "migrated":
        shared_body = (REFERENCE.parent / SHARED_NAME).read_text()
        print(f"reference already migrated; using {REFERENCE.parent / SHARED_NAME}")
    elif ref_state == "legacy":
        i, j = bounds(ref_lines, REFERENCE)
        # Drop the two marker lines themselves; they are splice machinery.
        body = "\n".join(ref_lines[i + 1:j]).strip("\n")
        shared_body = SHARED_HEADER + "\n" + body + "\n"
        print(f"reference block extracted: {REFERENCE} lines {i + 1}-{j + 1}")
    else:
        sys.exit(f"FATAL: reference is in state '{ref_state}' — fix it first.")

    ref_hash = md5(shared_body)
    print(f"reference content md5: {ref_hash}  ({len(shared_body.splitlines())} lines)\n")

    # ---- 2. per-repo ------------------------------------------------------
    results, problems = [], []

    for repo in repos:
        label = str(repo).replace(str(HOME), "~")
        if not repo.is_dir():
            print(f"  [SKIP]      {label}  — directory does not exist")
            problems.append((label, "directory does not exist"))
            continue

        state, detail = classify(repo)
        rewrite_claude_md = True   # cleared only for a drifted-but-migrated repo

        # LOCAL_RULES_REPOS: deliberately machine-local, so a gitignored shared
        # file is expected there rather than an error. Everywhere else it is fatal.
        if (state != "missing"
                and repo_key(repo) not in LOCAL_RULES_REPOS
                and shared_file_is_gitignored(repo)):
            why = (f"{SHARED_NAME} is gitignored here — it would never be "
                   f"committed, and CLAUDE.md would import a file a fresh clone "
                   f"does not have. Add a '!/{SHARED_NAME}' negation to "
                   f".gitignore (on its own line — a trailing comment is not a "
                   f"comment there), then re-run.")
            print(f"  [BLOCKED]   {label}  — {SHARED_NAME} is gitignored")
            problems.append((label, why))
            continue

        if state == "broken":
            print(f"  [BROKEN]    {label}  — {detail}")
            problems.append((label, detail))
            continue

        if state == "missing":
            print(f"  [SKIP]      {label}  — {detail}")
            problems.append((label, detail))
            continue

        if state == "needs-shared":
            if args.verify:
                print(f"  [PENDING]   {label}  — {detail}")
                problems.append((label, detail))
                continue
            if args.apply:
                (repo / SHARED_NAME).write_text(shared_body)
                print(f"  [PROPAGATED] {label}  — shared file written")
            else:
                print(f"  [WOULD DO]  {label}  — write shared file only")
            results.append((label, ref_hash))
            continue

        if state == "unblocked":
            # Install rather than convert. Deliberately NOT automatic: where the
            # import goes in an existing CLAUDE.md is an editorial call (it must
            # precede any project-specific override section to keep override
            # semantics), and guessing it wrong is silent.
            print(f"  [ADOPT?]    {label}  — {detail}")
            problems.append((label,
                             "never adopted the universal block; add "
                             f"'{IMPORT_LINE}' by hand at the right position, "
                             "then re-run to have the shared file written"))
            continue

        if state == "migrated":
            ok = detail == ref_hash
            print(f"  [{'OK' if ok else 'DRIFT':<9}] {label}  — already migrated"
                  f"{'' if ok else f', md5 {detail[:8]}… != reference {ref_hash[:8]}…'}")
            if ok:
                results.append((label, detail))
                continue
            if args.verify:
                problems.append((label, "content drifted from reference"))
                continue
            # Drifted: CLAUDE.md is already correct, only the shared file is
            # stale. Fall through and rewrite just that.
            rewrite_claude_md = False

        if args.verify:
            print(f"  [PENDING]   {label}  — still legacy, not migrated")
            problems.append((label, "not yet migrated"))
            continue

        cm = repo / "CLAUDE.md"
        shared = repo / SHARED_NAME
        lines = cm.read_text().split("\n")

        if not rewrite_claude_md:
            new_cm = None                     # CLAUDE.md already correct
        else:
            i, j = bounds(lines, cm)
            new_cm = "\n".join(lines[:i] + POINTER_BLOCK.split("\n") + lines[j + 1:])
            # Guard: the import must not land inside a fence.
            if in_fenced_block(new_cm.split("\n"), i):
                problems.append((label, "import line would land inside a code fence"))
                print(f"  [BROKEN]    {label}  — import would land inside a fence")
                continue

        if args.apply:
            if new_cm is not None:
                shutil.copy2(cm, cm.with_suffix(".md.pre-364.bak"))
                cm.write_text(new_cm)
            shared.write_text(shared_body)
            print(f"  [MIGRATED]  {label}")
        else:
            action = "write shared + rewrite CLAUDE.md" if new_cm is not None \
                     else "rewrite shared file only"
            print(f"  [WOULD DO]  {label}  — {action}")

        results.append((label, ref_hash))

    # ---- 2b. residual prose mentions --------------------------------------
    # The script only replaces the MARKED REGION.  Prose *outside* it that talks
    # about the marker machinery (slopstop's embedded propagation script, the
    # trap table) is left alone by design -- but it now describes machinery that
    # no longer exists.  Flag it; #364's DoD covers deleting it by hand.
    residual = []
    for repo in repos:
        cm = repo / "CLAUDE.md"
        if not cm.is_file():
            continue
        hits = [n for n, l in enumerate(cm.read_text().split("\n"), 1)
                if "UNIVERSAL SECTION" in l]
        if hits:
            residual.append((str(repo).replace(str(HOME), "~"), hits))

    if residual:
        print("\nRESIDUAL PROSE — these lines still mention the retired markers.")
        print("They sit OUTSIDE the marked region, so this script left them alone")
        print("on purpose.  Delete/rewrite them by hand (#364 DoD):")
        for label, hits in residual:
            print(f"  - {label}/CLAUDE.md lines {', '.join(map(str, hits))}")

    print("\nSTILL TO DO BY HAND after --apply (the script relocates, it never")
    print("edits rule text):")
    print("  1. CLAUDE-universal.md §10 still describes the marker/splice")
    print("     mechanism — rewrite it for copy+hash propagation, then re-run")
    print("     --apply so every mirror gets the corrected text.")
    print("  2. Delete the embedded propagation script + trap table from")
    print("     slopstop's CLAUDE.md (the residual lines listed above).")
    print("  3. Re-aim tests/test_bill355_behaviors.py::TestUniversalBlockUnchanged")
    print("     at CLAUDE-universal.md — it locates content by the removed markers,")
    print("     so it FAILS until updated. That failure is expected, not a flake.")
    print("  4. Open a fresh session in one migrated repo and run /context —")
    print("     CLAUDE-universal.md must appear under 'Memory files'. This is the")
    print("     only real proof the import resolves.")

    # ---- 3. summary -------------------------------------------------------
    print()
    if problems:
        print("PROBLEMS — resolve these before trusting the fleet:")
        for label, why in problems:
            print(f"  - {label}: {why}")
        print()

    if args.apply and results:
        print("Review each diff, then commit.  Universal §3: explicit branch name;")
        print("push to ALL remotes where a repo has more than one (mobile-v2 and")
        print("server-v2 have mycopy + origin).  Backups written as CLAUDE.md.pre-364.bak.")
        print()
        for label, _ in results:
            print(f"  (cd {label} && git diff --stat && git add {SHARED_NAME} CLAUDE.md)")
        print()

    hashes = {h for _, h in results}
    if len(hashes) == 1 and not problems:
        print(f"IN SYNC: {hashes.pop()}  across {len(results)} repo(s)")
        return 0
    if len(hashes) > 1:
        print(f"MIRRORS DISAGREE: {hashes}")
    return 1 if problems or len(hashes) > 1 else 0


if __name__ == "__main__":
    sys.exit(main())
