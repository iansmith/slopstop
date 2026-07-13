"""
Phase 0 red tests for BILL-196 — extend the design-layer config reference
with [tiers] and [fleet.*].

BILL-165 added the five v3 tables to .project-conf.toml.example and CONFIG.md
but not to the durable design-layer docs, so the two layers disagreed about
the schema surface (caught by BILL-165's review, spun off as this ticket).

Expected behaviors:
1. design/project-conf-options.md documents all five tables.
2. design/project-conf-toml.md's optionality table lists them.
3. Sampled defaults in the options doc match .project-conf.toml.example
   (CONFIG.md/example are the source of truth) so the layers can't silently
   diverge again.

Test command:
    python3 -m pytest tests/test_bill196_behaviors.py -v
"""

import tomllib
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent
OPTIONS = REPO_ROOT / "design" / "project-conf-options.md"
CONF_TOML_DOC = REPO_ROOT / "design" / "project-conf-toml.md"
EXAMPLE = REPO_ROOT / ".project-conf.toml.example"

FIVE_TABLES = ("[tiers]", "[fleet.agents]", "[fleet.monitoring]",
               "[fleet.budget]", "[fleet.router]")


@pytest.fixture(scope="module")
def options():
    return OPTIONS.read_text()


@pytest.fixture(scope="module")
def conf_doc():
    return CONF_TOML_DOC.read_text()


def test_options_doc_covers_five_tables(options):
    for table in FIVE_TABLES:
        assert table in options, f"project-conf-options.md must document {table}"


def test_optionality_table_covers_five_tables(conf_doc):
    for row in ("[tiers].*", "[fleet.agents].*", "[fleet.monitoring].*",
                "[fleet.budget].*", "[fleet.router].*"):
        assert row in conf_doc, (
            f"project-conf-toml.md's optionality table must list {row}"
        )


def _options_doc_defaults(options):
    """Parse the five table blocks out of the options doc into one config dict.

    Binds by value, not substring: the ```toml blocks under the five headings
    carry the doc's advertised defaults, so parsing them lets us compare the
    doc layer against the example layer key-for-key.
    """
    blocks = []
    for heading in ("## `[tiers]`", "## `[fleet.agents]`",
                    "## `[fleet.monitoring]`", "## `[fleet.budget]`",
                    "## `[fleet.router]`"):
        start = options.index(heading)
        fence = options.index("```toml", start) + len("```toml")
        end = options.index("```", fence)
        blocks.append(options[fence:end])
    return tomllib.loads("\n".join(blocks))


def test_options_defaults_match_example(options):
    """Sampled defaults in the options doc must equal the example TOML (source of truth).

    Both layers are parsed and compared by value, so a drifted default on
    *either* side — the example or the doc — fails the assertion.
    """
    example = tomllib.loads(EXAMPLE.read_text())
    doc = _options_doc_defaults(options)
    sampled = (
        ("tiers", "huge", "model"),                      # nested string
        ("fleet", "agents", "escalation_model"),  # string
        ("fleet", "monitoring", "silence_kill_min"),  # int
        ("fleet", "budget", "max_ticket_versions"),   # int
        ("fleet", "router", "enabled"),           # bool
    )
    for path in sampled:
        ex = example
        doc_val = doc
        for key in path:
            ex = ex[key]
            doc_val = doc_val[key]
        assert doc_val == ex, (
            f"project-conf-options.md default for {'.'.join(path)} "
            f"({doc_val!r}) must match the example TOML ({ex!r})"
        )
