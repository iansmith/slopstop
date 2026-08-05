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
    "start", "document", "archive",
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

@pytest.mark.parametrize("skill", REFACTOR_TARGETS)
def test_skill_references_has_manifest(skill):
    """Each refactored skill must have references/manifest.txt listing all reference files."""
    manifest = SKILLS_DIR / skill / "references" / "manifest.txt"
    assert manifest.is_file(), (
        f"skills/{skill}/references/manifest.txt missing — "
        f"create it listing all *.md files in the references/ dir."
    )


@pytest.mark.parametrize("skill", REFACTOR_TARGETS)
def test_skill_manifest_matches_files(skill):
    """manifest.txt entries must match the actual .md files in references/ (no missing, no extra)."""
    refs_dir = _require_refs_dir(skill)
    manifest = refs_dir / "manifest.txt"
    if not manifest.is_file():
        pytest.skip("manifest.txt absent — failing in test_skill_references_has_manifest")
    listed = {line.strip() for line in manifest.read_text().splitlines() if line.strip()}
    on_disk = {f.name for f in refs_dir.glob("*.md")}
    missing_from_disk = listed - on_disk
    missing_from_manifest = on_disk - listed
    assert not missing_from_disk, (
        f"skills/{skill}/references/manifest.txt lists files that don't exist on disk: "
        f"{sorted(missing_from_disk)}. Remove them or create the files."
    )
    assert not missing_from_manifest, (
        f"skills/{skill}/references/ has .md files not listed in manifest.txt: "
        f"{sorted(missing_from_manifest)}. Add them to manifest.txt so they get installed."
    )


# ---------------------------------------------------------------------------
# Spine must delegate to references/ via → Read pointers (BILL-91 skills)
# ---------------------------------------------------------------------------

