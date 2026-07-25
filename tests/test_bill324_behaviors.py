"""
Phase 0 red tests for BILL-324 — refactor the :merge spine to 150 lines.

Transcribed from the ticket's Test expectations
(https://github.com/iansmith/slopstop/issues/324). Same shape as BILL-322, which
took :plan from 349 to 145.

`skills/merge/SKILL.md` is 346 lines against a 350-line LINE_LIMIT, with 6
existing reference files — the pattern is established here, the spine just never
had its detail moved out.

Two lessons from BILL-322 are baked in rather than rediscovered:

- Step headings are matched **with a boundary**, not as bare substrings.
  CodeRabbit caught that `"Step 1" in spine` is satisfied by `## Step 10`, which
  made the equivalent :plan test vacuous for exactly the steps most likely to be
  lost.
- Section scoping uses `conftest.section()`, which is fence-aware. This file
  needs that more than :plan did: `merge/SKILL.md` contains `## Merged into
  $baseRefName` *inside* a fenced comment template, so a fence-blind extractor
  treats a template line as a section boundary.

These tests FAIL on current code and turn GREEN once the refactor lands.

Test command:
    python3 -m pytest tests/test_bill324_behaviors.py -v
"""

import re
from pathlib import Path

import pytest

from conftest import ref, section, spine as read_spine

REPO_ROOT = Path(__file__).parent.parent
MERGE_REFS = REPO_ROOT / "skills" / "merge" / "references"

TARGET_LINES = 150

POINTER_RE = re.compile(r"slopstop-([a-z-]+)-refs/([A-Za-z0-9._-]+\.md)")

# Multi-line output templates — needed only on the branch that emits them.
INLINE_TEMPLATES = {
    "Step 9 summary block": "Local:   $TRACKING_DIR/$TICKET/ untouched",
    "skip_archive commit-id comment": "## Merged into $baseRefName",
    # Added mid-ticket: /simplify found the first draft had DELETED this one rather
    # than relocating it — the spine paraphrased it ("plus the PR, Ticket and
    # soft-warning lines") and no reference carried the literal block, so the emitted
    # format would have been improvised from merge-autonomous.md's differently-prefixed
    # version. Exactly what the paired moved-out/still-exists tests are for; the
    # enumeration just didn't include it.
    "skip_confirm auto-confirm log": "[workflow.skip_confirm=true] Auto-confirming merge",
}

# Control flow and contract — a reader deciding WHICH path to take must not need
# a second file to find out.
SPINE_ANCHORS = {
    "strategy default is a real merge commit": "`merge` (real merge commit",
    "adopt mode exists and skips Step 4": "$ADOPT",
    "skip_confirm branch": "skip_confirm",
    "rules section": "## Rules",
    "autonomous trigger": "[autonomous] enabled = true",
    "merge-only path": "merge-only",
}

STEPS = [f"Step {n}" for n in range(1, 11)]


@pytest.fixture(scope="module")
def merge_spine():
    return read_spine("merge")


def test_spine_is_within_the_line_target(merge_spine):
    """Behavior 1 — 150 lines."""
    count = len(merge_spine.splitlines())
    assert count <= TARGET_LINES, (
        f"skills/merge/SKILL.md is {count} lines — must be <= {TARGET_LINES}. "
        "The 350-line LINE_LIMIT is a backstop, not the goal: this spine loads on "
        "every :merge invocation."
    )


def test_every_read_pointer_resolves(merge_spine):
    """Behavior 5 — a pointer to a nonexistent file is a dead end at runtime.

    The failure a relocation refactor most plausibly introduces: content moves to a
    new reference file and the pointer names it slightly differently, or the file is
    never created. Nothing in the repo checked this before BILL-322.
    """
    # Walk TRANSITIVELY from the spine. A spine-only check would miss the two files
    # this refactor demoted to second hop — merge-target-given.md (now reached only
    # from merge-pr-resolution.md) and merge-state-machines.md (only from
    # merge-ticket-system.md). Renaming either would leave every test green while
    # dead-ending the $TARGET_GIVEN path and all next-state computation at runtime.
    seen, queue, broken = set(), [merge_spine], []
    while queue:
        for skill, fn in POINTER_RE.findall(queue.pop()):
            key = (skill, fn)
            if key in seen:
                continue
            seen.add(key)
            target = REPO_ROOT / "skills" / skill / "references" / fn
            if not target.is_file():
                broken.append(f"slopstop-{skill}-refs/{fn}")
            else:
                queue.append(target.read_text())
    assert broken == [], (
        f"unresolvable → Read pointers reachable from skills/merge/SKILL.md: {broken}."
    )
    assert ("merge", "merge-state-machines.md") in seen, (
        "merge-state-machines.md must stay reachable from the spine — it owns the "
        "next-state algorithms and the terminal-state predicates"
    )
    assert ("merge", "merge-target-given.md") in seen, (
        "merge-target-given.md must stay reachable — it is the whole $TARGET_GIVEN path"
    )


def test_manifest_lists_every_reference():
    """Behavior 4 — a reference absent from manifest.txt is never installed."""
    manifest = MERGE_REFS / "manifest.txt"
    assert manifest.is_file(), "skills/merge/references/manifest.txt must exist"
    listed = {e.strip() for e in manifest.read_text().splitlines() if e.strip()}
    on_disk = {p.name for p in MERGE_REFS.glob("*.md")}
    assert on_disk - listed == set(), (
        f"reference files not listed in manifest.txt: {sorted(on_disk - listed)} — "
        "they will not be installed, so their pointers dangle for Desktop users"
    )
    assert listed - on_disk == set(), (
        f"manifest.txt lists files that do not exist: {sorted(listed - on_disk)}"
    )


@pytest.mark.parametrize("name,marker", sorted(INLINE_TEMPLATES.items()))
def test_inline_template_moved_out_of_spine(name, marker, merge_spine):
    """Behavior 3 — multi-line templates live in references."""
    assert marker not in merge_spine, (
        f"the {name} is still inline in skills/merge/SKILL.md (matched {marker!r})."
    )


@pytest.mark.parametrize("name,marker", sorted(INLINE_TEMPLATES.items()))
def test_inline_template_still_exists_somewhere(name, marker):
    """Behavior 2 — moved, not deleted. Opposed to the test above on purpose.

    Deleting a template satisfies "moved out of the spine" and fails this one.
    """
    homes = [p.name for p in MERGE_REFS.glob("*.md") if marker in p.read_text()]
    assert homes, (
        f"the {name} (matched {marker!r}) is in no skills/merge/references/ file. "
        "It must be relocated, not dropped."
    )


@pytest.mark.parametrize("name,marker", sorted(SPINE_ANCHORS.items()))
def test_control_flow_stays_in_the_spine(name, marker, merge_spine):
    """Behavior 6 — decisions stay inline; only their detail moves."""
    assert marker in merge_spine, (
        f"skills/merge/SKILL.md must keep {name} inline (expected {marker!r}) — "
        "control flow and contract are not relocatable detail"
    )


def test_every_step_is_still_reachable(merge_spine):
    """Behavior 2 + 7 — no step vanishes, matched with a heading boundary.

    NOT a bare substring check: `"Step 1" in spine` is satisfied by `## Step 10`.
    BILL-322 shipped that bug and CodeRabbit caught it; this file starts correct.
    """
    headings = [l.strip() for l in merge_spine.splitlines() if l.startswith("#")]
    missing = [
        s
        for s in STEPS
        if not any(re.search(rf"{re.escape(s)}(?![0-9A-Za-z])", h) for h in headings)
    ]
    assert missing == [], (
        f"these steps vanished from skills/merge/SKILL.md: {missing}. The refactor "
        "relocates detail; it does not remove steps."
    )


def test_adopt_mode_contract_survives(merge_spine):
    """Behavior 2 — adopt mode is the recovery path, and it is easy to bury.

    A PR merged outside `:merge` (web UI, bare `gh pr merge`) leaves the ticket open,
    the label applied, the tracking dir unarchived and no docs pushed. Adopt mode is
    the only documented recovery, and its load-bearing consequence is that Step 4
    must be SKIPPED — attempting a re-merge fails the run for no reason. A relocation
    that moves the "skip Step 4" instruction out of the spine leaves the spine
    describing a merge it must not perform.
    """
    assert "$ADOPT" in merge_spine, "the spine must still name $ADOPT"
    step4 = section(merge_spine, "## Step 4")
    assert step4, "skills/merge/SKILL.md must still carry a Step 4 section"
    low = step4.lower()
    assert "adopt" in low and "skip" in low, (
        "Step 4 must state that it is skipped in adopt mode — otherwise the spine "
        "instructs a re-merge of an already-merged PR"
    )


def test_closed_pr_is_refused_but_merged_pr_is_adopted(merge_spine):
    """Behavior 2 — the CLOSED/MERGED distinction is a correctness gate, not detail.

    Both are non-OPEN states, and collapsing them would either refuse a recoverable
    merged PR or advance a ticket whose work was abandoned. The spine must keep the
    distinction visible even after the gate list moves.
    """
    low = merge_spine.lower()
    assert "closed" in low and "adopt" in low, (
        "the spine must preserve the CLOSED-refuses / MERGED-adopts distinction"
    )


def test_archive_chain_condition_stays_in_the_spine(merge_spine):
    """Behavior 6 — whether Step 10 runs is a branch, and branches stay inline.

    Step 10 runs only for terminal post-merge states and never when skip_archive is
    true. That is the condition a session must evaluate to know whether to open the
    reference at all.
    """
    step10 = section(merge_spine, "## Step 10")
    assert step10, "skills/merge/SKILL.md must still carry a Step 10 section"
    low = step10.lower()
    assert "terminal" in low, "Step 10 must state it runs only for terminal states"
    assert "skip_archive" in low, (
        "Step 10 must state that skip_archive=true skips it entirely"
    )
