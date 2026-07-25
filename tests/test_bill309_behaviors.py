"""
Phase 0 red tests for BILL-309 — fleet agents must be able to Write.

Transcribed from the ticket's Test expectations
(https://github.com/iansmith/slopstop/issues/309). Structural assertions over
skill and doc text, matching the test_skill_structure.py convention.

`:run` launched every fleet agent with `--permission-mode auto`, under which the
agent's own `Write` is denied — an implementation agent that cannot Write cannot
implement anything. `acceptEdits` covers `Write`, `--allowedTools` covers `Bash`,
and neither alone is sufficient; the measured matrix lives in the bullet this file
guards (`skills/run/SKILL.md`, Step 4's flag rationale) rather than being copied
here. The old text got half of it right — `acceptEdits` alone does deny `Bash` —
and drew the wrong conclusion, because BILL-181's original measurement tested
`Bash` only and never tried the pairing.

The sweep uses the allowlist convention from test_bill316_behaviors.py: a closed
set of roots, rather than a denylist over REPO_ROOT. A denylist admits ~740
untracked files (installed plugins under `.claude/`, per-agent worktrees, the
gitignored `docs/`), which would false-red the moment a worktree cut before this
fix lands is left on disk. It also sweeps `.toml.example` and shell files, not
just `*.md` — the stale copy this ticket's first pass missed was in
`.project-conf.toml.example`, which an `*.md`-only sweep structurally cannot see.

CHANGELOG.md is deliberately excluded: its entries describe past releases in which
the recipe genuinely did say `auto`, and rewriting release history would be a lie.

These tests FAIL on current code and turn GREEN once the fix is applied.

Test command:
    python3 -m pytest tests/test_bill309_behaviors.py -v
"""

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent
RUN_SPINE = REPO_ROOT / "skills" / "run" / "SKILL.md"

# Anywhere a launch recipe or its rationale can live. Closed by construction.
SEARCH_ROOTS = [REPO_ROOT / "skills", REPO_ROOT / "design", REPO_ROOT / "tools"]
SWEEP_SUFFIXES = {".md", ".sh", ".json", ".example"}
TOP_LEVEL_DOCS = [
    REPO_ROOT / "CONFIG.md",
    REPO_ROOT / "README.md",
    REPO_ROOT / "SETUP-GUIDE.md",
    REPO_ROOT / ".project-conf.toml.example",
    REPO_ROOT / "install-for-claude-desktop.sh",
]

CORRECT_FLAG = "--permission-mode acceptEdits"
STALE_FLAG = "--permission-mode auto"


@pytest.fixture(scope="module")
def spine():
    return RUN_SPINE.read_text()


def _swept_files():
    files = [
        p
        for root in SEARCH_ROOTS
        for p in root.rglob("*")
        if p.is_file() and p.suffix in SWEEP_SUFFIXES
    ]
    files.extend(p for p in TOP_LEVEL_DOCS if p.is_file())
    return files


def test_launch_recipe_uses_acceptedits(spine):
    """Behavior 1 — the launch block specifies acceptEdits, the mode that permits Write."""
    assert CORRECT_FLAG in spine, (
        f"skills/run/SKILL.md must launch fleet agents with {CORRECT_FLAG!r} — "
        "under 'auto' the agent's Write is denied and it cannot implement anything"
    )


def test_no_file_recommends_bare_auto_for_fleet_launches():
    """Behaviors 1 and 3 — no stale recipe or rationale survives anywhere in the repo.

    Covers the spine, the second launch line in tools/mcp-go-edit/README.md, and the
    twinned `allowed_tools` explanations in CONFIG.md and .project-conf.toml.example.
    A fix that touches only skills/run/SKILL.md leaves anyone following another copy
    just as unable to Write.
    """
    offenders = sorted(
        str(p.relative_to(REPO_ROOT))
        for p in _swept_files()
        if STALE_FLAG in p.read_text()
    )
    assert offenders == [], (
        f"these files still recommend {STALE_FLAG!r} for a headless launch: "
        f"{offenders}. Every copy of the recipe must use {CORRECT_FLAG!r}."
    )


def test_rationale_states_neither_flag_alone_suffices(spine):
    """Behavior 2 — the corrected matrix, not just the corrected flag.

    The point that gets lost is that the two flags cover *different* tools. Text
    that swaps the flag without explaining the pairing invites the next reader to
    "simplify" it back to a single mode.
    """
    low = spine.lower()
    assert "neither" in low and "alone" in low, (
        "the flag-rationale bullet must say neither acceptEdits nor --allowedTools "
        "alone is sufficient — that is the finding BILL-181 missed"
    )


def test_docs_note_orchestrator_may_need_settings_permission(spine):
    """Behavior 4 — spawning `claude -p` with acceptEdits can itself be gated.

    Some harnesses classify the flag as an escalation and deny the subprocess
    outright rather than prompting, which surfaces as an agent that never starts.
    """
    assert "settings.json" in spine, (
        "skills/run/SKILL.md must note that the orchestrating session may need "
        "~/.claude/settings.json to permit spawning `claude -p` with acceptEdits"
    )
