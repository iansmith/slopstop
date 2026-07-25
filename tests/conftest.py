"""Shared helpers for the slopstop structural test suite.

Created by BILL-322. Three test modules had each grown their own markdown
section-extractor with subtly different semantics, and the third (added by
BILL-322 itself) shipped a real bug: it terminated on any line starting with `#`,
including the `## Definition of Done` *inside* a fenced ```markdown template. The
reference files exist precisely to hold those fenced templates, so the helper
truncated exactly the sections it was written to scope.

One fence-aware implementation lives here instead. See `section()`.
"""

import re
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
SKILLS_DIR = REPO_ROOT / "skills"


def _heading_depth(line):
    """Number of leading '#' chars if `line` is an ATX heading, else 0."""
    if not line.startswith("#"):
        return 0
    return len(line) - len(line.lstrip("#"))


def section(text, heading):
    """Text from `heading` up to the next heading of the same or shallower depth.

    Two things this gets right that hand-rolled versions did not:

    - **Fenced code blocks are skipped.** A ``` fence toggles "inside a fence",
      and headings inside one are content, not boundaries. Without this, any
      section containing a markdown template ends at the template's first
      heading — silently, returning a stub that assertions then pass or fail
      against for the wrong reason.
    - **Depth-aware termination.** `## 2a.` ends at the next `##` or `#`, not at
      the first `###` nested under it. A helper that breaks on `\\n## ` only
      cannot scope a subsection at all.

    Matches `heading` as a **heading-line prefix**, so `"## 2a."` finds
    `"## 2a. Draft the Definition of Done (client-readable)"`. The match must be
    on a heading line, so a prose mention of the same text earlier in the file
    does not reroot the section.

    Returns "" when the heading is absent — callers that require it should assert
    on the heading themselves, so the failure names the missing heading rather
    than an empty match.
    """
    lines = text.splitlines()
    target = heading.strip()
    start = None
    in_fence = False
    for i, line in enumerate(lines):
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            continue
        if not in_fence and _heading_depth(line) and line.strip().startswith(target):
            start = i
            break
    if start is None:
        return ""

    depth = _heading_depth(target)
    out = []
    in_fence = False
    for line in lines[start + 1 :]:
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            out.append(line)
            continue
        if not in_fence:
            d = _heading_depth(line)
            if d and d <= depth:
                break
        out.append(line)
    return "\n".join(out)


POINTER_RE = re.compile(r"slopstop-([a-z-]+)-refs/([A-Za-z0-9._-]+\.md)")


def reachable_references(skill):
    """Walk `→ Read` pointers transitively from a skill's spine.

    Returns `(reached, broken)` — a set of `(skill, filename)` pairs actually
    reachable, and a list of pointer strings whose target file does not exist.

    Transitive, not spine-only, and that distinction has already mattered twice.
    BILL-322 shipped a spine-only check; BILL-324 then demoted two `:merge`
    references to second hop (`merge-target-given.md`, reachable only via
    `merge-pr-resolution.md`, and `merge-state-machines.md` via
    `merge-ticket-system.md`). Under a spine-only check either could be renamed with
    every test green while dead-ending a whole execution path at runtime.

    Extracted here by BILL-325 — the second consumer. Universal §4 fires on 2+
    near-identical code paths, which is now, not when the first copy was written.
    """
    reached, queue, broken = set(), [spine(skill)], []
    while queue:
        for target_skill, filename in POINTER_RE.findall(queue.pop()):
            key = (target_skill, filename)
            if key in reached:
                continue
            reached.add(key)
            path = SKILLS_DIR / target_skill / "references" / filename
            if path.is_file():
                queue.append(path.read_text())
            else:
                broken.append(f"slopstop-{target_skill}-refs/{filename}")
    return reached, broken


def spine(skill):
    """A skill's SKILL.md text."""
    return (SKILLS_DIR / skill / "SKILL.md").read_text()


def ref(skill, filename):
    """A skill's references/<filename> text."""
    return (SKILLS_DIR / skill / "references" / filename).read_text()
