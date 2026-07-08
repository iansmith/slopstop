"""
Phase 0 red tests for BILL-146 — pr-cr-polling.md missing execution model guidance.

BILL-145 added the Execution model section (criteria 1+2). The remaining gap is
criterion 3: the Timeout handling section does not explain that a ~10-iteration
timeout is caused by running the loop in the foreground — the 10-min Bash tool
cap kills it. Agents hitting a false timeout have no textual signal that background
execution is the fix.

Expected behavior after fix:
1. The Timeout handling section references the 10-minute foreground cap or
   explains that a short-iteration timeout means the loop ran in the foreground.

This test FAILS on current code and turns GREEN once the fix is applied.

Test command:
    python3 -m pytest tests/test_bill146_behaviors.py -v
"""

from pathlib import Path
import pytest

REPO_ROOT = Path(__file__).parent.parent
CR_POLLING = REPO_ROOT / "skills" / "pr" / "references" / "pr-cr-polling.md"


@pytest.fixture(scope="module")
def cr_polling_text():
    return CR_POLLING.read_text()


def test_cr_polling_timeout_section_references_foreground_cap(cr_polling_text):
    """The Timeout handling section must mention the 10-min foreground cap as a failure cause."""
    lower = cr_polling_text.lower()
    timeout_idx = lower.find("timeout handling")
    assert timeout_idx != -1, "No 'Timeout handling' section found in pr-cr-polling.md"
    timeout_section = lower[timeout_idx:]
    has_cap_mention = (
        "10-min" in timeout_section
        or "10 min" in timeout_section
        or "10-minute" in timeout_section
        or ("foreground" in timeout_section and ("cap" in timeout_section or "background" in timeout_section))
    )
    assert has_cap_mention, (
        "The Timeout handling section must reference the 10-minute foreground cap — "
        "agents must understand that a ~10-iteration false timeout means the loop ran "
        "in the foreground, not that CodeRabbit failed to respond."
    )
