"""
Phase 0 red tests for BILL-145 — Step 6-cr poll loop exceeds Bash tool timeout.

The polling shell script in pr-cr-polling.md runs `sleep 60` inside a 20-iteration
loop (20 min total). The Bash tool has a 10-min hard cap, so the loop times out
before CodeRabbit responds. The fix: document and implement background execution
with a status-file protocol so the poll runs outside the foreground Bash timeout.

Expected behaviors after fix:
1. pr-cr-polling.md mentions run_in_background (background execution required)
2. pr-cr-polling.md documents a status file to pass the verdict back to the agent
3. pr-cr-polling.md instructs agents NOT to run the loop in the foreground
4. pr-cr-polling.md documents a timeout value for the background command
   (must be >= 1200000ms to cover the full 20-iteration window)

These tests FAIL on current code and turn GREEN once the fix is applied.

Test command:
    python3 -m pytest tests/test_bill145_behaviors.py -v
"""

from pathlib import Path
import re
import pytest

REPO_ROOT = Path(__file__).parent.parent
CR_POLLING = REPO_ROOT / "skills" / "pr" / "references" / "pr-cr-polling.md"


@pytest.fixture(scope="module")
def cr_polling_text():
    return CR_POLLING.read_text()


def test_cr_polling_mentions_run_in_background(cr_polling_text):
    """The doc must instruct agents to use run_in_background: true for the poll loop."""
    assert "run_in_background" in cr_polling_text, (
        "pr-cr-polling.md must mention run_in_background — the foreground Bash tool "
        "cannot complete a 20×60s loop (10-min hard cap)."
    )


def test_cr_polling_documents_status_file(cr_polling_text):
    """The doc must describe a status file so the re-invoked agent can read the verdict."""
    assert (
        "status_file" in cr_polling_text or "STATUS_FILE" in cr_polling_text
        or "status file" in cr_polling_text.lower()
    ), (
        "pr-cr-polling.md must document a status file protocol — the background "
        "process writes verdict/progress lines; the re-invoked agent reads them."
    )


def test_cr_polling_warns_against_foreground_execution(cr_polling_text):
    """The doc must explicitly warn agents NOT to run the loop in the foreground."""
    lower = cr_polling_text.lower()
    has_warning = (
        "never run" in lower
        or "not in the foreground" in lower
        or "do not run" in lower
        or ("foreground" in lower and "background" in lower)
    )
    assert has_warning, (
        "pr-cr-polling.md must warn against foreground execution — an agent reading "
        "only this doc must know a foreground call will hit the 10-min timeout wall."
    )


def test_cr_polling_background_timeout_covers_full_window(cr_polling_text):
    """The background command timeout must be >= 1200000ms (20 min) to cover all iterations."""
    # Look for a timeout value of at least 1200000 (ms) anywhere in the doc
    timeout_values = re.findall(r'\b(\d{6,})\b', cr_polling_text)
    sufficient = any(int(v) >= 1200000 for v in timeout_values)
    assert sufficient, (
        "pr-cr-polling.md must specify a background Bash timeout of at least 1200000ms "
        "(20 min) so the full 20-iteration poll window can complete without being killed."
    )
