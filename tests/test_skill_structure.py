"""
Phase 0 red tests for BILL-85 — skill spine + references/ refactor.

These tests describe the expected *post-refactor* structure of the slopstop
skills.  They FAIL on the current (un-refactored) codebase and turn GREEN
once the refactoring is complete.

Test command:
    pytest tests/test_skill_structure.py -v
"""

from pathlib import Path
import pytest

REPO_ROOT = Path(__file__).parent.parent
SKILLS_DIR = REPO_ROOT / "skills"
INSTALL_SCRIPT = REPO_ROOT / "install-for-claude-desktop.sh"

# Skills targeted for spine + references/ split (ordered by token impact).
# pr/plan/merge: refactored in BILL-85.
# start/document/archive/search/doc-sync/create-gh: refactored in BILL-91.
# update: audit-only (87 lines, nothing extractable — intentionally excluded).
REFACTOR_TARGETS = [
    "pr", "plan", "merge",
    "start", "document", "archive", "search",
    "doc-sync", "create-gh",
]

# Maximum allowed lines for any refactored SKILL.md spine
LINE_LIMIT = 350


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _require_refs_dir(skill: str) -> Path:
    """Return the references/ Path for *skill*, or skip the test if absent.

    Guards any test that requires the references/ dir to exist.  The
    structural prerequisite (does the dir exist at all?) is enforced by
    test_skill_has_references_dir; callers of this helper add content checks
    on top.
    """
    refs_dir = SKILLS_DIR / skill / "references"
    if not refs_dir.is_dir():
        pytest.skip(
            f"skills/{skill}/references/ absent — failing in test_skill_has_references_dir"
        )
    return refs_dir


def _refs_text(skill: str) -> str:
    """Return concatenated text of all *.md files in a skill's references/ dir.

    Callers must have already verified (or skip-guarded on) the dir existing.
    """
    refs_dir = SKILLS_DIR / skill / "references"
    return " ".join(f.read_text() for f in refs_dir.glob("*.md"))


# ---------------------------------------------------------------------------
# Line-count tests — all three target skills are currently well over the limit
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("skill", REFACTOR_TARGETS)
def test_skill_within_line_limit(skill):
    """Each refactored SKILL.md spine must be ≤ LINE_LIMIT lines."""
    path = SKILLS_DIR / skill / "SKILL.md"
    count = len(path.read_text().splitlines())
    assert count <= LINE_LIMIT, (
        f"skills/{skill}/SKILL.md has {count} lines — exceeds the {LINE_LIMIT}-line "
        f"spine limit.  Move detail to skills/{skill}/references/."
    )


# ---------------------------------------------------------------------------
# references/ directory structure tests
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("skill", REFACTOR_TARGETS)
def test_skill_has_references_dir(skill):
    """Each refactored skill must have a skills/<name>/references/ directory."""
    refs_dir = SKILLS_DIR / skill / "references"
    assert refs_dir.is_dir(), (
        f"skills/{skill}/references/ does not exist — "
        f"create it and move reference content out of the spine."
    )


@pytest.mark.parametrize("skill", REFACTOR_TARGETS)
def test_skill_references_dir_not_empty(skill):
    """Each references/ dir must contain at least one .md file."""
    _require_refs_dir(skill)
    assert _refs_text(skill), (
        f"skills/{skill}/references/ exists but has no .md files."
    )


# ---------------------------------------------------------------------------
# install-for-claude-desktop.sh must copy references/ alongside SKILL.md
# ---------------------------------------------------------------------------

def test_install_script_copies_references():
    """install-for-claude-desktop.sh must include logic to copy references/ subdirs."""
    script = INSTALL_SCRIPT.read_text()
    # After refactoring the install script will curl or copy each references/ file.
    # Minimum signal: the word "references" appears in the fetch/copy section
    # (not just in a comment) and there is a curl or cp/rsync call for it.
    assert "refs_dir" in script and "manifest_url" in script, (
        "install-for-claude-desktop.sh is missing the manifest/references fetch loop — "
        "it must be updated to install skills/<name>/references/*.md alongside SKILL.md. "
        "(checking for 'refs_dir' and 'manifest_url', not just a comment containing 'references')"
    )


# ---------------------------------------------------------------------------
# Spine-content discipline: verbose shell detail must move to references/
# ---------------------------------------------------------------------------

def test_pr_spine_does_not_contain_cc_gate_shell_detail():
    """skills/pr/SKILL.md spine must not contain the verbose CC gate shell snippet.

    The CC gate conditional decision ('if CHANGED_CODE is empty, skip') stays
    in the spine.  The full bash implementation (git diff --name-only, lizard
    invocation, JSON parsing loop) belongs in references/pr-cc-gate.md so it
    is only loaded when the CC gate actually runs.
    """
    spine = (SKILLS_DIR / "pr" / "SKILL.md").read_text()
    # These are implementation details that belong in the reference file
    assert "git diff --name-only" not in spine, (
        "skills/pr/SKILL.md contains 'git diff --name-only' — "
        "this CC gate implementation detail should live in references/pr-cc-gate.md."
    )
    assert "function_list" not in spine, (
        "skills/pr/SKILL.md contains 'function_list' (lizard JSON detail) — "
        "move it to references/pr-cc-gate.md."
    )


def test_pr_references_contain_cc_gate_shell_detail():
    """Once extracted, CC gate shell detail must be present in references/."""
    refs_dir = _require_refs_dir("pr")
    assert any("git diff --name-only" in f.read_text() for f in refs_dir.glob("*.md")), (
        "CC gate shell detail ('git diff --name-only') not found in any "
        "skills/pr/references/*.md file."
    )


def test_plan_spine_does_not_contain_worktree_agent_protocol():
    """skills/plan/SKILL.md spine must not contain the full per-agent prompt template.

    The orchestration spine keeps the Step number, decision points, and
    'Agent(isolation: worktree)' call.  The per-agent prompt template (the
    long instructional block starting with 'You are agent <agent-id>...') and
    the monitoring shell loop belong in references/plan-parallel.md.
    """
    spine = (SKILLS_DIR / "plan" / "SKILL.md").read_text()
    assert "You are agent" not in spine, (
        "skills/plan/SKILL.md contains per-agent prompt template text — "
        "move it to references/plan-agent-prompt.md."
    )
    assert "HARD_STUCK_MIN" not in spine, (
        "skills/plan/SKILL.md contains monitor shell loop detail — "
        "move it to references/plan-monitor-loop.md."
    )


# ---------------------------------------------------------------------------
# manifest.txt — every references/ dir must declare its files
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("skill", REFACTOR_TARGETS)
def test_skill_references_has_manifest(skill):
    """Each refactored skill must have references/manifest.txt listing all reference files."""
    manifest = SKILLS_DIR / skill / "references" / "manifest.txt"
    assert manifest.is_file(), (
        f"skills/{skill}/references/manifest.txt missing — "
        f"create it listing all *.md files in the references/ dir."
    )


# ---------------------------------------------------------------------------
# Spine must delegate to references/ via → Read pointers (BILL-91 skills)
# ---------------------------------------------------------------------------

# Skills from BILL-91 that are large enough to require extracted references.
BILL91_LARGE_TARGETS = ["start", "document", "archive", "search"]


@pytest.mark.parametrize("skill", BILL91_LARGE_TARGETS)
def test_bill91_skill_spine_has_read_pointers(skill):
    """Large BILL-91 target skills must delegate to references/ via → Read pointers."""
    spine = (SKILLS_DIR / skill / "SKILL.md").read_text()
    assert "→ Read" in spine, (
        f"skills/{skill}/SKILL.md has no '→ Read' pointers — "
        f"move conditional-branch detail to references/ and add pointer(s) at each decision point."
    )


# ---------------------------------------------------------------------------
# start spine content-discipline (BILL-91)
# ---------------------------------------------------------------------------

def test_start_spine_no_branch_type_table_detail():
    """skills/start/SKILL.md must not contain branch-type heuristic table rows.

    The branch-type label→suggestion mapping table (bug→fix, enhancement→feat,
    tech-debt→chore, etc.) only loads when the user is choosing a branch type.
    It belongs in references/start-branch-type-heuristics.md, with a → Read
    pointer at Step 4a.
    """
    spine = (SKILLS_DIR / "start" / "SKILL.md").read_text()
    assert "tech-debt" not in spine, (
        "skills/start/SKILL.md contains 'tech-debt' (branch-type heuristic table detail) — "
        "move the full label→type mapping table to references/start-branch-type-heuristics.md."
    )


def test_start_spine_no_autonomous_json_stub():
    """skills/start/SKILL.md must not contain the autonomous pipeline.json stub.

    The full JSON stub with phase0_tests_red, simplify_line_delta, etc. is only
    needed when [autonomous] metrics_emit_path is set.  It belongs in
    references/start-autonomous.md.
    """
    spine = (SKILLS_DIR / "start" / "SKILL.md").read_text()
    assert "phase0_tests_red" not in spine, (
        "skills/start/SKILL.md contains 'phase0_tests_red' (autonomous metrics JSON stub) — "
        "move the full stub to references/start-autonomous.md."
    )


# ---------------------------------------------------------------------------
# document spine content-discipline (BILL-91)
# ---------------------------------------------------------------------------

def test_document_spine_no_push_shell_detail():
    """skills/document/SKILL.md spine must not contain per-backend push shell snippets.

    The HEREDOC CLI invocations in Step 6 (description update, DoD comment,
    findings comment) are backend-specific implementation detail that only runs
    on the GitHub CLI path.  They belong in references/document-push-backends.md,
    with a → Read pointer at Step 6.
    """
    spine = (SKILLS_DIR / "document" / "SKILL.md").read_text()
    assert "HEREDOC" not in spine, (
        "skills/document/SKILL.md contains 'HEREDOC' (GitHub CLI push shell detail) — "
        "move per-backend push snippets to references/document-push-backends.md."
    )


def test_merge_spine_does_not_contain_jira_linear_state_machine_detail():
    """skills/merge/SKILL.md spine must not contain the full JIRA/Linear preference logic.

    The spine keeps 'compute next state' as a single step reference.
    The preference-ranking algorithm (exclude won't-do, same-category advance,
    position-ordering) belongs in references/merge-state-machines.md.
    """
    spine = (SKILLS_DIR / "merge" / "SKILL.md").read_text()
    assert "won.?t do" not in spine, (
        "skills/merge/SKILL.md contains JIRA/Linear negative-completion exclusion regex — "
        "move state-machine detail to references/merge-state-machines.md."
    )
    assert "statusCategory" not in spine, (
        "skills/merge/SKILL.md contains raw JIRA statusCategory field references — "
        "move state-machine detail to references/merge-state-machines.md."
    )
