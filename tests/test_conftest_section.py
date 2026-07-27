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


# ==========================================================================
# Step 0f — adversary gap tests
#
# The suite above covered ONE of four separator shapes and one of nine live
# collisions. Enumerated from the real corpus:
#
#   digit   merge/plan  "## Step 1"  also matches "## Step 10 …"
#   letter  pr          "## Step 2"  also matches "## Step 2d", "## Step 2e"
#           pr          "## Step 7"  also matches "## Step 7f"
#           plan        "## Step 3"  also matches "## Step 3a"
#           gh-init     "## Step 8"  also matches "## Step 8b"
#   dot     start       "### Step 3" also matches "### Step 3.5"
#
# The predicate must be **space-or-end-of-line**, not space-required: the pr
# spine has a bare `## Arguments` (nothing after it) and test_bill308:84 targets
# it, so requiring a trailing space breaks a live caller. Two more callers pass
# whole heading lines as targets.
#
# The weakest fix passing the five tests above rejects only a following digit,
# which leaves eight of the nine collisions broken. These close that.
# ==========================================================================

import re

import pytest

from conftest import SKILLS_DIR


def test_target_equal_to_the_whole_heading_matches():
    """A target that IS the entire heading line still matches.

    Live shape three times over: pr/SKILL.md:21 is a bare `## Arguments` with
    nothing after it, and test_bill328 passes whole heading lines lifted from the
    file. A space-required fix returns "" for all three — which is why the
    predicate is space-OR-END-OF-LINE.
    """
    text = "## Arguments\n\nargs body\n\n## Pre-flight\n\nflight body\n"
    found = section(text, "## Arguments")
    assert "args body" in found, "a full-heading target stopped matching"
    assert "flight body" not in found, "ran past the next heading"


@pytest.mark.parametrize(
    "collider,target,sep",
    [
        ("## Step 10 — Inline archive", "## Step 1", "digit"),
        ("## Step 2d — Red-test tamper gate", "## Step 2", "letter"),
        ("## Step 7f — Link the review back", "## Step 7", "letter"),
        ("## Step 8b — Seed scratch/", "## Step 8", "letter"),
        ("### Step 3.5 — Post attribution", "### Step 3", "dot"),
    ],
)
def test_only_whitespace_or_end_of_line_is_a_boundary(collider, target, sep):
    """Every separator shape that actually occurs in skills/**, one per case.

    RED today for all five. The digit case alone is what the original suite
    covered; a fix rejecting only digits passes it and leaves the rest broken.
    """
    assert section(f"{collider}\n\nwrong body\n", target) == "", (
        f"{target!r} matched {collider!r} across a {sep} separator"
    )


def test_wanted_heading_last_among_three_colliders():
    """A 3-way cluster with the target's own heading last in file order.

    pr/SKILL.md really has Step 2, 2d and 2e. Ordering-independence is the
    property that makes every currently-passing caller safe.
    """
    text = (
        "## Step 2d — Tamper gate\n\nbody 2d\n\n"
        "## Step 2e — Slop gate\n\nbody 2e\n\n"
        "## Step 2 — Run relevant tests\n\nbody 2\n"
    )
    found = section(text, "## Step 2")
    assert "body 2\n" in found or found.strip() == "body 2", "did not find Step 2"
    assert "body 2d" not in found and "body 2e" not in found, "matched a collider"


def test_target_metacharacters_are_literal():
    """A regex fix without re.escape turns '.' into a wildcard.

    `## 1c.` is a live target (test_bill134_behaviors.py). Headings containing
    parentheses are also passed whole, which would raise re.error unescaped.
    """
    text = "## 1cx Something else\n\nwrong\n\n## 1c. Map the code\n\nright\n"
    found = section(text, "## 1c.")
    assert "right" in found and "wrong" not in found, "'.' matched as a wildcard"
    assert section(
        "## Pre-flight (run in parallel)\n\nb\n", "## Pre-flight (run in parallel)"
    ).strip() == "b", "an unbalanced-paren target raised or failed to match"


def test_heading_only_inside_a_fence_is_not_found():
    """A heading that exists only inside a fenced template is not a section.

    The reference files exist to hold fenced markdown templates containing
    `## Definition of Done`. A fix that moves the match out of the fence-aware
    loop starts returning template bodies as sections, silently.
    """
    text = "intro\n\n```markdown\n## Definition of Done\ntemplate\n```\n\ntail\n"
    assert section(text, "## Definition of Done") == "", (
        "matched a heading inside a fenced template"
    )


@pytest.mark.parametrize(
    "text,target,why",
    [
        ("## A\n\nbody a\n", "## Zzz", "absent target"),
        ("prose only\nno headings\n", "## A", "no headings at all"),
        ("## A\n\nbody a\n", "", "empty target must not scoop up the first section"),
        ("## A\n\nbody a\n", "A", "a target with no '#' is not a heading"),
    ],
)
def test_degenerate_targets_return_empty(text, target, why):
    """"" is the documented contract for 'not found'.

    The empty-target case is RED today: it returns the first section's body,
    which is the same silent-wrong-section class this ticket exists to close.
    """
    assert section(text, target) == "", f"expected '' for {why}"


def test_depth_is_part_of_the_match():
    """`## Step 1` must not match `### Step 1`.

    pr's spine has `## Step 6` alongside `### Step 6-cr`, so the helper has to
    stay depth-discriminating while the match predicate is rewritten.
    """
    text = "### Step 1 — nested\n\ndeep body\n\n## Step 1 — real\n\nshallow body\n"
    found = section(text, "## Step 1")
    assert "shallow body" in found and "deep body" not in found


def test_the_heading_line_itself_is_excluded():
    """The implementation returns the body, not the heading.

    Its docstring says "text from `heading`", which reads as inclusive. Pin the
    behavior so a fixer reading the docstring literally does not change it.
    """
    found = section("## Step 1 — Resolve the PR\n\nbody one\n", "## Step 1")
    assert "Resolve the PR" not in found


def test_no_live_step_prefix_is_ambiguous_across_the_real_corpus():
    """The standing guard: fails when a new spine heading creates a collision.

    Synthetic tests cannot fail when someone adds `## Step 11` to a spine — which
    is how this bug arrived. This walks every real heading, derives the natural
    target (the heading truncated at its separator), and asserts that target
    resolves to its own body rather than a longer sibling's.
    """
    ambiguous = []
    for path in sorted(SKILLS_DIR.rglob("*.md")):
        lines = path.read_text().splitlines()
        headings = [l.rstrip() for l in lines if re.match(r"^#+ ", l)]
        for h in headings:
            target = re.split(r" [—:-] ", h)[0].rstrip()
            if target == h:
                continue
            for other in headings:
                if other == h:
                    continue
                tail = other[len(target):len(target) + 1]
                if other.startswith(target) and tail and not tail.isspace():
                    ambiguous.append(
                        f"{path.relative_to(SKILLS_DIR)}: {target!r} also matches "
                        f"{other[:40]!r}"
                    )
    assert not ambiguous, (
        "heading prefixes resolve ambiguously under the current predicate:\n  "
        + "\n  ".join(sorted(set(ambiguous)))
    )
