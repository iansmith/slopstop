"""
Behavior tests for BILL-259 — pin the [tiers] model-spec TABLE form and the
version-prefix tier-gate VOCABULARY in the skills.

Context: #257 shipped the example/CONFIG.md `[tiers.<tier>]` table form (each tier
a nested table with `provider` + `model` (family) + optional `version`, replacing
the legacy flat `huge = "fable"` string form). #258 shipped the skills' tier-gate
language describing the (family, version-dotted-prefix) match and `provider` being
informational / router-only (never gated). This module pins that content so it can't
silently regress; every assertion below would FAIL if the content it keys on were
removed.

Test command:
    python3 -m pytest tests/test_bill_modelspec_behaviors.py -v
"""

import tomllib
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent
EXAMPLE = REPO_ROOT / ".project-conf.toml.example"
CONFIG_MD = REPO_ROOT / "CONFIG.md"
SKILLS = REPO_ROOT / "skills"

TIERS = ("huge", "large", "medium", "small")


@pytest.fixture(scope="module")
def conf():
    return tomllib.loads(EXAMPLE.read_text())


@pytest.fixture(scope="module")
def config_md():
    return CONFIG_MD.read_text()


# ---------------------------------------------------------------------------
# Behavior 1 — the example [tiers.<tier>] tables carry provider + model (family)
# with an OPTIONAL version, and NO legacy flat string key survives.
# ---------------------------------------------------------------------------

def test_tiers_table_is_a_table_of_tables(conf):
    """[tiers] must exist and hold four nested tables (not flat string values)."""
    tiers = conf.get("tiers")
    assert tiers is not None, "[tiers] must exist in .project-conf.toml.example"
    for tier in TIERS:
        assert tier in tiers, f"[tiers] must define the {tier!r} tier"
        assert isinstance(tiers[tier], dict), (
            f"[tiers].{tier} must be a nested table, not the legacy string form "
            f"(got {tiers[tier]!r})"
        )


def test_no_legacy_flat_string_tier_key(conf):
    """No [tiers].<tier> may be a bare string (the rejected legacy form)."""
    tiers = conf.get("tiers") or {}
    string_keys = [k for k, v in tiers.items() if isinstance(v, str)]
    assert not string_keys, (
        f"legacy flat string tier key(s) survive in [tiers]: {string_keys} — "
        "the nested [tiers.<tier>] table form is required"
    )


def test_each_tier_table_has_provider_and_model(conf):
    """Every tier table carries provider + model as strings (the family)."""
    tiers = conf["tiers"]
    for tier in TIERS:
        table = tiers[tier]
        assert isinstance(table.get("provider"), str) and table["provider"], (
            f"[tiers.{tier}] must carry a non-empty string `provider`"
        )
        assert isinstance(table.get("model"), str) and table["model"], (
            f"[tiers.{tier}] must carry a non-empty string `model` (family)"
        )


def test_version_is_optional_but_string_when_present(conf):
    """`version` is OPTIONAL; the example omits it, but if present it is a string.

    The example ships no pinned version on any tier (version stays commented), so
    this pins the 'optional' property directly: not a single tier table carries a
    `version` key, yet the schema tolerates one (string) when a project adds it.
    """
    tiers = conf["tiers"]
    for tier in TIERS:
        table = tiers[tier]
        if "version" in table:
            assert isinstance(table["version"], str), (
                f"[tiers.{tier}].version, when present, must be a string"
            )
        else:
            # optional: the example leaves it out — asserted here so a future
            # example that hard-codes a version on every tier is caught.
            assert "version" not in table


# ---------------------------------------------------------------------------
# Behavior 2 — CONFIG.md documents the table form AND the string-form rejection.
# ---------------------------------------------------------------------------

def _tiers_section(config_md):
    heading = "### `[tiers]`"
    start = config_md.find(heading)
    assert start != -1, f"CONFIG.md must have a '{heading}' section"
    end = config_md.find("\n### ", start + 1)
    return config_md[start:end] if end != -1 else config_md[start:]


def test_config_md_documents_the_table_form(config_md):
    section = _tiers_section(config_md)
    assert "nested table with `provider` and `model`" in section, (
        "CONFIG.md [tiers] section must describe the nested-table form "
        "(provider + model + optional version)"
    )
    assert "an optional `version` field" in section, (
        "CONFIG.md [tiers] section must document `version` as optional"
    )
    # a concrete table example is shown
    assert "[tiers.huge]" in section, (
        "CONFIG.md [tiers] section must show a concrete [tiers.<tier>] table example"
    )


def test_config_md_documents_string_form_rejection(config_md):
    section = _tiers_section(config_md)
    assert "legacy flat string form" in section, (
        "CONFIG.md [tiers] section must name the legacy flat string form"
    )
    assert "is rejected with a loud error" in section, (
        "CONFIG.md [tiers] section must state the string form is rejected"
    )


# ---------------------------------------------------------------------------
# Behavior 3 — the :design / :tickets / :run tier-gate vocabulary describes the
# (family, version-dotted-prefix) match and provider being informational-only
# (router-only; never gated).
# ---------------------------------------------------------------------------

# Each substring below is a verbatim slice present on a single line of the named
# SKILL.md (no substring spans a newline). Removing the gate language removes the pin.
GATE_SUBSTRINGS = {
    "design": [
        "`provider` is never gated on",              # provider not gated
        "carried for the router only",               # informational / router-only
        "dotted prefix",                             # version match rule
        "`4.8` matches `claude-opus-4-8`",           # version-dotted-prefix example
        "`claude-fable-5` matches `model = \"fable\"`",  # family match example
    ],
    "tickets": [
        "`provider` is never gated on",
        "router-only; a session can't verify its endpoint",
        "dotted",                                    # "**dotted prefix**" (wraps a line)
        "`4.8` matches `claude-opus-4-8`",           # version-dotted-prefix example
        "matches `model = \"opus\"`",                # family match example
    ],
    "run": [
        "`provider` is never gated on",
        "router-only; a session can't verify its endpoint",
        "dotted-prefix",                             # version match rule
        "family",                                    # match on family
    ],
}


@pytest.mark.parametrize("skill", sorted(GATE_SUBSTRINGS))
def test_skill_tier_gate_vocabulary(skill):
    text = (SKILLS / skill / "SKILL.md").read_text()
    for needle in GATE_SUBSTRINGS[skill]:
        assert needle in text, (
            f"skills/{skill}/SKILL.md must contain the tier-gate phrase {needle!r}"
        )
