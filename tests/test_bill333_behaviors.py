"""
Behavior tests for BILL-333 — configurable reasoning effort for tier-resolved
agent spawns.

Design: `[tiers.<tier>]` picks a model but has no effort dial. This ticket adds
`effort` to each tier block (default "inherit"), a single fallback chain (specific
key -> resolved tier's effort -> inherit) for the existing `[pr_review].effort`
and `[fleet.agents].effort`/`adversary_effort` keys, unifies the effort vocabulary
on `low`/`medium`/`high`/`xhigh`/`max` (killing the stray `ultra`), and requires a
written capability audit (`design/agent-effort-capability.md`) naming which spawn
sites can actually carry an effort value.

Test command:
    python3 -m pytest tests/test_bill333_behaviors.py -v
"""

import re
import tomllib
from pathlib import Path

import pytest

from tests.conftest import REPO_ROOT, tracked_files

EFFORT_DOCS = [
    REPO_ROOT / "CONFIG.md",
    REPO_ROOT / "README.md",
    REPO_ROOT / "SETUP-GUIDE.md",
    REPO_ROOT / "QUICKSTART.md",
    REPO_ROOT / "COMMANDS.md",
    REPO_ROOT / "design" / "project-conf-options.md",
]

EXPECTED_EFFORT_SET = {"low", "medium", "high", "xhigh", "max"}

CAPABILITY_AUDIT = REPO_ROOT / "design" / "agent-effort-capability.md"
EXAMPLE_CONF = REPO_ROOT / ".project-conf.toml.example"
CONFIG_MD = REPO_ROOT / "CONFIG.md"
PR_CLAUDE_REVIEW = REPO_ROOT / "skills" / "pr" / "references" / "pr-claude-review.md"
PR_SKILL = REPO_ROOT / "skills" / "pr" / "SKILL.md"

# Every spawn-site path named in the ticket's file map.
SPAWN_SITES = [
    REPO_ROOT / "skills" / "tickets" / "references" / "tickets-adversary.md",
    REPO_ROOT / "skills" / "single-ticket" / "SKILL.md",
    REPO_ROOT / "skills" / "single-ticket" / "references" / "single-ticket-adversary.md",
    REPO_ROOT / "skills" / "run" / "references" / "run-failure-handling.md",
    REPO_ROOT / "skills" / "run" / "references" / "run-final-report.md",
    REPO_ROOT / "skills" / "run" / "references" / "run-verification.md",
    REPO_ROOT / "skills" / "plan" / "references" / "plan-investigation.md",
]


def test_effort_vocabulary_is_uniform():
    """No tracked file documents 'ultra' as an effort value; every documented
    effort enum is exactly low/medium/high/xhigh/max."""
    offenders = []
    ultra_re = re.compile(r"\bultra\b", re.IGNORECASE)
    for path in EFFORT_DOCS:
        text = path.read_text()
        for match in ultra_re.finditer(text):
            window = text[max(0, match.start() - 80) : match.end() + 80]
            if "effort" in window.lower():
                line_no = text.count("\n", 0, match.start()) + 1
                offenders.append(f"{path.relative_to(REPO_ROOT)}:{line_no}")
    assert not offenders, (
        f"'ultra' still documented as an effort value in: {offenders}. "
        "The accepted set is low/medium/high/xhigh/max — /code-review ultra is a "
        "separate review mode, not an effort level."
    )


def test_example_conf_tiers_carry_effort():
    text = EXAMPLE_CONF.read_text()
    tomllib.loads(text)  # must parse as valid TOML

    tier_blocks = re.findall(
        r"\[tiers\.(\w+)\](.*?)(?=\n\[|\Z)", text, re.DOTALL
    )
    assert tier_blocks, "No [tiers.<tier>] blocks found in .project-conf.toml.example"
    missing = [name for name, body in tier_blocks if "effort" not in body]
    assert not missing, (
        f"[tiers.<tier>] blocks missing an 'effort' line: {missing} "
        "(a commented example line is sufficient)."
    )


def test_config_md_documents_tier_effort():
    text = CONFIG_MD.read_text()
    assert re.search(r"\bTier\b.*\beffort\b|\beffort\b.*\btier\b", text, re.IGNORECASE), (
        "CONFIG.md does not document a per-tier 'effort' key."
    )
    assert "inherit" in text.lower(), (
        "CONFIG.md does not state 'inherit' as the tier effort default."
    )
    for value in EXPECTED_EFFORT_SET:
        assert value in text, f"CONFIG.md's tier effort docs are missing '{value}'."


def test_config_md_documents_fallback_chain():
    text = CONFIG_MD.read_text()
    assert re.search(
        r"specific key.{0,80}tier.{0,40}effort.{0,80}inherit"
        r"|tier.{0,40}effort.{0,80}inherit"
        r"|specific.{0,120}inherit",
        text,
        re.IGNORECASE | re.DOTALL,
    ), (
        "CONFIG.md does not state the specific-key -> tier-effort -> inherit "
        "fallback chain."
    )


def test_pr_review_effort_resolves_through_chain():
    text = PR_SKILL.read_text() + "\n" + PR_CLAUDE_REVIEW.read_text()
    assert re.search(r'\$PR_EFFORT\s*=\s*effort\s+else\s+"high"', text) is None, (
        "$PR_EFFORT still resolves via a bare literal 'else \"high\"' fallback — "
        "it must resolve through the specific-key -> tier-effort -> inherit chain."
    )
    assert re.search(r"tier.{0,60}effort|effort.{0,60}tier", text, re.IGNORECASE), (
        "$PR_EFFORT resolution does not reference a tier's effort as part of its "
        "fallback chain."
    )


def test_capability_audit_covers_every_spawn_site():
    assert CAPABILITY_AUDIT.is_file(), (
        "design/agent-effort-capability.md does not exist — Behavior 1's audit "
        "is missing."
    )
    text = CAPABILITY_AUDIT.read_text()
    missing = []
    for site in SPAWN_SITES:
        rel = str(site.relative_to(REPO_ROOT))
        if rel not in text:
            missing.append(rel)
    assert not missing, (
        f"design/agent-effort-capability.md does not mention these file-map spawn "
        f"sites: {missing}"
    )


def test_no_spawn_site_left_silent():
    """Every spawn-site file either passes an effort or carries the Behavior-5
    comment pointing at the audit — never silently unchanged."""
    assert CAPABILITY_AUDIT.is_file(), "Audit file missing (see prior test)."
    for site in SPAWN_SITES:
        text = site.read_text()
        passes_effort = re.search(r"\beffort\b", text, re.IGNORECASE) and re.search(
            r"\[tiers\.", text
        )
        names_audit = "agent-effort-capability" in text
        assert passes_effort or names_audit, (
            f"{site.relative_to(REPO_ROOT)} neither resolves/passes an effort value "
            "nor carries a comment naming design/agent-effort-capability.md."
        )
