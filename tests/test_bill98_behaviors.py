"""
Phase 0 red tests for BILL-98 — :merge must call :update + :document (always);
:archive reduced to file-move lifecycle only.

These tests describe the expected post-fix structure. They FAIL on the current
(un-changed) codebase and turn GREEN once the work is complete.

Test command:
    python3 -m pytest tests/test_bill98_behaviors.py -v
"""

from pathlib import Path
import pytest

REPO_ROOT = Path(__file__).parent.parent
SKILLS_DIR = REPO_ROOT / "skills"


# ---------------------------------------------------------------------------
# 1. :merge must have an :update step (Step 6 — Update tracking files)
# ---------------------------------------------------------------------------

def test_merge_has_update_tracking_step():
    """skills/merge/SKILL.md must describe an Update-tracking-files step.

    BILL-98: :merge must invoke :update as a named step between state-advance
    and :document. The old passive reference ('user can capture notes via
    /slopstop:update if they want') is not sufficient — an active invocation
    step must be present.
    """
    spine = (SKILLS_DIR / "merge" / "SKILL.md").read_text()
    has_update_step = any(phrase in spine for phrase in [
        "Update tracking files",
        "/slopstop:update inline",
        "Invoke /slopstop:update",
        "invoke /slopstop:update",
    ])
    assert has_update_step, (
        "skills/merge/SKILL.md does not describe an active :update step — "
        "add a step (e.g. 'Step 6 — Update tracking files') that explicitly invokes "
        ":update before pushing docs. Expected one of: 'Update tracking files', "
        "'/slopstop:update inline', 'Invoke /slopstop:update'."
    )


def test_merge_no_progress_not_written_note():
    """skills/merge/SKILL.md must NOT say 'intentionally NOT written'.

    BILL-98: after the fix :merge calls :update (which writes progress.md),
    so the old note claiming progress.md is intentionally untouched must be removed.
    """
    spine = (SKILLS_DIR / "merge" / "SKILL.md").read_text()
    assert "intentionally NOT written" not in spine, (
        "skills/merge/SKILL.md still says 'progress.md is intentionally NOT written to' — "
        "remove this note per BILL-98 (:update now runs as part of :merge)."
    )


# ---------------------------------------------------------------------------
# 2. :merge must have a direct :document step (not only via :archive)
# ---------------------------------------------------------------------------

def test_merge_has_document_step():
    """skills/merge/SKILL.md must invoke /slopstop:document directly.

    BILL-98: docs must be pushed for EVERY ticket (terminal or not) immediately
    after merge. Today docs only reach the ticket via the :archive chain (terminal
    tickets only). After BILL-98, :merge must call :document as its own step.
    """
    spine = (SKILLS_DIR / "merge" / "SKILL.md").read_text()
    assert "/slopstop:document" in spine or "slopstop:document" in spine, (
        "skills/merge/SKILL.md does not invoke /slopstop:document — "
        "add a step (e.g. 'Step 7 — Push docs to ticket') that directly calls "
        ":document after the ticket state is advanced. Currently docs are only pushed "
        "for terminal tickets via :archive; after BILL-98 :merge must push for all tickets."
    )


def test_merge_confirm_prompt_updated():
    """skills/merge/SKILL.md Step 3 confirm must NOT say 'Local tracking and ticket description NOT touched'.

    BILL-98: the confirm prompt must describe the new :update + :document steps.
    The old 'NOT touched' claim is wrong after the fix.
    """
    spine = (SKILLS_DIR / "merge" / "SKILL.md").read_text()
    assert "Local tracking and ticket description NOT touched" not in spine, (
        "skills/merge/SKILL.md Step 3 confirm still says "
        "'Local tracking and ticket description NOT touched' — "
        "update this text to reflect that :update + :document now run after the merge."
    )


def test_merge_summary_has_docs_line():
    """skills/merge/SKILL.md summary block must include a 'Docs:' output line.

    BILL-98: the post-merge summary must report the outcome of the :document step
    (pushed vs already-current vs failed) so the user can confirm the ticket was updated.
    """
    spine = (SKILLS_DIR / "merge" / "SKILL.md").read_text()
    assert "Docs:" in spine, (
        "skills/merge/SKILL.md summary block is missing a 'Docs:' line — "
        "add it to the Step 8/9 summary block to report the :document push outcome "
        "(e.g. 'Docs: description updated, findings posted | already current | failed: <reason>')."
    )


# ---------------------------------------------------------------------------
# 3. :archive must no longer call :document (pure lifecycle — file move only)
# ---------------------------------------------------------------------------

def test_archive_no_document_step_heading():
    """skills/archive/SKILL.md must NOT have a 'Push documentation (delegate' step.

    BILL-98: :archive is reduced to file-lifecycle only. Step 3 ('Push documentation
    — delegate to /slopstop:document') must be removed entirely. :document is now
    called by :merge, before the terminal-state :archive chain runs.
    """
    spine = (SKILLS_DIR / "archive" / "SKILL.md").read_text()
    assert "Push documentation (delegate" not in spine, (
        "skills/archive/SKILL.md still has a 'Push documentation (delegate...)' step — "
        "remove Step 3 (:document delegation) per BILL-98. "
        ":document is now called by :merge before chaining :archive."
    )


def test_archive_frontmatter_no_delegates_document():
    """skills/archive/SKILL.md frontmatter must NOT say 'Delegates the documentation push'.

    BILL-98: :archive no longer owns the documentation push. The description
    frontmatter must be updated to reflect the new file-lifecycle-only role.
    """
    spine = (SKILLS_DIR / "archive" / "SKILL.md").read_text()
    frontmatter_end = spine.find("---", 3)
    frontmatter = spine[:frontmatter_end] if frontmatter_end != -1 else spine[:500]
    assert "Delegates the documentation push" not in frontmatter, (
        "skills/archive/SKILL.md frontmatter still says 'Delegates the documentation push' — "
        "update the description to reflect the new lifecycle-only role per BILL-98."
    )


def test_archive_confirm_no_push_documentation():
    """archive-confirm-prompt.md must NOT say 'Push documentation to $SYSTEM'.

    BILL-98: the archive confirm prompt no longer offers to push documentation
    (that step is removed). The prompt must only describe the file move.
    """
    ref_path = SKILLS_DIR / "archive" / "references" / "archive-confirm-prompt.md"
    text = ref_path.read_text()
    assert "Push documentation to $SYSTEM" not in text, (
        "archive-confirm-prompt.md still says 'Push documentation to $SYSTEM' — "
        "remove the documentation push step from the confirm prompt per BILL-98."
    )


def test_archive_confirm_no_skip_push_option():
    """archive-confirm-prompt.md must NOT offer a 'skip-push' option.

    BILL-98: the skip-push option exists only because :archive currently owns
    the doc push. After the fix, there is no doc push to skip, so the option
    must be removed from the confirm prompt.
    """
    ref_path = SKILLS_DIR / "archive" / "references" / "archive-confirm-prompt.md"
    text = ref_path.read_text()
    assert "skip-push" not in text, (
        "archive-confirm-prompt.md still offers a 'skip-push' option — "
        "remove it per BILL-98 (:archive no longer calls :document, so there is "
        "no doc push to skip)."
    )


def test_archive_summary_no_dod_comment_line():
    """skills/archive/SKILL.md Step 5 summary must NOT have a 'DoD comment:' output line.

    BILL-98: the archive summary currently lists Description:, DoD comment:,
    and Findings: (artifacts pushed by :document). Since :archive no longer calls
    :document, these lines must be removed from the Step 5 output.
    """
    spine = (SKILLS_DIR / "archive" / "SKILL.md").read_text()
    assert "DoD comment:" not in spine, (
        "skills/archive/SKILL.md Step 5 still has a 'DoD comment:' output line — "
        "remove Description:, DoD comment:, and Findings: from the confirm output "
        "per BILL-98 (:archive no longer calls :document)."
    )


# ---------------------------------------------------------------------------
# 4. merge-autonomous.md must cover the :update step autonomous behavior
# ---------------------------------------------------------------------------

def test_merge_autonomous_covers_update_step():
    """merge-autonomous.md must describe autonomous behavior for the :update step.

    BILL-98: in autonomous mode, :merge must run :update unconditionally (no
    staleness prompt). merge-autonomous.md must document this rule so
    autonomous sessions know to skip the prompt and always update.
    """
    ref_path = SKILLS_DIR / "merge" / "references" / "merge-autonomous.md"
    text = ref_path.read_text()
    has_update_rule = any(phrase in text for phrase in [
        "update unconditionally",
        "Update tracking",
        ":update",
        "slopstop:update",
    ])
    assert has_update_rule, (
        "merge-autonomous.md does not describe autonomous :update behavior — "
        "add a section stating that in autonomous mode :update runs unconditionally "
        "(no staleness prompt, no skip option) before the :document step."
    )


# ---------------------------------------------------------------------------
# Adversary gap — six additional gaps found by adversary agent
# ---------------------------------------------------------------------------

def test_merge_update_before_document():
    """skills/merge/SKILL.md: the :update step heading must appear before :document.

    Gap 1: tests 1 and 3 only check presence; neither enforces order.
    :update must precede :document because :document reads progress.md (written
    by :update). Wrong order → stale content pushed.
    """
    spine = (SKILLS_DIR / "merge" / "SKILL.md").read_text()
    update_pos = spine.find("Update tracking files")
    doc_pos = spine.find("slopstop:document")
    assert update_pos != -1, (
        "skills/merge/SKILL.md: 'Update tracking files' step not found — "
        "add it before the :document step."
    )
    assert doc_pos != -1, (
        "skills/merge/SKILL.md: 'slopstop:document' not found — "
        "add the :document step after 'Update tracking files'."
    )
    assert update_pos < doc_pos, (
        "skills/merge/SKILL.md: 'Update tracking files' appears AFTER 'slopstop:document' — "
        ":update must precede :document so progress.md is current when docs are pushed."
    )


def test_merge_document_step_precedes_archive_chain():
    """skills/merge/SKILL.md: slopstop:document must appear before slopstop:archive.

    Gap 2: the pre-BILL-98 spine already chains :archive (which internally calls
    :document for terminal tickets). A naive impl could leave :archive in place and
    satisfy test_merge_has_document_step via the :archive prose alone. The unconditional
    :document call must be a standalone step before the :archive terminal chain.
    """
    spine = (SKILLS_DIR / "merge" / "SKILL.md").read_text()
    doc_pos = spine.find("slopstop:document")
    archive_pos = spine.find("slopstop:archive")
    assert doc_pos != -1, (
        "skills/merge/SKILL.md: slopstop:document not found."
    )
    assert archive_pos != -1, (
        "skills/merge/SKILL.md: slopstop:archive not found (terminal-chain invariant broken)."
    )
    assert doc_pos < archive_pos, (
        "skills/merge/SKILL.md: slopstop:document appears AFTER slopstop:archive — "
        "the :document call must be an unconditional standalone step (for all tickets) "
        "that runs before the terminal-only :archive chain."
    )


def test_merge_document_failure_is_nonfatal():
    """skills/merge/SKILL.md must describe :document failure as non-fatal.

    Gap 3: BILL-98 requires :document failure to not roll back the merge. The
    summary output test only checks that 'Docs:' exists; it does not verify the
    failure handling rule is documented.
    """
    spine = (SKILLS_DIR / "merge" / "SKILL.md").read_text()
    has_nonfatal = any(phrase in spine for phrase in [
        "best-effort",
        "non-fatal",
        "failed: <reason>",
        "do NOT roll back",
        "does not roll back",
    ])
    assert has_nonfatal, (
        "skills/merge/SKILL.md does not document that :document failure is non-fatal — "
        "add prose (e.g. 'best-effort: if :document fails, report but do not roll back') "
        "to the :document step or the Rules section."
    )


def test_archive_spine_no_push_documentation_in_autoconfirm():
    """skills/archive/SKILL.md must NOT say 'Push documentation to $SYSTEM' anywhere.

    Gap 4: test_archive_confirm_no_push_documentation only checks the reference file
    (archive-confirm-prompt.md). The SKILL.md spine's skip_confirm auto-confirm log
    block also contains 'Push documentation to $SYSTEM' and must be updated.
    """
    spine = (SKILLS_DIR / "archive" / "SKILL.md").read_text()
    assert "Push documentation to $SYSTEM" not in spine, (
        "skills/archive/SKILL.md still contains 'Push documentation to $SYSTEM' (likely "
        "in the skip_confirm auto-confirm log block) — remove it from the spine per BILL-98."
    )


def test_archive_reharvest_step_preserved():
    """skills/archive/SKILL.md must still contain the re-harvest step.

    Gap 5: removing Step 3 (:document) might accidentally take Step 3.5
    (re-harvest) with it. The BILL-90 re-harvest must survive.
    """
    spine = (SKILLS_DIR / "archive" / "SKILL.md").read_text()
    has_reharvest = any(phrase in spine for phrase in [
        "Re-harvest",
        "text_harvest_on_merge",
        "/harvest/ticket",
    ])
    assert has_reharvest, (
        "skills/archive/SKILL.md no longer has the re-harvest step — "
        "Step 3.5 (BILL-90 text DB re-harvest) must be preserved when removing the "
        ":document delegation step."
    )


def test_merge_autonomous_update_unconditionally():
    """merge-autonomous.md must say :update runs unconditionally (no staleness prompt).

    Gap 6: test_merge_autonomous_covers_update_step accepts any mention of ':update'.
    That passes if someone adds ':update' tangentially. The rule that the staleness
    prompt is SUPPRESSED in autonomous mode must be explicitly stated.
    """
    ref_path = SKILLS_DIR / "merge" / "references" / "merge-autonomous.md"
    text = ref_path.read_text()
    has_unconditional = any(phrase in text for phrase in [
        "unconditionally",
        "no staleness prompt",
        "no prompt",
        "always run",
    ])
    assert has_unconditional, (
        "merge-autonomous.md does not say :update runs unconditionally — "
        "add 'always run :update unconditionally (no staleness prompt)' or equivalent "
        "to the autonomous behavior section."
    )


# ---------------------------------------------------------------------------
# Adversary gap — invariants that must NOT regress after BILL-98
# ---------------------------------------------------------------------------

def test_archive_still_moves_files():
    """skills/archive/SKILL.md must still describe moving files to ticket-archive.

    Invariant: :archive's core job after BILL-98 is the file-lifecycle move.
    The 'ticket-archive' reference must still be present.
    """
    spine = (SKILLS_DIR / "archive" / "SKILL.md").read_text()
    assert "ticket-archive" in spine, (
        "skills/archive/SKILL.md no longer mentions 'ticket-archive' — "
        "the file move (ticket-active/ → ticket-archive/) must be preserved in BILL-98."
    )


def test_merge_still_chains_archive_for_terminal():
    """skills/merge/SKILL.md must still chain :archive for terminal-state tickets.

    Invariant: BILL-87 wired the terminal-state archive chain. BILL-98 must not
    remove it — after the doc push, terminal tickets still auto-archive (file move).
    """
    spine = (SKILLS_DIR / "merge" / "SKILL.md").read_text()
    assert "slopstop:archive" in spine, (
        "skills/merge/SKILL.md no longer chains :archive for terminal tickets — "
        "the BILL-87 terminal-state archive chain must be preserved in BILL-98."
    )
