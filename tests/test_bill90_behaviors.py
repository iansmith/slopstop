"""
Phase 0 red tests for BILL-90 — auto-update hooks.

Expected behaviors after implementation:
1. skills/archive: text DB re-harvest described (fire-and-forget after archive)
2. skills/archive: text_harvest_on_merge config key documented
3. skills/archive: RAG health check gates the harvest
4. skills/archive: harvest failure is non-blocking
5. Project: graph_index_on_commit config key documented somewhere
6. Project: PostToolUse hook for git commit described somewhere

These tests FAIL on current code (none of these behaviors exist yet) and
turn GREEN once the implementation is complete.

Test command:
    pytest tests/test_bill90_behaviors.py -v
"""

from pathlib import Path
import pytest

REPO_ROOT = Path(__file__).parent.parent
SKILLS_DIR = REPO_ROOT / "skills"
DESIGN_DIR = REPO_ROOT / "design"


def _skill_text(*parts):
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


def _design_texts():
    if not DESIGN_DIR.is_dir():
        return ""
    return "\n".join(f.read_text() for f in sorted(DESIGN_DIR.glob("*.md")))


def _all_skill_texts():
    parts = []
    for d in SKILLS_DIR.iterdir():
        if d.is_dir():
            parts.append(_skill_text(d.name))
    return "\n".join(parts)


# Computed once per test-session — both hook-config tests read the same corpus.
_SKILL_CORPUS = _all_skill_texts()
_DESIGN_CORPUS = _design_texts()


# ---------------------------------------------------------------------------
# 1. archive skill — text DB re-harvest
# ---------------------------------------------------------------------------

def test_archive_skill_mentions_text_harvest():
    """skills/archive must describe re-harvesting closed ticket into text DB.

    BILL-90 Trigger 2: after archive, re-harvest the closed ticket into
    ticket_chunks so search_tickets returns the final description + DoD.
    """
    text = _skill_text("archive")
    lower = text.lower()
    has_harvest = (
        "re-harvest" in lower
        or "reharvest" in lower
        or ("harvest" in lower and "ticket" in lower)
        or "ticket_chunks" in lower
        or "sync_ticket" in lower
        or ("text" in lower and "corpus" in lower)
    )
    assert has_harvest, (
        "skills/archive/ has no mention of text DB re-harvest — "
        "BILL-90 requires re-harvesting the closed ticket into ticket_chunks."
    )


def test_archive_skill_has_text_harvest_config_key():
    """skills/archive must reference the text_harvest_on_merge config key.

    BILL-90: '[hooks] text_harvest_on_merge = true' controls this behavior.
    """
    text = _skill_text("archive")
    assert "text_harvest_on_merge" in text, (
        "skills/archive/ missing 'text_harvest_on_merge' config key — "
        "BILL-90 requires this key to suppress re-harvest per-project."
    )


def test_archive_skill_harvest_is_nonblocking():
    """skills/archive must specify harvest failure doesn't block the archive.

    BILL-90: 'failure should warn, not fail the merge.'
    """
    text = _skill_text("archive")
    lower = text.lower()
    nonblocking = (
        "fire-and-forget" in lower
        or "non-blocking" in lower
        or "nonblocking" in lower
        or ("warn" in lower and ("not block" in lower or "not fail" in lower))
        or "harvest failure" in lower
    )
    assert nonblocking, (
        "skills/archive/ doesn't specify harvest failure is non-blocking — "
        "BILL-90 requires harvest failure to warn but not stop the archive."
    )


def test_archive_skill_checks_rag_health_before_harvest():
    """skills/archive must gate the text harvest on RAG service health.

    BILL-90: 'Both degrade gracefully when the RAG service is unavailable.'
    """
    text = _skill_text("archive")
    lower = text.lower()
    has_health_gate = (
        "rag_health" in text
        or ("rag" in lower and "health" in lower)
        or ("unavailable" in lower and "harvest" in lower)
        or ("skip" in lower and "harvest" in lower and "unavailable" in lower)
    )
    assert has_health_gate, (
        "skills/archive/ doesn't mention RAG health check before harvest — "
        "BILL-90 requires graceful degradation when RAG service is unavailable."
    )


# ---------------------------------------------------------------------------
# 2. Post-commit graph re-index — config + hook description
# ---------------------------------------------------------------------------

def test_graph_index_on_commit_config_documented():
    """graph_index_on_commit config key must appear somewhere in the project.

    BILL-90: '[hooks] graph_index_on_commit = true' in .project-conf.toml.
    Acceptable: any skill SKILL.md, design/*.md, or plugin config.
    """
    combined = _SKILL_CORPUS + "\n" + _DESIGN_CORPUS
    for plugin_file in (REPO_ROOT / ".claude-plugin").glob("*.json"):
        combined += "\n" + plugin_file.read_text()

    assert "graph_index_on_commit" in combined, (
        "'graph_index_on_commit' config key not found in any skill, design doc, or plugin config — "
        "BILL-90 requires this key to be documented."
    )


def test_post_commit_hook_mechanism_documented():
    """PostToolUse hook on Bash for git commit must be described somewhere.

    BILL-90: 'A PostToolUse hook on the Bash tool that detects a git commit
    invocation is the right mechanism.'
    """
    combined = _SKILL_CORPUS + "\n" + _DESIGN_CORPUS

    has_hook = "PostToolUse" in combined or "post_tool_use" in combined
    assert has_hook, (
        "PostToolUse hook for git commit not described in any skill or design doc — "
        "BILL-90 requires this mechanism to be documented (must mention 'PostToolUse')."
    )
