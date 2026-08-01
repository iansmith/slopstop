"""
The residual-marker scan in tools/fleet-sync/migrate-universal-block.py.

`--verify` is what CLAUDE.md tells maintainers to run as the fleet health check, so
a false positive there is not cosmetic: it makes a correct fleet look broken, and a
check that cries wolf stops being read.

The scan matched the loose substring "UNIVERSAL SECTION", which hits any prose that
merely *mentions* the retired markers — including slopstop's own CLAUDE.md, which
deliberately documents them in its "why a whole file, not a marked region" scar. The
module already defines the two exact marker comments as BEGIN and END; the scan must
use those, not a substring of them.
"""

import importlib.util
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent
FLEET_DIR = REPO_ROOT / "tools" / "fleet-sync"
SCRIPT = FLEET_DIR / "migrate-universal-block.py"


@pytest.fixture(scope="module")
def mod():
    if not SCRIPT.is_file():
        pytest.fail(f"{SCRIPT} does not exist")
    # The script imports its sibling `fleet` module, which is only importable with
    # its own directory on the path — it is run as a script, never as a package.
    sys.path.insert(0, str(FLEET_DIR))
    try:
        spec = importlib.util.spec_from_file_location("migrate_universal_block", SCRIPT)
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        return m
    finally:
        sys.path.remove(str(FLEET_DIR))


def test_live_markers_are_reported(mod):
    text = "\n".join(["# Rules", mod.BEGIN, "body", mod.END, "tail"])
    assert mod.marker_lines(text) == [2, 4], (
        "a CLAUDE.md still carrying the marked region is the thing this scan exists "
        "to find; reporting it is the whole point"
    )


def test_prose_mentioning_the_markers_is_not_reported(mod):
    # The exact sentence in slopstop's own CLAUDE.md.
    text = "delimited by `<!-- BEGIN/END UNIVERSAL SECTION -->` markers. That design"
    assert mod.marker_lines(text) == [], (
        "a documented mention of the retired markers is not a live marked region. "
        "Flagging it makes --verify report a false problem on the reference repo "
        "itself, every single run, forever."
    )


def test_the_scan_uses_the_modules_own_marker_constants(mod):
    """One definition per value — the scan must not carry its own copy."""
    for marker in (mod.BEGIN, mod.END):
        assert mod.marker_lines(marker) == [1]
    assert mod.marker_lines("UNIVERSAL SECTION") == [], (
        "matching a substring of the marker rather than the marker is exactly the "
        "bug; the constants are already defined for bounds() to use"
    )
