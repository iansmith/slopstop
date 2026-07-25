"""
Phase 0 red tests for BILL-325 — refactor the :pr spine to 150 lines.

Transcribed from the ticket's Test expectations
(https://github.com/iansmith/slopstop/issues/325). Third in the series after
BILL-322 (:plan, 349 → 145) and BILL-324 (:merge, 346 → 127).

`skills/pr/SKILL.md` is 339 lines with 10 existing reference files.

Every lesson the two prior refactors paid for is baked in here rather than
rediscovered:

- Step headings matched **with a boundary**, not as bare substrings (CodeRabbit
  caught that `"Step 1" in spine` is satisfied by `## Step 10`).
- Pointer resolution walks **transitively** via `conftest.reachable_references`
  (BILL-324 demoted two files to second hop, where a spine-only check is blind).
- Section scoping via fence-aware `conftest.section`.
- `INLINE_TEMPLATES` enumerates **every** multi-line template up front. BILL-324's
  first draft *deleted* one rather than relocating it, and the paired
  moved-out/still-exists guards missed it purely because the enumeration was
  incomplete.

`:pr` carries one contract the other two don't, and it is the whole reason this
skill is load-bearing: **Step 2d, the red-test tamper gate, is skippable by no
flag.** Its own text explains why — the fleet agent composes its own `:pr`
invocation, so any flag-keyed skip is a switch the policed party controls. A
relocation that moves that reasoning out of the spine hands an agent a gate it can
argue its way past.

These tests FAIL on current code and turn GREEN once the refactor lands.

Test command:
    python3 -m pytest tests/test_bill325_behaviors.py -v
"""

import re
from pathlib import Path

import pytest

from conftest import reachable_references, section, spine as read_spine

REPO_ROOT = Path(__file__).parent.parent
PR_REFS = REPO_ROOT / "skills" / "pr" / "references"

TARGET_LINES = 150

INLINE_TEMPLATES = {
    "Step 7f ticket link-back body": "## PR review — $PR_BACKEND",
    "Step 8 confirmation summary": "Slop gate:",
}

SPINE_ANCHORS = {
    "rules section": "## Rules",
    "autonomous trigger": "[autonomous] enabled = true",
    "--inline forces the claude backend": "--inline",
    "Step 6 dispatches on the resolved backend": "$PR_BACKEND",
    "Step 2d is skippable by no flag": "No flag skips",
}

# Steps in dispatch order. 2d and 2e are gates with their own skip semantics, and
# 6-cr / 6-greptile / 6-claude are the three backend branches.
STEPS = [
    "Step 0", "Step 1", "Step 2", "Step 2d", "Step 2e", "Step 3", "Step 4",
    "Step 5", "Step 6", "Step 6-cr", "Step 6-greptile", "Step 6-claude",
    "Step 7", "Step 7f", "Step 8",
]


@pytest.fixture(scope="module")
def pr_spine():
    return read_spine("pr")


def test_spine_is_within_the_line_target(pr_spine):
    """Behavior 1 — 150 lines."""
    count = len(pr_spine.splitlines())
    assert count <= TARGET_LINES, (
        f"skills/pr/SKILL.md is {count} lines — must be <= {TARGET_LINES}. "
        "The 350-line LINE_LIMIT is a backstop, not the goal: this spine loads on "
        "every :pr invocation."
    )


def test_every_read_pointer_resolves_transitively():
    """Behavior 5 — including second-hop references.

    Uses the shared transitive walk. A spine-only check would miss any reference
    this refactor demotes to second hop, exactly as happened in :merge.
    """
    reached, broken = reachable_references("pr")
    assert broken == [], (
        f"unresolvable → Read pointers reachable from skills/pr/SKILL.md: {broken}."
    )
    # The three review backends must each stay reachable — losing one silently
    # disables a configured [pr_review] backend.
    for required in ("pr-cr-polling.md", "pr-greptile-polling.md", "pr-claude-review.md"):
        assert ("pr", required) in reached, (
            f"{required} must stay reachable from the :pr spine — it is a configured "
            "[pr_review] backend, and an unreachable one silently never runs"
        )
    assert ("pr", "pr-slop-detection.md") in reached, (
        "pr-slop-detection.md must stay reachable — it owns both Step 2d's tamper "
        "diff and Step 2e's slop catalog"
    )


def test_manifest_lists_every_reference():
    """Behavior 4 — a reference absent from manifest.txt is never installed."""
    manifest = PR_REFS / "manifest.txt"
    assert manifest.is_file(), "skills/pr/references/manifest.txt must exist"
    listed = {e.strip() for e in manifest.read_text().splitlines() if e.strip()}
    on_disk = {p.name for p in PR_REFS.glob("*.md")}
    assert on_disk - listed == set(), (
        f"reference files not listed in manifest.txt: {sorted(on_disk - listed)} — "
        "they will not be installed, so their pointers dangle for Desktop users"
    )
    assert listed - on_disk == set(), (
        f"manifest.txt lists files that do not exist: {sorted(listed - on_disk)}"
    )


@pytest.mark.parametrize("name,marker", sorted(INLINE_TEMPLATES.items()))
def test_inline_template_moved_out_of_spine(name, marker, pr_spine):
    """Behavior 3 — multi-line templates live in references."""
    assert marker not in pr_spine, (
        f"the {name} is still inline in skills/pr/SKILL.md (matched {marker!r})."
    )


@pytest.mark.parametrize("name,marker", sorted(INLINE_TEMPLATES.items()))
def test_inline_template_still_exists_somewhere(name, marker):
    """Behavior 2 — moved, not deleted. Opposed to the test above on purpose."""
    homes = [p.name for p in PR_REFS.glob("*.md") if marker in p.read_text()]
    assert homes, (
        f"the {name} (matched {marker!r}) is in no skills/pr/references/ file. "
        "It must be relocated, not dropped. BILL-324's first draft deleted a "
        "template exactly this way."
    )


@pytest.mark.parametrize("name,marker", sorted(SPINE_ANCHORS.items()))
def test_control_flow_stays_in_the_spine(name, marker, pr_spine):
    """Behavior 6 — decisions stay inline; only their detail moves."""
    assert marker in pr_spine, (
        f"skills/pr/SKILL.md must keep {name} inline (expected {marker!r})."
    )


def test_every_step_is_still_reachable(pr_spine):
    """Behavior 2 + 7 — no step vanishes, matched with a heading boundary."""
    headings = [l.strip() for l in pr_spine.splitlines() if l.startswith("#")]
    missing = [
        s
        for s in STEPS
        if not any(re.search(rf"{re.escape(s)}(?![0-9A-Za-z-])", h) for h in headings)
    ]
    assert missing == [], (
        f"these steps vanished from skills/pr/SKILL.md: {missing}."
    )


def test_step2d_remains_unskippable_in_the_spine(pr_spine):
    """Behavior 6 — the tamper gate's skip semantics are the point of the gate.

    Step 2d runs on `git log` + `git diff`: no tests, no latency, no dependency on
    the suite. It skips on exactly one condition, and that condition is a recorded
    fact (`:plan` never established a baseline), not an agent-supplied argument.

    This must stay in the spine because the fleet agent composes its own `:pr`
    invocation. Any flag-keyed skip is a switch the *policed party* controls — an
    agent could disable its own tamper gate with `--no-test`, a flag that nominally
    just means "don't run the suite". Move this reasoning into a reference and the
    agent's incentive to not open that reference is exactly aligned against it.
    """
    step2d = section(pr_spine, "## Step 2d")
    assert step2d, "skills/pr/SKILL.md must still carry a Step 2d section"
    low = step2d.lower()
    assert "no flag skips" in low, (
        "Step 2d must state in the spine that NO flag skips it"
    )
    assert "--no-test" in step2d and "--no-adversary" in step2d, (
        "Step 2d must name the specific flags that do NOT skip it — a general claim "
        "invites an agent to assume its particular flag is the exception"
    )
    assert "on_slop_findings" in step2d, (
        "Step 2d must state that on_slop_findings does not govern it either — that "
        "knob defaults to 'skip' for fleet agents, so sharing it would disable this "
        "gate for exactly the agents it exists to police"
    )
    assert "clean" in low and "tree" in low, (
        "Step 2d must keep the do-NOT-skip-on-a-clean-tree rule: tampering is "
        "committed work presenting a clean tree, so a clean tree is precisely when "
        "the gate must still run"
    )


def test_interactive_review_dispatch_survives(pr_spine):
    """BILL-308's contract — all three backends still route, and --inline overrides.

    Guards against a relocation that collapses the dispatch table into a pointer.
    Interactive `:pr` must keep honoring [pr_review] backend.
    """
    for backend in ("coderabbit", "greptile", "claude"):
        assert f'`"{backend}"`' in pr_spine, (
            f"Step 6's dispatch must still route the {backend} backend"
        )
    assert "interactive-only" in pr_spine.lower(), (
        "the spine must keep stating that the bot backends are interactive-only — "
        "that is why --inline forces claude (BILL-308)"
    )
