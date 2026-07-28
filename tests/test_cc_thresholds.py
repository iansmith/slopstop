"""
Behavior tests for the :pr CC gate's thresholds and comparison semantics.

Both thresholds are **inclusive lower bounds**:

    CC >= cc_reject_threshold                    -> 🔴 violation (hard-gate)
    cc_warn_threshold <= CC < cc_reject_threshold -> 🟡 elevated (warning)

Defaults: warn 5, reject 10. So 5–9 inclusive warns and 10-or-above rejects.

The inclusive form matters as much as the numbers. Under the previous exclusive
semantics (`CC > reject`, `warn < CC <= reject`) a reject threshold of 10 would have
let CC 10 through, and the config value would not have meant what it says.

Test command:
    python3 -m pytest tests/test_cc_thresholds.py -v
"""

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent
CC_GATE = REPO_ROOT / "skills" / "pr" / "references" / "pr-cc-gate.md"
CONFIG_MD = REPO_ROOT / "CONFIG.md"
CONF_OPTIONS = REPO_ROOT / "design" / "project-conf-options.md"
TEST_GATES = REPO_ROOT / "skills" / "pr" / "references" / "pr-test-gates.md"

WARN_DEFAULT = 5
REJECT_DEFAULT = 10


@pytest.fixture(scope="module")
def cc_gate() -> str:
    return CC_GATE.read_text()


def test_gate_defaults_are_five_and_ten(cc_gate: str) -> None:
    """The gate's own defaults are the source of truth for the thresholds."""
    warn = re.search(r"cc_warn_threshold.*?default:\s*\*\*(\d+)\*\*", cc_gate)
    reject = re.search(r"cc_reject_threshold.*?default:\s*\*\*(\d+)\*\*", cc_gate)
    assert warn and reject, "pr-cc-gate.md must state both defaults"
    assert int(warn.group(1)) == WARN_DEFAULT, (
        f"cc_warn_threshold default should be {WARN_DEFAULT}, got {warn.group(1)}"
    )
    assert int(reject.group(1)) == REJECT_DEFAULT, (
        f"cc_reject_threshold default should be {REJECT_DEFAULT}, got {reject.group(1)}"
    )


def test_reject_comparison_is_inclusive(cc_gate: str) -> None:
    """CC == cc_reject_threshold must be a 🔴, not a pass.

    Asserted on the classification line specifically. A whole-file search for `>=`
    would pass on any unrelated comparison elsewhere in the file.
    """
    line = next(
        (l for l in cc_gate.split("\n") if "cc_reject_threshold" in l and "🔴" in l), ""
    )
    assert line, "pr-cc-gate.md has no 🔴 classification line"
    assert re.search(r"(>=|≥)\s*`?cc_reject_threshold", line), (
        "the 🔴 rule must be `CC >= cc_reject_threshold`. With the old exclusive "
        f"form (`CC > threshold`), a threshold of {REJECT_DEFAULT} would let "
        f"CC={REJECT_DEFAULT} pass — the exact value the config says to reject"
    )


def test_warn_band_is_inclusive_lower_exclusive_upper(cc_gate: str) -> None:
    """The 🟡 band is [warn, reject) — 5..9 at the defaults."""
    line = next(
        (l for l in cc_gate.split("\n") if "cc_warn_threshold" in l and "🟡" in l), ""
    )
    assert line, "pr-cc-gate.md has no 🟡 classification line"
    assert re.search(r"`?cc_warn_threshold`?\s*(<=|≤)", line), (
        "the 🟡 band must include its lower bound, so CC == cc_warn_threshold warns"
    )
    assert re.search(r"<\s*`?cc_reject_threshold", line), (
        "the 🟡 band must exclude its upper bound — CC == cc_reject_threshold is a "
        "🔴, and a value cannot be both"
    )


def test_report_format_matches_the_comparisons(cc_gate: str) -> None:
    """The human-facing report must not contradict the rule it reports on.

    The band labels are what a reader trusts when triaging a gate failure; if they
    still say `CC > T` while the rule says `CC >= T`, the report is lying about a
    boundary case.
    """
    assert "CC > T" not in cc_gate, (
        "report header still labels 🔴 as 'CC > T' — the rule is now CC >= T"
    )
    assert "W < CC" not in cc_gate, (
        "report header still labels 🟡 as 'W < CC ≤ T' — the band is now W <= CC < T"
    )


@pytest.mark.parametrize("doc", [CONFIG_MD, CONF_OPTIONS, TEST_GATES])
def test_docs_agree_with_the_gate(doc: Path) -> None:
    """One definition per value: every doc stating the defaults must agree.

    `pr-test-gates.md` joined this list in BILL-340. It was missed by 747c87e's
    retune and sat at the old 10/15 — the three surfaces are only kept in step by
    checking them through one mechanism, so a fourth surface is added here rather
    than given its own bespoke assertion.
    """
    text = doc.read_text()
    assert re.search(rf"cc_warn_threshold[^\n]*\b{WARN_DEFAULT}\b", text), (
        f"{doc.name} does not document cc_warn_threshold = {WARN_DEFAULT}"
    )
    assert re.search(rf"cc_reject_threshold[^\n]*\b{REJECT_DEFAULT}\b", text), (
        f"{doc.name} does not document cc_reject_threshold = {REJECT_DEFAULT}"
    )
    assert "15" not in re.findall(r"cc_reject_threshold[^\n]*", text)[0], (
        f"{doc.name} still carries the old reject default of 15"
    )
