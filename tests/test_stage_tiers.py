"""
Behavior tests for [stage_tiers] — declarative stage→tier mapping.

Design: docs/stage-tiers-table-design.md (follow-on to the four-tier recalibration,
umbrella #237). [tiers] maps tier→model; [stage_tiers] maps each stage/check→a tier.
Resolution is two hops (stage→tier→model), so re-tiering a stage is a one-line config
edit instead of a skill rewrite.

These tests pin: the table's presence + ladder defaults, stage_tier→tier referential
integrity, that CONFIG.md documents it, and that the skills resolve via [stage_tiers]
(no skill still hardcodes a bare [tiers].<tier> for a stage/check).

Test command:
    python3 -m pytest tests/test_stage_tiers.py -v
"""

import re
import tomllib
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent
EXAMPLE = REPO_ROOT / ".project-conf.toml.example"
CONFIG_MD = REPO_ROOT / "CONFIG.md"
SKILLS = REPO_ROOT / "skills"

# The settled "checker one tier above the doer" ladder.
LADDER = {
    "design": "huge",
    "tickets": "large",
    "run": "medium",
    "ticket_adversary": "huge",
    "rewrite_delta_check": "huge",
    "drift_check": "large",
    "handoff_verifier": "medium",
    "report_adversary": "huge",
}


@pytest.fixture(scope="module")
def conf():
    return tomllib.loads(EXAMPLE.read_text())


@pytest.fixture(scope="module")
def config_md():
    return CONFIG_MD.read_text()


def test_stage_tiers_table_present_with_ladder_defaults(conf):
    """[stage_tiers] must map every stage/check to its ladder tier."""
    st = conf.get("stage_tiers")
    assert st is not None, "[stage_tiers] must exist in .project-conf.toml.example"
    for key, tier in LADDER.items():
        assert st.get(key) == tier, (
            f"[stage_tiers].{key} must default to {tier!r}, got {st.get(key)!r}"
        )


def test_stage_tier_values_are_valid_tiers(conf):
    """Every [stage_tiers] value must name a tier defined in [tiers] — otherwise the
    stage→tier→model resolution dangles."""
    tiers = conf.get("tiers") or {}
    st = conf.get("stage_tiers") or {}
    for key, tier in st.items():
        assert tier in tiers, (
            f"[stage_tiers].{key} = {tier!r} is not a tier in [tiers] "
            f"({sorted(tiers)}) — the stage→tier→model resolution would dangle"
        )


