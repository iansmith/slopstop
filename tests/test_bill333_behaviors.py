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
    REPO_ROOT / ".project-conf.toml",  # this repo's own LIVE config, not just .example
]

EXPECTED_EFFORT_SET = {"low", "medium", "high", "xhigh", "max"}

CAPABILITY_AUDIT = REPO_ROOT / "design" / "agent-effort-capability.md"
EXAMPLE_CONF = REPO_ROOT / ".project-conf.toml.example"
CONFIG_MD = REPO_ROOT / "CONFIG.md"
PR_CLAUDE_REVIEW = REPO_ROOT / "skills" / "pr" / "references" / "pr-claude-review.md"
PR_SKILL = REPO_ROOT / "skills" / "pr" / "SKILL.md"
RUN_SKILL = REPO_ROOT / "skills" / "run" / "SKILL.md"

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

    bad_values = []
    for name, body in tier_blocks:
        m = re.search(r'effort\s*=\s*"(\w+)"', body)
        if m and m.group(1) not in EXPECTED_EFFORT_SET:
            bad_values.append((name, m.group(1)))
    assert not bad_values, (
        f"[tiers.<tier>] effort example values outside {EXPECTED_EFFORT_SET}: {bad_values}"
    )


def test_example_conf_effort_vocabulary_is_clean():
    """The new effort line(s) must not use the retired 'ultra' value — EFFORT_DOCS
    omits .project-conf.toml.example, so the vocab sweep never reaches it otherwise."""
    text = EXAMPLE_CONF.read_text()
    ultra_re = re.compile(r"\bultra\b", re.IGNORECASE)
    offenders = []
    for match in ultra_re.finditer(text):
        window = text[max(0, match.start() - 80) : match.end() + 80]
        if "effort" in window.lower():
            offenders.append(text.count("\n", 0, match.start()) + 1)
    assert not offenders, (
        f".project-conf.toml.example uses 'ultra' as an effort value at line(s) {offenders}"
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


def test_config_md_effort_enum_documented_together():
    """The five effort values must appear co-located near an 'effort' mention,
    not merely scattered as incidental English words ('high-level', 'low overhead')."""
    text = CONFIG_MD.read_text()
    windows = [
        text[max(0, m.start() - 200) : m.end() + 400]
        for m in re.finditer(r"\beffort\b", text, re.IGNORECASE)
    ]
    assert any(all(v in w for v in EXPECTED_EFFORT_SET) for w in windows), (
        "No single region near an 'effort' mention lists all five values together."
    )


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


def test_config_md_fallback_chain_names_all_three_links():
    """The chain must name all three links in order: a specific key, tier effort,
    and inherit — not just any two words within reach of each other."""
    text = CONFIG_MD.read_text().lower()
    assert re.search(
        r"specific\b.{0,80}\btier\b.{0,80}\beffort\b.{0,80}\binherit\b", text, re.DOTALL
    ), (
        "CONFIG.md does not name all three links (specific key -> tier effort -> "
        "inherit) in one documented chain."
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


def test_pr_effort_var_definition_itself_references_tier_chain():
    """The chain reference must sit near the actual $PR_EFFORT definition/uses,
    not merely appear somewhere else in a multi-KB file."""
    text = PR_SKILL.read_text() + "\n" + PR_CLAUDE_REVIEW.read_text()
    defs = [m.start() for m in re.finditer(r"\$PR_EFFORT", text)]
    assert defs, "$PR_EFFORT is not referenced at all."
    found_chain_near_def = any(
        re.search(
            r"tier.{0,60}effort|effort.{0,60}tier",
            text[max(0, pos - 40) : pos + 300],
            re.IGNORECASE,
        )
        for pos in defs
    )
    assert found_chain_near_def, (
        "No $PR_EFFORT reference is followed/preceded by tier-effort chain "
        "language within a local window."
    )


# Round-2 review found: the fleet CLI launch (skills/run/SKILL.md) is one of only
# two spawn sites the capability audit marks CAPABLE, but its --effort recipe was
# never updated to route through the chain, and separately would break every
# default-config launch if it substituted the literal string "inherit" into
# --effort (the CLI doesn't accept that as a value).
def test_fleet_launch_effort_resolves_through_chain():
    text = RUN_SKILL.read_text()
    assert re.search(r"\[fleet\.agents\]\.effort", text), (
        "skills/run/SKILL.md's fleet launch does not reference "
        "[fleet.agents].effort as the specific-key link in the chain."
    )
    assert re.search(r"\[tiers\.small\]\.effort", text), (
        "skills/run/SKILL.md's fleet launch does not reference "
        "[tiers.small].effort as the tier-effort link in the chain."
    )


# Round-2 review (BILL-333) found that terminating this chain at bare "inherit"
# (--effort omitted) silently drops the concrete default [fleet.agents].effort
# already had before this ticket -- a real regression for every project that
# doesn't explicitly set effort anywhere, including this repo itself. Fixed by
# making the chain's floor each key's pre-existing literal default ("medium" /
# "high") instead of "inherit", so --effort is now unconditionally present on
# fleet launches. This test's own assertions previously required the opposite
# (omission) -- they encoded the same wrong assumption the bug was rooted in,
# so they're corrected here to match, not weakened to dodge a failure.
def test_fleet_launch_never_passes_literal_inherit():
    text = RUN_SKILL.read_text()
    assert re.search(r'--effort\s+"?inherit"?', text) is None, (
        "skills/run/SKILL.md's launch recipe substitutes the literal string "
        "'inherit' into --effort — the CLI does not accept 'inherit' as an "
        "effort value; the chain's floor must be a concrete default instead."
    )
    assert re.search(r'--effort\s+"\$FLEET_EFFORT"', text), (
        "skills/run/SKILL.md's launch recipe does not pass --effort "
        "unconditionally (it should never be conditionally omitted for fleet "
        "launches, since [fleet.agents].effort always had a concrete default)."
    )
    assert re.search(r'floor.{0,150}"medium"|"medium".{0,150}floor', text, re.IGNORECASE | re.DOTALL), (
        "skills/run/SKILL.md does not state that the chain's floor for "
        "[fleet.agents].effort is the pre-existing literal default 'medium', "
        "not bare 'inherit'."
    )


def test_adversary_effort_resolves_through_chain():
    """fleet.agents effort/adversary_effort spawn sites must reference the
    tier-effort chain, not a bare literal fallback, mirroring the pr_review
    chain requirement."""
    adversary_sites = [
        REPO_ROOT / "skills" / "tickets" / "references" / "tickets-adversary.md",
        REPO_ROOT / "skills" / "single-ticket" / "references" / "single-ticket-adversary.md",
    ]
    for site in adversary_sites:
        text = site.read_text()
        assert re.search(r"adversary_effort", text), (
            f"{site.relative_to(REPO_ROOT)} does not reference adversary_effort."
        )
        assert re.search(r"tier.{0,60}effort|effort.{0,60}tier", text, re.IGNORECASE), (
            f"{site.relative_to(REPO_ROOT)} does not reference the tier-effort "
            "chain for adversary_effort resolution."
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


def test_capability_audit_states_a_verdict_per_site():
    """Each spawn site's audit entry must state whether it can carry an effort
    value, not just be named in a list."""
    text = CAPABILITY_AUDIT.read_text()
    verdict_re = re.compile(r"\b(can|cannot|can't|able to|unable to)\b", re.IGNORECASE)
    missing_verdict = []
    for site in SPAWN_SITES:
        rel = str(site.relative_to(REPO_ROOT))
        idx = text.find(rel)
        assert idx != -1, f"{rel} not mentioned in audit."
        window = text[idx : idx + 400]
        if not verdict_re.search(window):
            missing_verdict.append(rel)
    assert not missing_verdict, (
        f"Audit mentions these sites without a can/cannot verdict nearby: {missing_verdict}"
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


def test_new_and_changed_files_are_tracked():
    files = tracked_files()
    must_be_tracked = [CAPABILITY_AUDIT, EXAMPLE_CONF, CONFIG_MD, PR_CLAUDE_REVIEW, PR_SKILL, *SPAWN_SITES]
    untracked = [f for f in must_be_tracked if f not in files]
    assert not untracked, f"Not tracked by git: {[str(f.relative_to(REPO_ROOT)) for f in untracked]}"
