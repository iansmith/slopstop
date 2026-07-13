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


def test_config_md_documents_stage_tiers(config_md):
    """CONFIG.md must have a '### `[stage_tiers]`' section with a key reference table."""
    heading = "### `[stage_tiers]`"
    start = config_md.find(heading)
    assert start != -1, f"CONFIG.md must have a '{heading}' section"
    end = config_md.find("\n### ", start + 1)
    section = config_md[start:end] if end != -1 else config_md[start:]
    assert "| Key | Type | Default |" in section, (
        "the [stage_tiers] section must include a key reference table"
    )
    # every stage/check key is documented
    for key in LADDER:
        assert key in section, f"CONFIG.md [stage_tiers] section must document {key!r}"


def test_skills_resolve_via_stage_tiers(conf):
    """Each gate/spawn in the skills resolves via [stage_tiers].<key> — no stage or
    check still hardcodes a bare [tiers].<tier>. (Fleet-impl [tiers].small and the
    fleet escalation [tiers].medium in prose are exempt — they are the
    [fleet.agents].model / escalation_model tiers, not [stage_tiers] keys. BILL-271
    ties both to the tier ladder; the exemption is scoped to lines in a fleet or
    escalation context, so it can't silence the guard on a real stage-gate hardcode.)"""
    offenders = []
    for md in SKILLS.rglob("*.md"):
        text = md.read_text()
        for m in re.finditer(r"\[tiers\]\.(huge|large|medium)\b", text):
            # A reference is exempt when its surrounding context is a [stage_tiers]
            # resolution (the "→ [tiers].<that tier>" model hop) or a fleet/escalation
            # default (BILL-271 resolves fleet model/escalation from the tier ladder).
            # Scope the check to a window, not the physical line: markdown prose wraps,
            # so the marker can sit on an adjacent wrapped line within the same sentence.
            # Match SPECIFIC config-key tokens ("[fleet.", "escalation_model"), never the
            # bare substrings "fleet"/"escalat" — otherwise an incidental mention
            # (fleet-state.md, a "## Tier escalation" heading) would shield a genuine
            # stage-gate hardcode of a bare [tiers].<tier> nearby.
            window = text[max(0, m.start() - 150):m.end() + 40].lower()
            exempt = any(tok in window for tok in
                         ("stage_tiers", "<that tier>", "[fleet.", "escalation_model"))
            if not exempt:
                line = text[text.rfind("\n", 0, m.start()) + 1:
                            text.find("\n", m.end())]
                offenders.append(f"{md.relative_to(REPO_ROOT)}: {line.strip()[:80]}")
    assert not offenders, (
        "these skill lines still hardcode a tier instead of resolving via "
        "[stage_tiers]:\n" + "\n".join(offenders)
    )
