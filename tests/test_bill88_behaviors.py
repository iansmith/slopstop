"""
Phase 0 red tests for BILL-88 — adversary agents for :plan (red test gaps)
and :pr (slop detection).

These tests describe the expected post-fix structure. They FAIL on the current
(un-changed) codebase and turn GREEN once the work is complete.

Test command:
    pytest tests/test_bill88_behaviors.py -v
"""

from pathlib import Path
import pytest

REPO_ROOT = Path(__file__).parent.parent
SKILLS_DIR = REPO_ROOT / "skills"


def _skill_text(*parts):
    """Return all text in a skill directory: SKILL.md + all reference .md files."""
    base = SKILLS_DIR.joinpath(*parts)
    texts = []
    skill_md = base / "SKILL.md"
    if skill_md.exists():
        texts.append(skill_md.read_text())
    refs = base / "references"
    if refs.is_dir():
        for f in sorted(refs.glob("*.md")):
            texts.append(f.read_text())
    return "\n".join(texts)


# ---------------------------------------------------------------------------
# 1. :plan — adversary agent (red test gap finder)
# ---------------------------------------------------------------------------

def test_plan_has_adversary_after_red_tests():
    """skills/plan must introduce an adversary agent after Step 0c (red tests written).

    BILL-88: after writing red tests, an adversary agent attacks the test suite
    for gaps (boundary omissions, error path gaps, false negatives, etc.).
    The spine or a reference file must mention 'adversary' in the context of
    Phase 0 / red test gap finding.
    """
    text = _skill_text("plan")
    assert "adversary" in text.lower(), (
        "skills/plan/ has no mention of an adversary agent — "
        "BILL-88 requires a gap-finder adversary after Step 0c."
    )


def test_plan_adversary_presents_add_skip_options():
    """skills/plan must offer add all / add selected / skip for adversary gap findings.

    BILL-88 spec: 'The orchestrator presents the findings and asks:
    add all / add selected / skip.'
    """
    text = _skill_text("plan")
    assert "add all" in text.lower() or "add selected" in text.lower(), (
        "skills/plan/ doesn't have 'add all / add selected / skip' options — "
        "required by BILL-88 for adversary gap findings."
    )


def test_plan_adversary_red_verifies_added_tests():
    """skills/plan must require adversary-added tests to be verified RED before proceeding.

    BILL-88 spec: 'Added tests must also fail on current code (same RED-state
    verification as Step 0d).' — this must appear in adversary context, not just
    the general Phase 0 intro text.
    """
    text = _skill_text("plan")
    lower = text.lower()
    # Must be adversary-specific — the general "fail on current code" from Phase 0 intro
    # doesn't count. Look for the adversary cross-referencing RED verification.
    has_red_verify = (
        ("adversary" in lower and "red" in lower and "fail" in lower)
        or "red-state verification" in lower
        or ("adversary" in lower and "same red" in lower)
        or ("gap" in lower and "verified red" in lower)
        or ("gap finding" in lower and "fail" in lower)
    )
    assert has_red_verify, (
        "skills/plan/ doesn't specify that adversary-added tests must be verified RED — "
        "required by BILL-88 (need adversary + RED verification in same context)."
    )


# ---------------------------------------------------------------------------
# 2. :pr — slop-detection pre-commit gate
# ---------------------------------------------------------------------------

def test_pr_has_slop_detector():
    """skills/pr must include a slop-detection step before the commit step.

    BILL-88: before committing, a slop-detection agent hunts for AI-specific
    cheating patterns (test rewriting, expectation inversion, etc.).
    Must be 'slop detector' / 'slop detection' / 'slop pattern' — not just
    the 'slopstop' prefix on every reference path.
    """
    text = _skill_text("pr")
    lower = text.lower()
    has_slop_detector = (
        "slop detector" in lower
        or "slop detection" in lower
        or "slop pattern" in lower
        or "slop-detection" in lower
    )
    assert has_slop_detector, (
        "skills/pr/ has no slop detector — "
        "BILL-88 requires a pre-commit slop-detection gate."
    )


def test_pr_slop_red_findings_hard_stop():
    """skills/pr must hard-stop on 🔴 slop findings without explicit override.

    BILL-88 spec: '🔴 findings: hard stop — requires explicit override from
    user with a reason recorded in pipeline.json.' — must be in slop detector
    context, not the existing CC gate or test-failure gate.
    """
    text = _skill_text("pr")
    lower = text.lower()
    # Must combine slop-specific language (not just "slopstop") with hard-stop/override.
    # "slop detector" / "slop detection" / "slop-detection" won't match "slopstop:pr".
    has_slop_stop = (
        ("slop detector" in lower and ("hard stop" in lower or "override" in lower))
        or ("slop detection" in lower and ("hard stop" in lower or "override" in lower))
        or ("slop-detection" in lower and "override" in lower)
        or ("slop pattern" in lower and "override" in lower)
    )
    assert has_slop_stop, (
        "skills/pr/ doesn't mention hard stop + override for 🔴 slop findings — "
        "required by BILL-88 (need slop + hard stop/override in same context)."
    )


def test_pr_slop_override_recorded_in_pipeline_json():
    """skills/pr must record slop override reasons in pipeline.json.

    BILL-88 spec: 'requires explicit override from user with a reason recorded
    in pipeline.json.' — pipeline.json already exists for CC gate; need to
    verify it's referenced in slop-detector context specifically.
    """
    text = _skill_text("pr")
    lower = text.lower()
    # pipeline.json already exists in pr for CC gate — need slop-specific context
    has_slop_pipeline = (
        ("slop" in lower and "pipeline.json" in text)
        and (
            "slop detector" in lower
            or "slop detection" in lower
            or "slop-detection" in lower
            or "slop pattern" in lower
        )
    )
    assert has_slop_pipeline, (
        "skills/pr/ doesn't reference pipeline.json in slop-detector context — "
        "required by BILL-88 (slop override reason must be recorded there)."
    )


# ---------------------------------------------------------------------------
# 3. --no-adversary flag (both skills)
# ---------------------------------------------------------------------------

def test_plan_no_adversary_flag():
    """skills/plan must support --no-adversary to skip adversary for speed runs.

    BILL-88 spec: 'Both adversaries are skippable via --no-adversary flag
    for speed runs.'
    """
    text = _skill_text("plan")
    assert "--no-adversary" in text, (
        "skills/plan/ doesn't mention --no-adversary flag — "
        "required by BILL-88 for speed runs."
    )


def test_pr_no_adversary_flag():
    """skills/pr must support --no-adversary to skip slop detector for speed runs.

    BILL-88 spec: 'Both adversaries are skippable via --no-adversary flag
    for speed runs.'
    """
    text = _skill_text("pr")
    assert "--no-adversary" in text, (
        "skills/pr/ doesn't mention --no-adversary flag — "
        "required by BILL-88 for speed runs."
    )


# ---------------------------------------------------------------------------
# 4. Autonomous mode config keys
# ---------------------------------------------------------------------------

def test_plan_autonomous_on_test_gaps():
    """skills/plan autonomous section must handle [autonomous] on_test_gaps.

    BILL-88 spec: 'Autonomous mode: adversary behavior configurable via
    [autonomous] on_test_gaps.'
    """
    text = _skill_text("plan")
    assert "on_test_gaps" in text, (
        "skills/plan/ autonomous section doesn't mention on_test_gaps — "
        "required by BILL-88."
    )


def test_pr_autonomous_on_slop_findings():
    """skills/pr autonomous section must handle [autonomous] on_slop_findings.

    BILL-88 spec: 'Autonomous mode: adversary behavior configurable via
    [autonomous] on_slop_findings.'
    """
    text = _skill_text("pr")
    assert "on_slop_findings" in text, (
        "skills/pr/ autonomous section doesn't mention on_slop_findings — "
        "required by BILL-88."
    )
