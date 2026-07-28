"""
Behavior tests for BILL-337 — simplify and slop detection scope to the branch diff.

Both `:pr` Step 1 (simplify) and Step 2e (slop detection) skipped when the working
tree was clean. Every fleet agent reaches `:pr` with a clean tree, because
`:plan` Step 3a commits after each work item — so neither gate ran for any fleet
agent in any `:run`.

The fix is to ask a different question: scope both to the whole branch change
(`git diff <merge-base>`, one ref so it covers committed AND uncommitted work)
rather than to the uncommitted tree. That also retires the "leave implementation
work uncommitted until :pr" rule, which existed only to feed Step 1's diff.

Test command:
    python3 -m pytest tests/test_bill337_behaviors.py -v
"""

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent
PR_SKILL = REPO_ROOT / "skills" / "pr" / "SKILL.md"
PR_SIMPLIFY = REPO_ROOT / "skills" / "pr" / "references" / "pr-simplify.md"
PR_SLOP = REPO_ROOT / "skills" / "pr" / "references" / "pr-slop-detection.md"
PR_REVIEW = REPO_ROOT / "skills" / "pr" / "references" / "pr-claude-review.md"
SKILLS_DIR = REPO_ROOT / "skills"

# The one-ref form is the contract: `git diff A..B` compares two commits and would
# miss uncommitted work; `git diff A` compares A to the working tree.
MERGE_BASE_PAT = re.compile(r"git merge-base")


def _line_starting(text: str, prefix: str) -> str:
    """Return the single line beginning with `prefix`. Scoping matters here.

    Asserting against the whole file passes vacuously — `$DIRTY` appears in
    several unrelated steps of pr/SKILL.md.
    """
    for line in text.split("\n"):
        if line.startswith(prefix):
            return line
    return ""


@pytest.fixture(scope="module")
def pr_skill() -> str:
    return PR_SKILL.read_text()


@pytest.fixture(scope="module")
def simplify() -> str:
    return PR_SIMPLIFY.read_text()


def test_simplify_not_skipped_on_clean_tree(pr_skill: str) -> None:
    """Behavior 1 — Step 1 no longer keys its skip on an empty working tree."""
    line = _line_starting(pr_skill, "Skip if `--no-simplify`")
    assert line, "pr/SKILL.md has no Step 1 skip-condition line"
    assert "$DIRTY" not in line, (
        "Step 1 still skips when $DIRTY is empty. Every fleet agent arrives with a "
        "clean tree (plan Step 3a commits per item), so this condition disables "
        "simplify for the entire fleet pipeline"
    )


def test_slop_detection_not_skipped_on_clean_tree(pr_skill: str) -> None:
    """Behavior 2 — Step 2e loses the same skip. This is the 🔴 gate."""
    line = _line_starting(pr_skill, "Skip if `--no-adversary`")
    assert line, "pr/SKILL.md has no Step 2e skip-condition line"
    assert "$DIRTY" not in line, (
        "Step 2e still skips when $DIRTY is empty. Slop detection is the gate for "
        "test manipulation, expectation inversion and test deletion — Step 2d "
        "already argues, one paragraph above, that a clean tree is precisely when "
        "such a gate must still run"
    )


def test_simplify_scopes_to_merge_base(simplify: str) -> None:
    """Behavior 1 — the diff handed to simplify covers the whole branch change."""
    assert MERGE_BASE_PAT.search(simplify), (
        "pr-simplify.md must capture the diff from the merge-base, not from HEAD — "
        "`git diff HEAD` sees only uncommitted work"
    )
    assert "uncommitted changes in this working tree" not in simplify, (
        "the agent prompt still tells the reviewer to look at uncommitted changes "
        "in the working tree; that is the scope this ticket replaces"
    )


def test_simplify_excludes_frozen_phase0_tests(simplify: str) -> None:
    """Behavior 3 — widening scope must not let simplify touch frozen tests."""
    body = simplify.lower()
    assert "phase 0" in body and "frozen" in body, (
        "pr-simplify.md must state that frozen Phase 0 test files are excluded. "
        "Without it, simplify can 'improve' a frozen assertion and Step 2d then "
        "hard-stops on tampering — a quality pass turned into a tamper failure"
    )
    assert re.search(r"exclud|never modif|do not (touch|modify)", body), (
        "naming Phase 0 is not the same as excluding it — the file must say the "
        "frozen tests are left alone, not merely mention them"
    )


def test_simplify_diff_is_one_ref_not_a_range(simplify: str) -> None:
    """Gap (boundary) — `git diff A..B` would reintroduce the original bug.

    The whole fix rests on the one-ref form: `git diff A` compares A to the
    WORKING TREE, so it covers committed and uncommitted work together. The range
    form compares two commits and silently drops uncommitted work — which is the
    defect this ticket exists to remove, reintroduced in a form that still matches
    a naive `git merge-base` check.
    """
    captures = [l for l in simplify.split("\n") if "git merge-base" in l]
    assert captures, "no merge-base diff capture found in pr-simplify.md"
    for line in captures:
        assert ".." not in line, (
            f"diff capture uses a commit range, not the one-ref form: {line.strip()!r}. "
            "`git diff A..B` misses uncommitted work; the contract is `git diff A`"
        )


def test_slop_detection_scope_also_widened() -> None:
    """Gap (coverage) — removing 2e's skip is useless if its diff stays empty.

    Step 2e inherits `$INLINE_DIFF` from Step 1. If Step 2e stops skipping on a
    clean tree but is still handed a working-tree diff, it runs on nothing — the
    gate reports clean for structural reasons rather than because the code is.
    """
    text = PR_SLOP.read_text()
    # Scope to Step 2e's own sections. Step 2d (above) legitimately uses both
    # `git merge-base` and the word "committed", so a whole-file search passes
    # vacuously against unimplemented code.
    start = text.find("## Inline slop detection")
    assert start != -1, "pr-slop-detection.md has no Step 2e inline section"
    step2e = text[start:]

    assert "git diff HEAD" not in step2e, (
        "Step 2e still gathers `git diff HEAD` — a working-tree diff. Removing its "
        "clean-tree skip without widening this makes it worse, not better: the gate "
        "runs on an empty diff and reports a clean pass for structural reasons"
    )
    assert re.search(r"merge.base", step2e, re.I), (
        "Step 2e's diff must span the branch change from the merge-base, matching "
        "Step 1. Step 2d already learned this the hard way — see 'Why this exists'"
    )


def test_no_leave_uncommitted_instruction() -> None:
    """Behavior 4 — the rule that existed only to feed Step 1's diff is gone."""
    offenders = []
    for path in SKILLS_DIR.rglob("*.md"):
        text = path.read_text()
        if re.search(r"UNCOMMITTED until|uncommitted\*\* until", text):
            offenders.append(str(path.relative_to(REPO_ROOT)))
    assert not offenders, (
        "these files still instruct the reader to leave implementation work "
        f"uncommitted until :pr: {offenders}. Once simplify scopes to the branch "
        "diff, committing as you go is fully supported and the rule only costs "
        "per-item commits that bisect and Step 2d's range checks rely on"
    )


def test_code_review_scope_documented() -> None:
    """Behavior 5 — record that review's PR-diff scope is deliberate, not a bug.

    NOT a bare `"working tree" in text` check: the phrase already appears seven
    times in this file describing `--fix` behaviour, so that assertion passes
    against unimplemented code.
    """
    text = PR_REVIEW.read_text()
    assert re.search(
        r"(deliberate|by design|independent of|unaffected by|not a bug)", text, re.I
    ), (
        "pr-claude-review.md must state that reviewing the PR/branch diff is "
        "deliberate and independent of working-tree state — otherwise the next "
        "reader 'fixes' it into false consistency with Steps 1 and 2e, which are "
        "the two that actually had the bug"
    )
    assert re.search(r"Step 1|Step 2e|simplify|slop", text, re.I), (
        "the note must name what it is distinguishing itself from, or it reads as "
        "an unmotivated aside"
    )
