"""
Phase 0 red tests for BILL-132 — add tracking_dir config option to decouple
ticket-active location from ~/.claude.

Expected behaviors after implementation:
1. All seven ticket-lifecycle skills read tracking_dir from .project-conf.toml
2. All seven skills use $TRACKING_DIR as the base path for ticket path construction
3. Relative tracking_dir paths are resolved via dirname "$(git rev-parse --git-common-dir)"
4. Absent/default tracking_dir falls back to ~/.claude/ticket-active (backward-compat)
5. No skill constructs ticket paths as ~/.claude/ticket-active/$TICKET (hardcoded)

These tests FAIL on current code and turn GREEN once the implementation is complete.

Test command:
    python3 -m pytest tests/test_bill132_behaviors.py -v
"""

from pathlib import Path
import pytest

REPO_ROOT = Path(__file__).parent.parent
SKILLS_DIR = REPO_ROOT / "skills"

SEVEN_SKILLS = ["start", "plan", "update", "pr", "merge", "archive", "document"]


def _skill_text(name):
    """Return concatenated text of SKILL.md + all references/*.md for a skill."""
    base = SKILLS_DIR / name
    texts = []
    skill_md = base / "SKILL.md"
    if skill_md.exists():
        texts.append(skill_md.read_text())
    refs = base / "references"
    if refs.is_dir():
        for f in sorted(refs.glob("*.md")):
            texts.append(f.read_text())
    return "\n".join(texts)


def _spine(name):
    return (SKILLS_DIR / name / "SKILL.md").read_text()


# ---------------------------------------------------------------------------
# 1. All 7 skills must read tracking_dir from .project-conf.toml
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("skill", SEVEN_SKILLS)
def test_skill_reads_tracking_dir(skill):
    """Each of the 7 ticket-lifecycle skills must reference the tracking_dir config key.

    BILL-132: tracking_dir is the new optional field that allows per-project isolation
    of ticket tracking files. Every skill that constructs a $TRACKING_DIR path must
    read this config key before doing so.
    """
    text = _skill_text(skill)
    assert "tracking_dir" in text, (
        f"skills/{skill}/ has no mention of 'tracking_dir' — "
        f"BILL-132 requires this skill to read tracking_dir from .project-conf.toml "
        f"and resolve it to $TRACKING_DIR before constructing ticket paths."
    )


# ---------------------------------------------------------------------------
# 2. All 7 skills must use $TRACKING_DIR as the resolved base path variable
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("skill", SEVEN_SKILLS)
def test_skill_uses_tracking_dir_variable(skill):
    """Each skill must use $TRACKING_DIR when constructing ticket paths.

    BILL-132: after resolving tracking_dir from config, the skill must refer to
    $TRACKING_DIR throughout — not the literal ~/.claude/ticket-active string.
    This ensures the user's configured location is actually used at runtime.
    """
    text = _skill_text(skill)
    assert "$TRACKING_DIR" in text, (
        f"skills/{skill}/ does not use $TRACKING_DIR — "
        f"BILL-132 requires this variable to be set from tracking_dir config "
        f"and used for all ticket path construction."
    )


# ---------------------------------------------------------------------------
# 3. No skill should construct ticket paths via the hardcoded ~/.claude/ticket-active
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("skill", SEVEN_SKILLS)
def test_skill_does_not_hardcode_ticket_active_path(skill):
    """No skill should construct paths as ~/.claude/ticket-active/$<VAR>.

    After BILL-132, the path base must come from $TRACKING_DIR, not a literal string.
    The pattern '~/.claude/ticket-active/$' (followed by TICKET, ARGUMENTS, KEY, etc.)
    is always a hardcoded path that bypasses $TRACKING_DIR.

    Note: '~/.claude/ticket-active' appearing alone (without a following '$') is
    acceptable as the documentation for the absent-config default value.
    """
    text = _skill_text(skill)
    assert "~/.claude/ticket-active/$" not in text, (
        f"skills/{skill}/ still constructs ticket paths as '~/.claude/ticket-active/$...' — "
        f"BILL-132 requires all ticket path construction to use $TRACKING_DIR/$TICKET instead."
    )


# ---------------------------------------------------------------------------
# 4. Relative path resolution: must use git rev-parse --git-common-dir
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("skill", SEVEN_SKILLS)
def test_skill_relative_tracking_dir_resolved_from_main_worktree(skill):
    """Relative tracking_dir paths must be resolved from the main worktree root.

    Resolution: dirname "$(git rev-parse --git-common-dir)" gives the main worktree
    root even when operating from a linked worktree. This ensures worktree sessions
    and main-checkout sessions share the same tracking files at the same path.

    The skill must document this resolution rule so that implementers know which
    directory a relative path is relative to.
    """
    spine = _spine(skill)
    # git-common-dir already appears in every skill for the config-file fallback (BILL-130 B1).
    # After BILL-132 the skill must also mention tracking_dir resolution in that context,
    # OR the tracking_dir resolution block must itself cite git-common-dir.
    # Either way, 'tracking_dir' and 'git-common-dir' must co-exist in the spine.
    assert "tracking_dir" in spine and "git-common-dir" in spine, (
        f"skills/{skill}/SKILL.md must document relative tracking_dir path resolution "
        f"via dirname \"$(git rev-parse --git-common-dir)\". "
        f"BILL-132: relative paths are relative to the main worktree root, not cwd."
    )


# ---------------------------------------------------------------------------
# 5. :start — seeding step must use $TRACKING_DIR, not a hardcoded path
# ---------------------------------------------------------------------------

def test_start_skill_seed_step_uses_tracking_dir():
    """The :start skill's fresh-start seed step must create the tracking dir at $TRACKING_DIR.

    The seed step (Step 6) currently hardcodes '~/.claude/ticket-active/$ARGUMENTS/'.
    After BILL-132 it must use '$TRACKING_DIR/$ARGUMENTS/' so that the tracking dir
    is placed in the user's configured location, not always under ~/.claude.
    """
    spine = _spine("start")
    assert "~/.claude/ticket-active/$ARGUMENTS" not in spine, (
        "skills/start/SKILL.md step 6 still seeds the tracking dir at "
        "'~/.claude/ticket-active/$ARGUMENTS/' — "
        "BILL-132: use $TRACKING_DIR/$ARGUMENTS/ after resolving tracking_dir."
    )


def test_start_skill_prints_tracking_dir_not_hardcoded():
    """The :start skill's Step 6 confirmation print must not hardcode the active path.

    Currently: 'Started $ARGUMENTS — tracking at ~/.claude/ticket-active/$ARGUMENTS/.'
    After BILL-132: must use $TRACKING_DIR so the printed path matches reality.
    """
    spine = _spine("start")
    assert "tracking at ~/.claude/ticket-active" not in spine, (
        "skills/start/SKILL.md still prints '~/.claude/ticket-active' as the tracking "
        "location — BILL-132: print '$TRACKING_DIR/$TICKET/' instead."
    )


# ---------------------------------------------------------------------------
# 6. :archive — mv source must use $TRACKING_DIR
# ---------------------------------------------------------------------------

def test_archive_skill_mv_source_uses_tracking_dir():
    """The :archive skill's mv command must use $TRACKING_DIR as the source path base.

    Step 4 currently runs: mv ~/.claude/ticket-active/$TICKET ~/.claude/ticket-archive/$TICKET
    After BILL-132 the source must be $TRACKING_DIR/$TICKET so that tickets stored in
    a custom tracking_dir can actually be found and archived.
    """
    text = _skill_text("archive")
    assert "mv $TRACKING_DIR" in text or "mv ~/.claude/ticket-active" not in text, (
        "skills/archive/ mv command still uses ~/.claude/ticket-active as source — "
        "BILL-132: mv source must be $TRACKING_DIR/$TICKET."
    )


def test_archive_confirm_prompt_uses_tracking_dir():
    """The archive-confirm-prompt.md reference must use $TRACKING_DIR in the mv preview.

    The confirm prompt currently shows: mv ~/.claude/ticket-active/$TICKET/ → ...
    After BILL-132 it must show: mv $TRACKING_DIR/$TICKET/ → ... so the preview
    matches the location the user configured.
    """
    ref = (SKILLS_DIR / "archive" / "references" / "archive-confirm-prompt.md").read_text()
    assert "~/.claude/ticket-active/$" not in ref, (
        "skills/archive/references/archive-confirm-prompt.md still shows "
        "'~/.claude/ticket-active/$TICKET' in the mv preview — "
        "BILL-132: use $TRACKING_DIR/$TICKET."
    )


# ---------------------------------------------------------------------------
# 7. :plan — monitor loop state file must use $TRACKING_DIR
# ---------------------------------------------------------------------------

def test_plan_monitor_loop_uses_tracking_dir():
    """The plan-monitor-loop.md reference must use $TRACKING_DIR for the STATE file path.

    plan-monitor-loop.md currently sets: STATE=~/.claude/ticket-active/$TICKET/.agents.json
    After BILL-132 it must use: STATE=$TRACKING_DIR/$TICKET/.agents.json so that the
    parallel-agent monitor finds the state file in the configured tracking location.
    """
    ref = (SKILLS_DIR / "plan" / "references" / "plan-monitor-loop.md").read_text()
    assert "~/.claude/ticket-active/$" not in ref, (
        "skills/plan/references/plan-monitor-loop.md still sets STATE at "
        "'~/.claude/ticket-active/$TICKET/.agents.json' — "
        "BILL-132: use $TRACKING_DIR/$TICKET/.agents.json."
    )


# ---------------------------------------------------------------------------
# 8. :merge — progress.md read path must use $TRACKING_DIR
# ---------------------------------------------------------------------------

def test_merge_skill_progress_read_uses_tracking_dir():
    """The :merge skill's Step 6 must read progress.md from $TRACKING_DIR, not hardcoded.

    Step 6 currently reads: 'Read progress.md in ~/.claude/ticket-active/$TICKET/'
    After BILL-132 it must read from $TRACKING_DIR/$TICKET/ so that merge works
    regardless of where the tracking dir is configured.
    """
    spine = _spine("merge")
    assert "~/.claude/ticket-active/$TICKET/" not in spine, (
        "skills/merge/SKILL.md step 6 still reads progress.md from "
        "'~/.claude/ticket-active/$TICKET/' — "
        "BILL-132: use $TRACKING_DIR/$TICKET/ after resolving tracking_dir."
    )


# ---------------------------------------------------------------------------
# 9. :document — must read tracking files from $TRACKING_DIR
# ---------------------------------------------------------------------------

def test_document_skill_reads_from_tracking_dir():
    """The :document skill must read task_plan.md and findings.md from $TRACKING_DIR.

    Step 3 currently reads: ~/.claude/ticket-active/$TICKET/{task_plan,findings}.md
    After BILL-132 it must read from $TRACKING_DIR/$TICKET/ so that :document
    finds tracking files regardless of the configured location.
    """
    spine = _spine("document")
    assert "~/.claude/ticket-active/$TICKET" not in spine, (
        "skills/document/SKILL.md still reads tracking files from "
        "'~/.claude/ticket-active/$TICKET' — "
        "BILL-132: use $TRACKING_DIR/$TICKET/ after resolving tracking_dir."
    )
