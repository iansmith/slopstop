"""
Behavior tests for BILL-271 — fleet-agent + escalation models default from the
tier ladder (honoring version pins).

Context: `:run` hardcoded the fleet-agent launch defaults as raw model strings —
`[fleet.agents].model` defaulted to "haiku" and `[fleet.agents].escalation_model`
to "sonnet" — duplicating what `[tiers].small` / `[tiers].medium` already declare.
BILL-271 makes the fleet defaults DERIVE from the tier ladder: absent
`[fleet.agents]`, the fleet implementation model is resolved from `[tiers].small`
and the capability-escalation model from `[tiers].medium`, each honoring the tier's
optional version pin (family + version -> a model id, e.g. sonnet + "5" ->
claude-sonnet-5; unpinned -> the bare family alias, e.g. haiku). Explicit
`[fleet.agents]` / `[fleet.escalation]` blocks remain overrides that win.

Every assertion below FAILS on the pre-BILL-271 content (which documents the raw
"haiku"/"sonnet" hardcoded defaults with no tier derivation and no version-id rule),
and passes once the skills + docs describe the tier-derived resolution.

Test command:
    python3 -m pytest tests/test_bill271_behaviors.py -v
"""

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent
CONFIG_MD = REPO_ROOT / "CONFIG.md"
OPTIONS = REPO_ROOT / "design" / "project-conf-options.md"
RUN_SKILL = REPO_ROOT / "skills" / "run" / "SKILL.md"
FAILURE = REPO_ROOT / "skills" / "run" / "references" / "run-failure-handling.md"

# The canonical resolution phrases BILL-271 introduces. Fleet model defaults are
# no longer bare "haiku"/"sonnet" literals; they are resolved from the tier ladder.
SMALL_DERIVATION = "resolved from `[tiers].small`"
MEDIUM_DERIVATION = "resolved from `[tiers].medium`"
VERSION_ID_EXAMPLE = "claude-sonnet-5"  # sonnet family + version "5" -> versioned id


@pytest.fixture(scope="module")
def config_md():
    return CONFIG_MD.read_text()


@pytest.fixture(scope="module")
def fleet_agents_section(config_md):
    """The CONFIG.md `### [fleet.agents]` section (up to the next '### ' or '---')."""
    marker = "### `[fleet.agents]`"
    start = config_md.index(marker)
    rest = config_md[start + len(marker):]
    end_candidates = [i for i in (rest.find("\n### "), rest.find("\n---")) if i != -1]
    end = min(end_candidates) if end_candidates else len(rest)
    return rest[:end]


@pytest.fixture(scope="module")
def options():
    return OPTIONS.read_text()


@pytest.fixture(scope="module")
def run_skill():
    return RUN_SKILL.read_text()


@pytest.fixture(scope="module")
def failure_handling():
    return FAILURE.read_text()


# ---------------------------------------------------------------------------
# Behavior 1 — fleet implementation model defaults from [tiers].small
# ---------------------------------------------------------------------------

def test_config_fleet_model_derives_from_small(fleet_agents_section):
    assert SMALL_DERIVATION in fleet_agents_section, (
        "CONFIG.md [fleet.agents] must state the fleet model default is "
        f"{SMALL_DERIVATION} (not a hardcoded \"haiku\")"
    )


def test_run_skill_fleet_model_derives_from_small(run_skill):
    assert SMALL_DERIVATION in run_skill, (
        "skills/run/SKILL.md must document the fleet launch model defaulting to "
        f"the model {SMALL_DERIVATION}"
    )


# ---------------------------------------------------------------------------
# Behavior 2 — escalation model defaults from [tiers].medium
# ---------------------------------------------------------------------------

def test_config_escalation_derives_from_medium(fleet_agents_section):
    assert MEDIUM_DERIVATION in fleet_agents_section, (
        "CONFIG.md [fleet.agents] must state the escalation model default is "
        f"{MEDIUM_DERIVATION} (not a hardcoded \"sonnet\")"
    )


def test_failure_handling_escalation_derives_from_medium(failure_handling):
    assert MEDIUM_DERIVATION in failure_handling, (
        "run-failure-handling.md must document escalation defaulting to the model "
        f"{MEDIUM_DERIVATION}"
    )


# ---------------------------------------------------------------------------
# Behavior 3 — version pins are honored: family + version -> a model id
# ---------------------------------------------------------------------------

def test_version_id_construction_documented(config_md, run_skill):
    """A version-pinned tier yields a versioned model id (sonnet+5 -> claude-sonnet-5)."""
    assert VERSION_ID_EXAMPLE in config_md or VERSION_ID_EXAMPLE in run_skill, (
        f"The version-id construction rule ({VERSION_ID_EXAMPLE}) must be documented "
        "in CONFIG.md or skills/run/SKILL.md"
    )


def test_unpinned_family_alias_documented(fleet_agents_section):
    """An unpinned tier resolves to the bare family alias (e.g. haiku)."""
    assert "unpinned" in fleet_agents_section, (
        "CONFIG.md [fleet.agents] must document the unpinned-tier -> family-alias case"
    )


# ---------------------------------------------------------------------------
# Behavior 4 — explicit [fleet.agents]/[fleet.escalation] overrides still win
# ---------------------------------------------------------------------------

def test_explicit_override_still_wins(fleet_agents_section):
    assert "override" in fleet_agents_section.lower(), (
        "CONFIG.md [fleet.agents] must document that an explicit value overrides the "
        "tier-derived default"
    )


# ---------------------------------------------------------------------------
# Behavior 5 (docs) — the design-layer options doc reflects tier derivation
# ---------------------------------------------------------------------------

def test_options_doc_reflects_tier_derivation(options):
    assert MEDIUM_DERIVATION in options or SMALL_DERIVATION in options, (
        "design/project-conf-options.md must document the tier-derived fleet defaults "
        "(it previously said fleet implementation 'stays small via [fleet.agents].model')"
    )
