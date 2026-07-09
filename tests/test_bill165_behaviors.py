"""
Phase 0 red tests for BILL-165 — Config schema: [tiers], [fleet.agents],
[fleet.monitoring], [fleet.budget], [fleet.router].

The v3 three-tier process (PRD: docs/prd-slopstop-v3-agent-process.md, umbrella
#162) needs five new config tables. This ticket adds them to
.project-conf.toml.example with the agreed defaults and documents them in
CONFIG.md — no skill consumes them yet.

Expected behaviors:
1. .project-conf.toml.example parses as valid TOML.
2. [tiers] table present with big=fable, medium=opus, small=haiku.
3. [fleet.agents] with model=haiku, effort=medium, adversary_effort=high,
   escalation_model=sonnet.
4. [fleet.monitoring] with poll_interval_min=5, quiet_investigate_min=15,
   silence_kill_min=30, loop_kill_reports=3, filemap_violation="kill".
5. [fleet.budget] with max_attempts_per_version=3, max_ticket_versions=3,
   max_tier_escalations=1.
6. [fleet.router] with enabled=false.
7. CONFIG.md documents each table, the filemap_violation "warn" testing mode,
   and the defensive resolution rule (absent keys -> defaults; missing tables
   never error).

These tests FAIL on current code and turn GREEN once the schema lands.

Test command:
    python3 -m pytest tests/test_bill165_behaviors.py -v
"""

import tomllib
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent
EXAMPLE = REPO_ROOT / ".project-conf.toml.example"
CONFIG_MD = REPO_ROOT / "CONFIG.md"


@pytest.fixture(scope="module")
def conf():
    return tomllib.loads(EXAMPLE.read_text())


@pytest.fixture(scope="module")
def config_md():
    return CONFIG_MD.read_text()


def test_example_parses_as_toml():
    """.project-conf.toml.example must parse as valid TOML."""
    tomllib.loads(EXAMPLE.read_text())


def test_tiers_table(conf):
    """[tiers] must map big/medium/small to fable/opus/haiku."""
    assert conf.get("tiers") == {
        "big": "fable",
        "medium": "opus",
        "small": "haiku",
    }, "[tiers] must map big/medium/small to fable/opus/haiku"


def test_fleet_agents_table(conf):
    """[fleet.agents] defaults must match the model/effort/escalation settings."""
    agents = conf.get("fleet", {}).get("agents")
    assert agents == {
        "model": "haiku",
        "effort": "medium",
        "adversary_effort": "high",
        "escalation_model": "sonnet",
    }, "[fleet.agents] defaults must match PRD §3/§7"


def test_fleet_monitoring_table(conf):
    """[fleet.monitoring] must ship the poll-loop and kill-trigger defaults."""
    monitoring = conf.get("fleet", {}).get("monitoring")
    assert monitoring == {
        "poll_interval_min": 5,
        "quiet_investigate_min": 15,
        "silence_kill_min": 30,
        "loop_kill_reports": 3,
        "filemap_violation": "kill",
    }, "[fleet.monitoring] defaults must match PRD §7"


def test_fleet_budget_table(conf):
    """[fleet.budget] must ship the attempt/version/escalation caps."""
    budget = conf.get("fleet", {}).get("budget")
    assert budget == {
        "max_attempts_per_version": 3,
        "max_ticket_versions": 3,
        "max_tier_escalations": 1,
    }, "[fleet.budget] defaults must match PRD §7 (3 attempts x 3 versions x 1 escalation)"


def test_fleet_router_table(conf):
    """[fleet.router] must exist and ship enabled=false (zero-infrastructure default)."""
    router = conf.get("fleet", {}).get("router")
    assert router is not None, "[fleet.router] table must exist"
    assert router.get("enabled") is False, (
        "[fleet.router] must ship enabled=false — the zero-infrastructure default"
    )


def test_config_md_documents_each_table(config_md):
    """CONFIG.md must document each of the five new config tables."""
    for section in ("[tiers]", "[fleet.agents]", "[fleet.monitoring]",
                    "[fleet.budget]", "[fleet.router]"):
        assert section in config_md, f"CONFIG.md must document {section}"


def test_config_md_documents_warn_mode(config_md):
    """CONFIG.md must document the filemap_violation warn mode for process testing."""
    assert '"warn"' in config_md and "filemap_violation" in config_md, (
        "CONFIG.md must document the filemap_violation warn mode for process testing"
    )


def test_config_md_documents_resolution_rule(config_md):
    """CONFIG.md must state the defensive resolution rule (absent keys -> defaults; missing tables never error)."""
    lowered = config_md.lower()
    assert "missing" in lowered and "default" in lowered and "never error" in lowered, (
        "CONFIG.md must state the defensive resolution rule: absent keys resolve to "
        "defaults; missing tables never error"
    )
