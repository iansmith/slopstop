"""
Phase 0 red tests for BILL-322 — refactor the :plan spine to 150 lines.

Transcribed from the ticket's Test expectations
(https://github.com/iansmith/slopstop/issues/322). Structural assertions over
skill text, matching the test_skill_structure.py convention.

BILL-310 pushed skills/plan/SKILL.md to 349 lines against LINE_LIMIT = 350, so
the next edit of any kind fails the suite and the spine is effectively frozen.
The target is 150, not "under the limit": the spine is read into context on every
`/slopstop:plan` invocation while references are read only on the branch that
needs them, and a 349-line spine has already lost the property that split exists
for.

This is a pure relocation. The risk it carries is *losing* something — a step, a
decision criterion, or a pointer whose target was never created — so most of the
tests below check that nothing went missing rather than that the file got smaller.

These tests FAIL on current code and turn GREEN once the refactor lands.

Test command:
    python3 -m pytest tests/test_bill322_behaviors.py -v
"""

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent
PLAN_SPINE = REPO_ROOT / "skills" / "plan" / "SKILL.md"
PLAN_REFS = REPO_ROOT / "skills" / "plan" / "references"

TARGET_LINES = 150

# Pointer form used throughout the repo, e.g.
#   → Read `~/.claude/commands/slopstop-plan-refs/plan-red-tests.md`
POINTER_RE = re.compile(r"slopstop-([a-z-]+)-refs/([A-Za-z0-9._-]+\.md)")

# The three multi-line markdown templates the ticket names (behavior 3), keyed on
# a line that only appears inside each.
INLINE_TEMPLATES = {
    "findings.md Investigation block": "### Constraints to honor",
    "Definition of Done block": "This ticket will be considered complete when ALL",
    "Plan / work-items block": "- **Parallel-safe with:**",
}

# Control flow and contract — behavior 6. A reader deciding WHICH path to take
# must not have to open a second file to find out.
SPINE_ANCHORS = {
    "profile selection": "## Profile selection",
    "serial-vs-parallel decision": "## Step 3 — Decide",
    "rules section": "## Rules",
    "autonomous trigger": "[autonomous] enabled = true",
}


@pytest.fixture(scope="module")
def spine():
    return PLAN_SPINE.read_text()


def test_spine_is_within_the_line_target(spine):
    """Behavior 1 — 150 lines, the ticket's actual target."""
    count = len(spine.splitlines())
    assert count <= TARGET_LINES, (
        f"skills/plan/SKILL.md is {count} lines — must be <= {TARGET_LINES}. "
        "The 350-line LINE_LIMIT is a backstop, not the goal: this spine loads on "
        "every :plan invocation."
    )


def test_every_read_pointer_resolves(spine):
    """Behavior 5 — a pointer to a file that doesn't exist is a dead end at runtime.

    Nothing in the repo resolves `→ Read` targets today, and this is the failure a
    relocation refactor most plausibly introduces: content moves to a new reference
    file, and the pointer names it slightly differently or the file is never created.
    Cross-skill pointers are resolved against that skill's own references/ dir.
    """
    broken = []
    for skill, filename in POINTER_RE.findall(spine):
        target = REPO_ROOT / "skills" / skill / "references" / filename
        if not target.is_file():
            broken.append(f"slopstop-{skill}-refs/{filename}")
    assert broken == [], (
        f"skills/plan/SKILL.md points at reference files that do not exist: {broken}. "
        "Every → Read target must resolve to skills/<skill>/references/<file>."
    )


def test_manifest_lists_every_reference(spine):
    """Behavior 4 — a reference absent from manifest.txt is never installed.

    The Desktop installer fetches each skill's manifest and installs only what it
    lists, so a new reference file that isn't listed leaves its pointer dangling for
    every Desktop user even though the repo test suite passes.
    """
    manifest = PLAN_REFS / "manifest.txt"
    assert manifest.is_file(), "skills/plan/references/manifest.txt must exist"
    listed = {entry.strip() for entry in manifest.read_text().splitlines() if entry.strip()}
    on_disk = {p.name for p in PLAN_REFS.glob("*.md")}
    assert on_disk - listed == set(), (
        f"reference files not listed in manifest.txt: {sorted(on_disk - listed)} — "
        "they will not be installed"
    )
    assert listed - on_disk == set(), (
        f"manifest.txt lists files that do not exist: {sorted(listed - on_disk)}"
    )


@pytest.mark.parametrize("name,marker", sorted(INLINE_TEMPLATES.items()))
def test_inline_template_moved_out_of_spine(name, marker, spine):
    """Behavior 3 — the three multi-line templates live in references, not the spine."""
    assert marker not in spine, (
        f"the {name} is still inline in skills/plan/SKILL.md (matched {marker!r}). "
        "Multi-line output templates are exactly what references/ is for — they are "
        "needed only on the branch that emits them."
    )


@pytest.mark.parametrize("name,marker", sorted(INLINE_TEMPLATES.items()))
def test_inline_template_still_exists_somewhere(name, marker):
    """Behavior 2 — moved, not deleted. A relocation that loses a template is a regression."""
    homes = [p.name for p in PLAN_REFS.glob("*.md") if marker in p.read_text()]
    assert homes, (
        f"the {name} (matched {marker!r}) is in no skills/plan/references/ file. "
        "It must be relocated, not dropped."
    )


@pytest.mark.parametrize("name,marker", sorted(SPINE_ANCHORS.items()))
def test_control_flow_stays_in_the_spine(name, marker, spine):
    """Behavior 6 — decisions stay inline; only their detail moves.

    A spine that delegates its own branching is worse than a long one: the reader
    has to open a file to learn which file to open.
    """
    assert marker in spine, (
        f"skills/plan/SKILL.md must keep {name} inline (expected {marker!r}) — "
        "control flow and contract are not relocatable detail"
    )


def test_every_step_is_still_reachable(spine):
    """Behavior 2 — no step silently disappears in the shuffle.

    Steps 0 through 10 plus the named sub-steps that carry their own gates. Matched
    against actual heading lines with a trailing boundary, NOT as bare substrings of
    the whole file — CodeRabbit caught that the substring form was vacuous for
    exactly the two steps most likely to be lost: `"Step 1" in spine` is satisfied by
    `## Step 10`, and `"Step 3"` by `## Step 3a`. Verified by mutation: deleting the
    `## Step 1 — Investigation` heading left the substring version reporting nothing
    missing. A test whose whole job is "no step vanished" must not be satisfiable by
    a different step's heading.
    """
    headings = [l.strip() for l in spine.splitlines() if l.startswith("#")]
    missing = []
    for step in ("Step 0", "Step 1", "Step 2", "Step 3", "Step 3a", "Step 4",
                 "Step 5", "Step 6", "Step 7", "Step 8", "Step 9", "Step 10"):
        # A heading "owns" the step only if the step name is followed by a
        # non-alphanumeric boundary (" — ", " ", or end of line).
        if not any(re.search(rf"{re.escape(step)}(?![0-9A-Za-z])", h) for h in headings):
            missing.append(step)
    assert missing == [], (
        f"these steps vanished from skills/plan/SKILL.md: {missing}. The refactor "
        "relocates detail; it does not remove steps."
    )


def test_phase0_freeze_contract_survives(spine):
    """Behavior 2 — the load-bearing Phase 0 invariants stay findable from the spine.

    These are the ones a relocation is most tempting to bury, and burying them is
    expensive: :pr Step 2d and :run's tamper check both read the Phase 0 commit as
    their baseline, so a session that never learns the freeze rule produces a
    baseline those gates then reject.
    """
    low = spine.lower()
    assert "phase 0" in low, "the spine must still name Phase 0"
    # Assert the RELATIONSHIP, not that the words appear somewhere. CodeRabbit's
    # point: "freeze" anywhere in a 145-line file says nothing about whether the
    # spine states that *the commit* freezes *the tests*.
    assert "freezes the tests" in low, (
        "the spine must state that the Phase 0 commit FREEZES THE TESTS, not merely "
        "mention freezing — :pr Step 2d and :run's tamper check both key on that commit"
    )
    assert "underspecified` halt" in low or "underspecified halt" in low, (
        "the spine must name TICKET UNDERSPECIFIED as a *halt* — it is the only "
        "sanctioned alternative to editing a red test's expected value, and naming it "
        "without saying it halts invites treating it as advice"
    )
