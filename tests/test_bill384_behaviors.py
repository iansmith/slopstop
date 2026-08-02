"""
Phase 0 red test for BILL-384 — price the current tiers in router/prices.toml
and correct router/README.md's stale rate-basis note.

Transcribed from the ticket's Test expectations
(https://github.com/iansmith/slopstop/issues/384). Transcription, not
authorship: every assertion below is pinned by the ticket, and per the fleet
brief's hard constraint 9 the implementer may not renegotiate it. If it is
wrong, the sanctioned exit is the TICKET UNDERSPECIFIED halt (TD-4a), not an
edit to this file.

Composition rule (per the ticket, do not change): the expected model ids are
BUILT from `.project-conf.toml`'s `[tiers.<tier>]` tables, not looked up —
`claude-<model>-<version>` with dots in `version` replaced by hyphens. This is
the durable form of the defect: pinning only `claude-opus-5` literally would
let the same gap reopen at the next model bump.

The test resolves both TOML files via REPO_ROOT (derived from __file__), so
it stays correct when invoked with a relative path from a different cwd —
e.g. `python3 -m pytest ../tests/ -q` run with cwd=<repo>/tests.

Test command:
    python3 -m pytest tests/test_bill384_behaviors.py -v
"""

import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
PROJECT_CONF = REPO_ROOT / ".project-conf.toml"
PRICES_TOML = REPO_ROOT / "router" / "prices.toml"


def _expected_model_ids() -> set[str]:
    conf = tomllib.loads(PROJECT_CONF.read_text())
    tiers = conf["tiers"]
    ids = set()
    for tier_table in tiers.values():
        model = tier_table["model"]
        version = tier_table["version"].replace(".", "-")
        ids.add(f"claude-{model}-{version}")
    return ids


def test_prices_toml_has_a_row_for_every_tier_model() -> None:
    expected_ids = _expected_model_ids()
    prices = tomllib.loads(PRICES_TOML.read_text())
    priced_ids = set(prices["models"].keys())

    missing = expected_ids - priced_ids
    assert not missing, (
        f"router/prices.toml is missing a row for: {sorted(missing)} — "
        f"every model named in .project-conf.toml's [tiers] tables must be "
        f"priced, or metering silently reports $0 for it."
    )
