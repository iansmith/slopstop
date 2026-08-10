#!/usr/bin/env python3
"""Fail on relative markdown links whose target does not exist.

    python3 tools/check-markdown-links.py            # this repo
    python3 tools/check-markdown-links.py ../slopstop # some other checkout

Exits 0 when every relative link resolves, 1 when any does not, 2 on a usage error.

WHY THIS FILE EXISTS (BILL-537).  `32ecb23` deleted 147 files and 13,211 lines, and
nothing swept the references to them.  Seven dead relative links survived in four tracked
files, two of which are read as *instructions* -- `.claude/rules/repo-conventions.md` loads
into context at session start, and it pointed sessions at a skill that no longer exists.
The deletion was correct; the missing piece was any mechanism that would have noticed.
This is that mechanism, so the next mass deletion cannot leave the same debt silently.

THE BUG THIS IS WRITTEN AGAINST.  A markdown link resolves against the directory of the
file that *names* it, never against the process working directory.  The naive
implementation gets this wrong and only shows it when run from somewhere other than the
repo root -- at which point it reports every `../CONFIG.md` as missing while the file is
sitting right there.  `_resolve()` is the whole of the fix; `ROOT` is used only to find
the files and to print paths, never to resolve a target.

SCOPE.  Tracked markdown only (`git ls-files`), relative targets only.  External URLs are
a different failure mode with a different fix and would make this need the network, which
a pre-commit-shaped check must not; bare anchors (`#section`) are not a path claim.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

# Links that do not resolve on the filesystem and are correct anyway.  Every entry needs a
# reason -- an exemption without one is indistinguishable from an unfixed dead link.
# Matched as (file-relative-to-root, exact link target).
EXEMPTIONS: dict[tuple[str, str], str] = {
    ("site/index.md", "walkthrough/index.md"): (
        "Correct in the BUILT site, dead only in the tree. `.github/workflows/pages.yml` "
        "stages the walkthrough before Jekyll runs -- `cp -R walkthrough site/walkthrough` "
        "then `mv site/walkthrough/README.md site/walkthrough/index.md` -- and builds with "
        "`source: ./site`. So site/walkthrough/index.md exists at build time and never in "
        "the checkout. Verified against the published site, not inferred: "
        "https://iansmith.github.io/slopstop/walkthrough/ -> 200 (BILL-537, 2026-08-09)."
    ),
    ("site/what_is_slopstop.md", "walkthrough/index.md"): (
        "Same build-time staging as site/index.md above; same 200."
    ),
}

# Inline links and images: [text](target) / ![alt](target).  The target runs to the first
# unescaped ')' or whitespace -- markdown allows `(path "title")`, so stop at the space.
INLINE_LINK = re.compile(r"!?\[[^\]]*\]\(\s*([^)\s]+)")

# Reference definitions at the head of a line: [label]: target
REF_DEF = re.compile(r"^\s{0,3}\[[^\]]+\]:\s*(\S+)")

FENCE = re.compile(r"^\s*(```+|~~~+)")

# Inline code spans: `![alt](url)` in prose is a picture of link syntax, not a link.  Missing
# this is how a checker demands an edit to a doc that is already correct -- `design/
# ticket-doc-sync.md` says "embedded `![alt](url)` references pass through unchanged", which
# BILL-537 first recorded as an "unfilled placeholder" on exactly that misreading.
CODE_SPAN = re.compile(r"(`+)(?:(?!\1).)*\1", re.DOTALL)

# Targets that make no filesystem claim.
SKIP_PREFIXES = ("http://", "https://", "mailto:", "tel:", "#", "data:", "//")


def _tracked_markdown(root: Path) -> list[str]:
    out = subprocess.run(
        ["git", "ls-files", "-z", "--", "*.md"],
        cwd=root,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return sorted(p for p in out.split("\0") if p)


def _links(text: str):
    """Yield (line_number, target) for every relative link, skipping fenced code."""
    fence: str | None = None
    for lineno, line in enumerate(text.splitlines(), 1):
        m = FENCE.match(line)
        if m:
            # A fence closes only on a marker of the same kind; ``` inside ~~~ is content.
            if fence is None:
                fence = m.group(1)[0]
            elif m.group(1)[0] == fence:
                fence = None
            continue
        if fence is not None:
            continue
        # Blank out code spans before matching, preserving length so columns stay honest.
        line = CODE_SPAN.sub(lambda m: " " * len(m.group(0)), line)
        targets = [m.group(1) for m in INLINE_LINK.finditer(line)]
        ref = REF_DEF.match(line)
        if ref:
            targets.append(ref.group(1))
        for target in targets:
            target = target.strip("<>")
            if not target or target.startswith(SKIP_PREFIXES):
                continue
            yield lineno, target


def _resolve(root: Path, md_relpath: str, target: str) -> Path:
    """Resolve TARGET the way a markdown reader does: against the directory of the file
    that names it. Never against the process working directory -- that is the bug."""
    path = target.split("#", 1)[0].split("?", 1)[0]
    return (root / md_relpath).parent / path


def check(root: Path) -> tuple[list[tuple[str, int, str]], list[tuple[str, str]]]:
    dead: list[tuple[str, int, str]] = []
    exempt: list[tuple[str, str]] = []
    for md in _tracked_markdown(root):
        try:
            text = (root / md).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for lineno, target in _links(text):
            path = _resolve(root, md, target)
            if path.exists():
                continue
            if (md, target) in EXEMPTIONS:
                exempt.append((md, target))
                continue
            dead.append((md, lineno, target))
    return dead, exempt


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Fail on relative markdown links whose target does not exist.",
    )
    ap.add_argument(
        "root",
        nargs="?",
        default=".",
        help="repo root to check (default: the current directory). "
        "A relative path resolves from the current directory, not from this script.",
    )
    args = ap.parse_args()

    root = Path(args.root).resolve()
    if not (root / ".git").exists():
        print(f"not a git repository: {root}", file=sys.stderr)
        return 2

    dead, exempt = check(root)

    for md, lineno, target in dead:
        print(f"{md}:{lineno}: dead link -> {target}")

    if exempt:
        print()
        print(f"{len(exempt)} exempt (stated reasons):")
        for md, target in exempt:
            print(f"  {md} -> {target}")
            print(f"      {EXEMPTIONS[(md, target)]}")

    print()
    if dead:
        print(f"{len(dead)} dead relative link(s) in {len({d[0] for d in dead})} file(s)")
        return 1
    print("no dead relative links")
    return 0


if __name__ == "__main__":
    sys.exit(main())
