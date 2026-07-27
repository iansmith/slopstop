"""
Phase 0 red tests for BILL-330 — `conftest.section()` prefix-matches headings.

Transcribed from the ticket's Test expectations
(https://github.com/iansmith/slopstop/issues/330).

`section()` matches with `line.strip().startswith(target)` (conftest.py:58), so
`"## Step 1"` prefix-matches `## Step 10 — Inline archive`. The helper has 15
callers, and three spines carry ten or more step headings — `merge` (10), `pr`
(12), `plan` (12) — so `"## Step 1"` is ambiguous in all three. Those tests pass
today only because `## Step 1` happens to precede `## Step 10` in file order.
Reorder or delete Step 1 and they silently re-scope to Step 10 and keep passing,
asserting against the wrong section.

Found by the Step 0f adversary during BILL-328, whose
`test_merge_spine_has_dod_gate` docstring claims boundary matching the helper
does not provide. That docstring becomes true when this lands.

The helper had no tests of its own. The last two below transcribe the two
properties its docstring already claims, so the fix cannot quietly break them.

Test command:
    python3 -m pytest tests/test_conftest_section.py -v
"""

from conftest import section

# A heading whose prefix collides with the one we ask for. The collision is the
# bug: "## Step 1" is a string-prefix of "## Step 10".
STEP_10_ONLY = """## Step 10 — Inline archive

body ten

## Rules

rules body
"""

BOTH_STEP_10_FIRST = """## Step 10 — Inline archive

body ten

## Step 1 — Resolve the PR

body one
"""


def test_step_1_does_not_match_step_10():
    """Asking for a heading that is absent returns "", not a prefix collision.

    RED today: returns Step 10's body, so a caller scoping to Step 1 in a spine
    that has a Step 10 silently asserts against the wrong section.
    """
    assert section(STEP_10_ONLY, "## Step 1") == "", (
        "'## Step 1' matched '## Step 10 — Inline archive' by string prefix"
    )


def test_step_1_found_when_step_10_precedes_it():
    """The right heading wins regardless of file order.

    RED today: `section()` breaks on the first prefix match, so Step 10 wins
    purely by appearing first. Every currently-passing caller depends on the
    opposite ordering holding by luck.
    """
    found = section(BOTH_STEP_10_FIRST, "## Step 1")
    assert "body one" in found, "did not find Step 1's body"
    assert "body ten" not in found, "returned Step 10's body instead of Step 1's"


def test_exact_heading_still_matches():
    """A heading prefix followed by a separator still matches.

    Paired guard, green before and after. Its job is to fail if the fix
    over-tightens into requiring the full heading string — callers pass
    `"## Step 1"` for `## Step 1 — Resolve the PR` on purpose.
    """
    text = "## Step 1 — Resolve the PR\n\nbody one\n\n## Step 2 — Next\n\nbody two\n"
    found = section(text, "## Step 1")
    assert "body one" in found, "the exact-prefix-plus-separator form stopped matching"
    assert "body two" not in found, "section ran past its own boundary"


def test_fenced_headings_are_not_boundaries():
    """A `##` inside a fence is content, not a section boundary.

    Transcribes a property `section()`'s docstring already claims. Green today;
    pins behavior the fix must not break, since the reference files exist
    precisely to hold fenced templates.
    """
    text = (
        "## Step 1 — Resolve the PR\n\n"
        "```markdown\n"
        "## Definition of Done\n"
        "template body\n"
        "```\n\n"
        "after the fence\n\n"
        "## Step 2 — Next\n\nbody two\n"
    )
    found = section(text, "## Step 1")
    assert "template body" in found, "the fenced heading truncated the section"
    assert "after the fence" in found, "section ended at a heading inside a fence"
    assert "body two" not in found, "section ran past the real next heading"


def test_depth_aware_termination():
    """A subsection ends at the next same-or-shallower heading, not at a nested one.

    The other property the docstring claims. `## 2a.` must survive a `###` nested
    under it and stop at the following `##`.
    """
    text = (
        "## 2a. Draft the DoD\n\n"
        "outer body\n\n"
        "### 2a-i. A nested detail\n\n"
        "nested body\n\n"
        "## 2b. Next subsection\n\nsibling body\n"
    )
    found = section(text, "## 2a.")
    assert "outer body" in found, "lost the section's own body"
    assert "nested body" in found, "terminated at a deeper heading"
    assert "sibling body" not in found, "ran past the next same-depth heading"
