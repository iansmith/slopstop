"""
Phase 0 red tests for BILL-87 — integrate archive into merge + slopstop-update-ticket skill.

These tests describe the expected post-fix structure. They FAIL on the current
(un-changed) codebase and turn GREEN once the work is complete.

Test command:
    pytest tests/test_bill87_behaviors.py -v
"""

from pathlib import Path
import pytest

REPO_ROOT = Path(__file__).parent.parent
SKILLS_DIR = REPO_ROOT / "skills"


# ---------------------------------------------------------------------------
# 1. Standalone :archive — terminal-state gate must be removed
# ---------------------------------------------------------------------------

def test_archive_no_terminal_state_gate_step():
    """skills/archive/SKILL.md must not have a terminal-state gate step.

    BILL-87: the gate is obsolete once :merge chains archive automatically for
    terminal tickets.  Step 2 ("Terminal-state gate — refuse if not terminal")
    must be removed from the archive spine.
    """
    spine = (SKILLS_DIR / "archive" / "SKILL.md").read_text()
    assert "Terminal-state gate" not in spine, (
        "skills/archive/SKILL.md still has a 'Terminal-state gate' step — "
        "remove it per BILL-87 (standalone :archive must run regardless of ticket state)."
    )


def test_archive_no_terminal_refusal_in_rules():
    """skills/archive/SKILL.md Rules must not refuse on non-terminal tickets.

    BILL-87 spec: 'Refusing to run because the ticket isn't terminal defeats
    the purpose of keeping the standalone command.'
    """
    spine = (SKILLS_DIR / "archive" / "SKILL.md").read_text()
    assert "Refuses unless the ticket is" not in spine, (
        "skills/archive/SKILL.md Rules still says 'Refuses unless the ticket is *already* terminal' — "
        "remove this restriction per BILL-87."
    )


def test_archive_description_no_terminal_requirement():
    """skills/archive/SKILL.md description frontmatter must not require terminal state.

    The skill description (shown in /help listings) currently says
    'Use /slopstop:archive AFTER moving the ticket to a terminal state ... Refuses to run otherwise.'
    This must be updated to reflect the new unconditional behaviour.
    """
    spine = (SKILLS_DIR / "archive" / "SKILL.md").read_text()
    # The description key lives in the YAML frontmatter (first few lines)
    frontmatter_end = spine.find("---", 3)
    frontmatter = spine[:frontmatter_end] if frontmatter_end != -1 else spine[:200]
    assert "Refuses to run otherwise" not in frontmatter, (
        "skills/archive/SKILL.md frontmatter description still says 'Refuses to run otherwise' — "
        "update it to reflect that standalone :archive no longer requires terminal state."
    )


# ---------------------------------------------------------------------------
# 2. :merge must chain archive automatically for terminal tickets (non-autonomous)
# ---------------------------------------------------------------------------

def test_merge_spine_chains_archive_on_terminal():
    """skills/merge/SKILL.md Step 7 must not tell the user to 'Run /slopstop:archive' for terminal tickets.

    Before BILL-87, the Next-step recommendation block for branch A says:
        '✅ Ticket is now in '<new state>' — terminal. Run /slopstop:archive.'
    After BILL-87, that prompt must be gone because :merge auto-chains archive for
    terminal tickets — there is nothing left for the user to run.
    """
    spine = (SKILLS_DIR / "merge" / "SKILL.md").read_text()
    # The distinguishing marker: branch A recommendation telling the user to Run :archive.
    # After BILL-87 this prompt is removed; archive runs inline automatically.
    assert "terminal. Run /slopstop:archive" not in spine, (
        "skills/merge/SKILL.md still has a branch-A recommendation telling the user "
        "'Run /slopstop:archive' for terminal tickets — remove this per BILL-87 "
        "(auto-chain archive inline instead of prompting the user to run it manually)."
    )


def test_merge_spine_has_auto_archive_step():
    """skills/merge/SKILL.md must describe an inline archive-chain step for terminal tickets.

    BILL-87 spec: 'run the archive sequence inline' after a terminal-state merge.
    The spine must contain language about executing archive automatically, e.g.
    'archive sequence inline', 'archive step', or 'auto-archive'.
    """
    spine = (SKILLS_DIR / "merge" / "SKILL.md").read_text()
    # Check for any of the specific phrases the ticket spec uses:
    has_explicit_chain = any(phrase in spine for phrase in [
        "archive sequence inline",
        "archive step inline",
        "auto-archive",
        "archive inline",
    ])
    assert has_explicit_chain, (
        "skills/merge/SKILL.md does not describe running the archive sequence inline for "
        "terminal tickets — add a post-merge archive step (non-autonomous path) per BILL-87. "
        "Expected one of: 'archive sequence inline', 'archive step inline', 'auto-archive', "
        "'archive inline'."
    )


def test_merge_description_no_does_not_archive():
    """skills/merge/SKILL.md description must not say 'Does NOT archive'.

    The frontmatter description currently says 'Does NOT archive' — that was true
    before BILL-87.  After the fix, :merge DOES chain archive for terminal tickets,
    so this claim must be removed or updated.
    """
    spine = (SKILLS_DIR / "merge" / "SKILL.md").read_text()
    frontmatter_end = spine.find("---", 3)
    frontmatter = spine[:frontmatter_end] if frontmatter_end != -1 else spine[:200]
    assert "Does NOT archive" not in frontmatter, (
        "skills/merge/SKILL.md frontmatter description still says 'Does NOT archive' — "
        "update it to reflect that :merge now chains :archive for terminal tickets."
    )


# ---------------------------------------------------------------------------
# 3. New slopstop-update-ticket skill must exist
# ---------------------------------------------------------------------------

def test_update_ticket_skill_exists():
    """skills/update-ticket/SKILL.md must exist.

    BILL-87: a new 'slopstop-update-ticket' skill must be created that pushes
    the current tracking-file state to the ticket without archiving.
    """
    skill_path = SKILLS_DIR / "update-ticket" / "SKILL.md"
    assert skill_path.is_file(), (
        "skills/update-ticket/SKILL.md does not exist — "
        "create the slopstop-update-ticket skill per BILL-87."
    )


def test_update_ticket_runs_slopstop_update_first():
    """skills/update-ticket/SKILL.md must run slopstop-update (checkpoint) before pushing.

    BILL-87 spec: 'Run slopstop-update first (checkpoint progress.md, capture current state).'
    """
    skill_path = SKILLS_DIR / "update-ticket" / "SKILL.md"
    if not skill_path.is_file():
        pytest.skip("skills/update-ticket/SKILL.md absent — failing in test_update_ticket_skill_exists")
    text = skill_path.read_text()
    assert "slopstop:update" in text or "slopstop-update" in text, (
        "skills/update-ticket/SKILL.md does not reference running slopstop-update first — "
        "the skill must checkpoint progress.md before pushing to the ticket."
    )


def test_update_ticket_pushes_task_plan_as_description():
    """skills/update-ticket/SKILL.md must push task_plan.md as the ticket description.

    BILL-87 spec: 'Push task_plan.md as the ticket description body
    (same logic as :document — divergence detection, ## Original description appendix).'
    """
    skill_path = SKILLS_DIR / "update-ticket" / "SKILL.md"
    if not skill_path.is_file():
        pytest.skip("skills/update-ticket/SKILL.md absent — failing in test_update_ticket_skill_exists")
    text = skill_path.read_text()
    assert "task_plan" in text or "task_plan.md" in text, (
        "skills/update-ticket/SKILL.md does not mention pushing task_plan.md — "
        "the skill must push the current task plan as the ticket description."
    )


def test_update_ticket_is_idempotent():
    """skills/update-ticket/SKILL.md must describe idempotent behaviour.

    BILL-87 acceptance: 'slopstop-update-ticket is idempotent: running it twice
    in a row with no changes is a no-op.'
    """
    skill_path = SKILLS_DIR / "update-ticket" / "SKILL.md"
    if not skill_path.is_file():
        pytest.skip("skills/update-ticket/SKILL.md absent — failing in test_update_ticket_skill_exists")
    text = skill_path.read_text()
    assert "idempotent" in text, (
        "skills/update-ticket/SKILL.md does not mention idempotency — "
        "the skill must document that running it twice with no changes is a no-op."
    )
