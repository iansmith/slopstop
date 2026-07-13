"""
Phase 0 red tests for BILL-165 — Config schema: [tiers], [fleet.agents],
[fleet.monitoring], [fleet.budget], [fleet.router].

The v3 four-tier process (PRD: docs/prd-slopstop-v3-agent-process.md, umbrella
#162) needs five new config tables. This ticket adds them to
.project-conf.toml.example with the agreed defaults and documents them in
CONFIG.md — no skill consumes them yet.

Expected behaviors:
1. .project-conf.toml.example parses as valid TOML.
2. [tiers] table present with huge=fable, large=opus, medium=sonnet, small=haiku.
3. [fleet.agents] with model=haiku, effort=medium, adversary_effort=high,
   escalation_model=sonnet.
4. [fleet.monitoring] with poll_interval_min=5, quiet_investigate_min=15,
   silence_kill_min=30, loop_kill_reports=3, filemap_violation="kill".
5. [fleet.budget] with max_attempts_per_version=3, max_ticket_versions=3,
   max_tier_escalations=1.
6. [fleet.router] with enabled=false.
7. CONFIG.md documents each table (as a heading with a key table), the
   filemap_violation "warn" testing mode, and the defensive resolution rule
   (absent keys -> defaults; missing tables never error).

Assertions check that the required keys hold the agreed defaults (subset
semantics — future tickets may add keys to these tables without breaking
BILL-165's pins).

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


def _config_md_section(config_md, table):
    """Slice CONFIG.md to the documentation section for one config table."""
    heading = f"### `{table}`"
    start = config_md.find(heading)
    assert start != -1, f"CONFIG.md must have a '{heading}' section heading"
    end = config_md.find("\n### ", start + 1)
    return config_md[start:end] if end != -1 else config_md[start:]


def _assert_subset(actual, required, table):
    """Assert every required key is present with the agreed default value."""
    assert actual is not None, f"{table} table must exist in .project-conf.toml.example"
    for key, value in required.items():
        assert actual.get(key) == value, (
            f"{table}.{key} must default to {value!r}, got {actual.get(key)!r}"
        )


def test_example_parses_as_toml():
    """.project-conf.toml.example must parse as valid TOML."""
    tomllib.loads(EXAMPLE.read_text())


def test_tiers_table(conf):
    """[tiers] must have nested tables huge/large/medium/small with provider and model."""
    tiers = conf.get("tiers")
    assert tiers is not None, "[tiers] table must exist"
    for tier_name, (provider, model) in [
        ("huge", ("anthropic", "fable")),
        ("large", ("anthropic", "opus")),
        ("medium", ("anthropic", "sonnet")),
        ("small", ("anthropic", "haiku")),
    ]:
        tier_config = tiers.get(tier_name)
        assert tier_config is not None, f"[tiers.{tier_name}] must exist"
        assert isinstance(tier_config, dict), f"[tiers.{tier_name}] must be a table"
        assert tier_config.get("provider") == provider, (
            f"[tiers.{tier_name}].provider must be {provider!r}, "
            f"got {tier_config.get('provider')!r}"
        )
        assert tier_config.get("model") == model, (
            f"[tiers.{tier_name}].model must be {model!r}, "
            f"got {tier_config.get('model')!r}"
        )


def test_fleet_agents_table(conf):
    """[fleet.agents] defaults must match the model/effort/escalation settings."""
    _assert_subset(conf.get("fleet", {}).get("agents"), {
        "model": "haiku",
        "effort": "medium",
        "adversary_effort": "high",
        "escalation_model": "sonnet",
    }, "[fleet.agents]")


def test_fleet_monitoring_table(conf):
    """[fleet.monitoring] must ship the poll-loop and kill-trigger defaults."""
    _assert_subset(conf.get("fleet", {}).get("monitoring"), {
        "poll_interval_min": 5,
        "quiet_investigate_min": 15,
        "silence_kill_min": 30,
        "loop_kill_reports": 3,
        "filemap_violation": "kill",
    }, "[fleet.monitoring]")


def test_fleet_budget_table(conf):
    """[fleet.budget] must ship the attempt/version/escalation caps."""
    _assert_subset(conf.get("fleet", {}).get("budget"), {
        "max_attempts_per_version": 3,
        "max_ticket_versions": 3,
        "max_tier_escalations": 1,
    }, "[fleet.budget]")


def test_fleet_router_table(conf):
    """[fleet.router] must exist and ship enabled=false (zero-infrastructure default)."""
    _assert_subset(conf.get("fleet", {}).get("router"), {
        "enabled": False,
    }, "[fleet.router]")


def test_config_md_documents_each_table(config_md):
    """CONFIG.md must document each new table as its own section with a key table."""
    for table in ("[tiers]", "[fleet.agents]", "[fleet.monitoring]",
                  "[fleet.budget]", "[fleet.router]"):
        section = _config_md_section(config_md, table)
        assert "| Key | Type | Default |" in section, (
            f"CONFIG.md's {table} section must include a key reference table"
        )


def test_config_md_documents_warn_mode(config_md):
    """CONFIG.md's [fleet.monitoring] section must document the warn testing mode."""
    section = _config_md_section(config_md, "[fleet.monitoring]")
    assert '"warn"' in section and "filemap_violation" in section, (
        "The [fleet.monitoring] section itself must document the "
        'filemap_violation "warn" mode for process testing'
    )


def test_config_md_documents_resolution_rule(config_md):
    """CONFIG.md's [tiers] section must state the defensive resolution rule."""
    section = _config_md_section(config_md, "[tiers]")
    lowered = section.lower()
    assert "missing key" in lowered and "default" in lowered and "never error" in lowered, (
        "The [tiers] section must state the resolution rule that governs it and "
        "every [fleet.*] table: a missing key resolves to its documented default; "
        "a missing table never errors"
    )


def test_config_md_documents_omitted_version_means_any(config_md):
    """CONFIG.md's [tiers] section must state that an omitted version resolves
    to any version of the family, not a pinned one."""
    section = _config_md_section(config_md, "[tiers]")
    assert "any version" in section.lower(), (
        "The [tiers] section must state that an omitted `version` key resolves "
        "to any version of the model family"
    )


def test_config_md_documents_url_absence(config_md):
    """CONFIG.md's [tiers] section must explain that `url` is intentionally
    absent from the schema because gating never dials an endpoint."""
    section = _config_md_section(config_md, "[tiers]")
    assert "url" in section.lower(), (
        "The [tiers] section must document that `url` is absent from the "
        "schema because gating never dials an endpoint"
    )
