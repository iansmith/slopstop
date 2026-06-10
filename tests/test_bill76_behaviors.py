"""
Phase 0 red tests for BILL-76 — pr-remote and origin-remote config options.

Two optional .project-conf.toml keys:
  pr-remote     = "origin"   # remote to push feature branches to before opening a PR
  origin-remote = "origin"   # canonical remote; PR target + :merge source of truth

Skills affected: :start, :pr, :merge
Docs affected:   CONFIG.md, .project-conf.toml.example

These tests FAIL on current code and turn GREEN once all items are done.

Test command:
    python3 -m pytest tests/test_bill76_behaviors.py -v
"""

from pathlib import Path
import pytest

REPO_ROOT = Path(__file__).parent.parent
SKILLS_DIR = REPO_ROOT / "skills"
CONFIG_MD = REPO_ROOT / "CONFIG.md"
EXAMPLE_CONF = REPO_ROOT / ".project-conf.toml.example"


def _skill_text(skill: str) -> str:
    """Return concatenated text of SKILL.md + references/*.md for *skill*."""
    base = SKILLS_DIR / skill
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
# CONFIG.md — both keys must be documented
# ---------------------------------------------------------------------------

def test_config_md_documents_pr_remote():
    """CONFIG.md must document the pr-remote config key."""
    assert CONFIG_MD.is_file(), "CONFIG.md missing"
    assert "pr-remote" in CONFIG_MD.read_text(), (
        "CONFIG.md does not document 'pr-remote'. "
        "Add it to the top-level keys section with its default (\"origin\") and purpose."
    )


def test_config_md_documents_origin_remote():
    """CONFIG.md must document the origin-remote config key."""
    assert CONFIG_MD.is_file(), "CONFIG.md missing"
    assert "origin-remote" in CONFIG_MD.read_text(), (
        "CONFIG.md does not document 'origin-remote'. "
        "Add it to the top-level keys section with its default (\"origin\") and purpose."
    )


# ---------------------------------------------------------------------------
# .project-conf.toml.example — both keys with defaults shown
# ---------------------------------------------------------------------------

def test_example_conf_has_pr_remote():
    """.project-conf.toml.example must contain the pr-remote key."""
    assert EXAMPLE_CONF.is_file(), ".project-conf.toml.example missing"
    assert "pr-remote" in EXAMPLE_CONF.read_text(), (
        ".project-conf.toml.example is missing 'pr-remote'. "
        "Add it as an optional top-level key with default value \"origin\"."
    )


def test_example_conf_has_origin_remote():
    """.project-conf.toml.example must contain the origin-remote key."""
    assert EXAMPLE_CONF.is_file(), ".project-conf.toml.example missing"
    assert "origin-remote" in EXAMPLE_CONF.read_text(), (
        ".project-conf.toml.example is missing 'origin-remote'. "
        "Add it as an optional top-level key with default value \"origin\"."
    )


def test_example_conf_remotes_default_to_origin():
    """.project-conf.toml.example must show that remote keys default to \"origin\"."""
    assert EXAMPLE_CONF.is_file(), ".project-conf.toml.example missing"
    content = EXAMPLE_CONF.read_text()
    if "pr-remote" not in content or "origin-remote" not in content:
        pytest.skip("keys absent — failing in test_example_conf_has_pr_remote / test_example_conf_has_origin_remote")
    # Either the key is set to "origin" or a comment says it defaults to origin
    has_origin_default = (
        'pr-remote     = "origin"' in content
        or 'pr-remote = "origin"' in content
        or ("pr-remote" in content and "default" in content.lower() and "origin" in content)
    )
    assert has_origin_default, (
        ".project-conf.toml.example does not make clear that pr-remote defaults to \"origin\". "
        "Show the default value explicitly or add a comment."
    )


# ---------------------------------------------------------------------------
# :pr skill — push uses pr-remote; PR base uses origin-remote
# ---------------------------------------------------------------------------

def test_pr_skill_uses_pr_remote_for_push():
    """:pr skill must reference $PR_REMOTE (not hardcoded origin) when pushing."""
    text = _skill_text("pr")
    assert "$PR_REMOTE" in text or "pr-remote" in text, (
        "skills/pr/ does not reference '$PR_REMOTE' or 'pr-remote'. "
        "Step 4b (push the branch) must read pr-remote from config and push to $PR_REMOTE."
    )


def test_pr_skill_uses_origin_remote_for_pr_base():
    """:pr skill must reference $ORIGIN_REMOTE or origin-remote for the PR target."""
    text = _skill_text("pr")
    assert "$ORIGIN_REMOTE" in text or "origin-remote" in text, (
        "skills/pr/ does not reference '$ORIGIN_REMOTE' or 'origin-remote'. "
        "The PR is opened against origin-remote's repo, not necessarily the push remote."
    )


def test_pr_skill_documents_remote_read_in_preflight():
    """:pr skill preflight must mention reading pr-remote and origin-remote from config."""
    text = _skill_text("pr")
    assert "pr-remote" in text and "origin-remote" in text, (
        "skills/pr/ does not document reading both remote config keys. "
        "The Pre-flight section must read pr-remote and origin-remote from .project-conf.toml."
    )


# ---------------------------------------------------------------------------
# :merge skill — fetch/pull use origin-remote
# ---------------------------------------------------------------------------

def test_merge_skill_uses_origin_remote_for_fetch():
    """:merge skill must reference $ORIGIN_REMOTE (not hardcoded origin) for git fetch."""
    text = _skill_text("merge")
    assert "$ORIGIN_REMOTE" in text or "origin-remote" in text, (
        "skills/merge/ does not reference '$ORIGIN_REMOTE' or 'origin-remote'. "
        "Step 6a (fetch origin --prune) must use $ORIGIN_REMOTE."
    )


def test_merge_skill_reads_origin_remote_from_config():
    """:merge skill must say to read origin-remote from .project-conf.toml."""
    text = _skill_text("merge")
    assert "origin-remote" in text, (
        "skills/merge/ does not document reading 'origin-remote' from config. "
        "The Pre-flight or Project scope section must read origin-remote."
    )


# ---------------------------------------------------------------------------
# :start skill — base ref and remote branch check use the right remotes
# ---------------------------------------------------------------------------

def test_start_skill_uses_origin_remote_for_base():
    """:start skill must reference $ORIGIN_REMOTE for the base branch ref."""
    text = _skill_text("start")
    assert "$ORIGIN_REMOTE" in text or "origin-remote" in text, (
        "skills/start/ does not reference '$ORIGIN_REMOTE' or 'origin-remote'. "
        "Step 4c (determine base ref) must use origin-remote for $BASE_REF."
    )


def test_start_skill_uses_pr_remote_for_branch_check():
    """:start skill must use $PR_REMOTE when checking if a branch already exists remotely."""
    text = _skill_text("start")
    assert "$PR_REMOTE" in text or "pr-remote" in text, (
        "skills/start/ does not reference '$PR_REMOTE' or 'pr-remote'. "
        "Step 5a (check if remote branch exists) must use pr-remote."
    )


# ---------------------------------------------------------------------------
# Default fallback — skills document that absent keys default to "origin"
# ---------------------------------------------------------------------------

def test_at_least_one_skill_documents_remote_defaults():
    """At least one skill must document that pr-remote and origin-remote default to 'origin'."""
    skills_to_check = ["pr", "merge", "start"]
    found = False
    for skill in skills_to_check:
        text = _skill_text(skill)
        if "pr-remote" in text and "origin-remote" in text and "default" in text.lower():
            found = True
            break
    assert found, (
        "No skill documents the default fallback for pr-remote and origin-remote. "
        "At least one skill's Pre-flight must note: absent key → default to 'origin'."
    )
