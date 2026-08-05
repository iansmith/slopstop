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
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
SKILLS_DIR = REPO_ROOT / "skills"

# lizard --csv's headerless column order (verified against lizard 1.23.0). Two
# consumers as of BILL-341 (test_cc_gate_invocation.py, test_cc_exemption.py) —
# extracted here rather than left duplicated, same reasoning as `reachable_references`
# above: a third divergent copy is how this kind of contract silently drifts.
CSV_COLUMNS = [
    "nloc",
    "ccn",
    "token_count",
    "param_count",
    "length",
    "long_name",
    "filename",
    "name",
    "signature",
    "start_line",
    "end_line",
]

# The derived-metrics record contract — one definition (universal §5).
#
# Three test files each kept their own copy, so BILL-454's schema bump broke two
# suites that had nothing to do with it. A fourth bump is already scheduled
# (#443 removes simplify_line_delta), which is why this moved here rather than
# being re-pinned in place a third time.
#
# The four keys added by BILL-454 are skeleton stubs; each is filled in by its own
# ticket — spans #406, spawns #445, active #452, version #453.
DERIVED_METRICS_KEYS = {
    "schema",
    "ticket",
    "system",
    "repo",
    "generated_at",
    "timing",
    "tokens",
    "phases",
    "signals",
    "spans",
    "spawns",
    "active",
    "version",
}

DERIVED_METRICS_SCHEMA = "slopstop.derived-metrics/2"


def tracked_files():
    """Every file `git ls-files` reports, as absolute paths under REPO_ROOT.

    Second consumer as of BILL-341 (test_cc_gate_invocation.py,
    test_cc_exemption.py) — extracted for the same reason as `CSV_COLUMNS` above.
    """
    out = subprocess.run(
        ["git", "ls-files"], cwd=REPO_ROOT, capture_output=True, text=True, check=True
    ).stdout
    return [REPO_ROOT / p for p in out.split("\n") if p]


def _heading_depth(line):
    """Number of leading '#' chars if `line` is an ATX heading, else 0."""
    if not line.startswith("#"):
        return 0
    return len(line) - len(line.lstrip("#"))


def _matches_heading(line, target):
    """True when `line` is the heading `target` names — matched at a boundary.

    `target` is a **prefix** of a heading line by design: callers pass
    `"## Step 1"` for `## Step 1 — Resolve the PR`. The boundary is what stops
    that prefix from also matching a longer sibling.

    That boundary is space-or-end-of-line, and both halves are load-bearing:

    - Without it (a bare `startswith`, which is what this was until BILL-330),
      `"## Step 1"` matches `## Step 10 — Inline archive`. Nine such collisions
      exist across `skills/`, over three separator shapes — a digit (`Step 1` /
      `Step 10`), a letter (`Step 2` / `Step 2d`), and a dot (`Step 3` /
      `Step 3.5`). Which heading won was decided by file order, so a test could
      keep passing while silently scoping to the wrong section.
    - Without the end-of-line half, a target that is an entire heading stops
      matching. `skills/pr/SKILL.md` has a bare `## Arguments` with nothing after
      it, and some callers pass whole heading lines lifted from the file.

    Compared on the stripped line: `target` arrives stripped, and heading lines
    may carry trailing whitespace.
    """
    stripped = line.strip()
    return stripped == target or stripped.startswith(target + " ")


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

    Matches `heading` as a **heading-line prefix ending at a boundary**, so
    `"## 2a."` finds `"## 2a. Draft the Definition of Done (client-readable)"`
    while `"## Step 1"` does not match `## Step 10` — see `_matches_heading`. The
    match must be on a heading line, so a prose mention of the same text earlier
    in the file does not reroot the section.

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
        if not in_fence and _heading_depth(line) and _matches_heading(line, target):
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


def git(cwd, *args, check=True):
    """Run `git <args>` in `cwd`, returning the completed process (stdout/stderr
    available, not pre-stripped — callers that only want stdout.strip() do that
    themselves).

    Second+ consumer as of BILL-287 (test_cc_exemption.py had its own single-purpose
    version returning a bare stripped string; test_bill287_behaviors.py had a second,
    slightly different one). One definition, callers adapt.
    """
    return subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True, text=True, check=check
    )


def init_git_repo(path):
    """`git init` + a throwaway identity, for tests that build a real repo fixture.

    Third occurrence of this exact three-line bootstrap as of BILL-287 (twice in
    test_bill287_behaviors.py, once in test_cc_exemption.py's scope_fixture_repo)
    — extracted here rather than left duplicated.
    """
    git(path, "init", "-q")
    git(path, "config", "user.email", "t@t.com")
    git(path, "config", "user.name", "t")


def changed_line_ranges(base_sha, path, cwd):
    """Parse `git diff --unified=0` hunk headers for the new-file line ranges a
    branch touched in `path`. Mirrors the algorithm pr-cc-gate.md and
    pr-slop-detection.md both document (BILL-341's exemption, BILL-343's
    vacuity gate) — same hunk-header regex, same +N,0 pure-deletion handling.

    Second occurrence as of BILL-343 (test_cc_exemption.py had its own
    `_changed_ranges`, test_bill343_behaviors.py a second, slightly renamed
    copy) — extracted here rather than left duplicated a third time.
    """
    diff = git(cwd, "diff", "--unified=0", f"{base_sha}..HEAD", "--", path).stdout
    ranges = []
    for m in re.finditer(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@", diff, re.MULTILINE):
        start = int(m.group(1))
        count = int(m.group(2)) if m.group(2) is not None else 1
        ranges.append((start, start if count == 0 else start + count - 1))
    return ranges


def touched(ranges, fn_start, fn_end):
    """Does any (a, b) range in `ranges` overlap [fn_start, fn_end]?"""
    return any(a <= fn_end and fn_start <= b for a, b in ranges)


FORBIDDEN_KEY_PATTERN = re.compile(r"total|basis|effective|invoice", re.IGNORECASE)


def walk_values(obj):
    """Recursively yield every `(key, value)` pair in a JSON-shaped `dict`/`list`.

    Third occurrence as of BILL-390 (test_bill386_behaviors.py and
    test_bill389_behaviors.py each had their own copy) -- extracted here
    rather than left duplicated a third time.
    """
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield k, v
            yield from walk_values(v)
    elif isinstance(obj, list):
        for item in obj:
            yield from walk_values(item)


def assert_no_forbidden_keys(obj, forbidden_sum=None):
    """Assert no key anywhere in `obj` matches `FORBIDDEN_KEY_PATTERN`.

    `forbidden_sum`, when given, is also asserted absent as a value anywhere
    in `obj` -- catching a key that sums counters under an unrelated name.

    Union of three tickets' independent blacklists (BILL-386: `total`;
    BILL-389: `basis`/`effective`; BILL-390: adds `invoice`) -- one shared
    vocabulary instead of three drifting copies.
    """
    for key, value in walk_values(obj):
        assert not FORBIDDEN_KEY_PATTERN.search(key), f"forbidden key: {key!r}"
        if (
            forbidden_sum is not None
            and isinstance(value, int)
            and not isinstance(value, bool)
        ):
            assert value != forbidden_sum, (
                f"key {key!r} equals a forbidden summed value"
            )
