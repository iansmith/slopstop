"""
Phase 0 red tests for BILL-138 — agent prompt: require findings + progress writes
during parallel fanout.

When :plan fans out parallel agents, agents do real investigation and implementation
work but write nothing to ~/.claude/ticket-active/$TICKET/. The orchestrator's
:update + :document chain runs against stale data. This ticket adds a # Documentation
section to plan-agent-prompt.md that tells agents to:

  1. Read findings.md at start (for investigation context)
  2. Append discovery sections to findings.md during work (named per-agent sections,
     concurrent-safe)
  3. Append a named summary to progress.md at completion or stop

Expected behaviors after implementation:
1. plan-agent-prompt.md has a "# Documentation" section
2. plan-agent-prompt.md instructs reading findings.md at start
3. plan-agent-prompt.md instructs writing to findings.md during work
4. plan-agent-prompt.md specifies named "## Agent" section format for findings writes
5. plan-agent-prompt.md instructs appending a summary to progress.md at completion
6. plan-agent-prompt.md specifies named "## Agent" section format for progress writes
7. plan-agent-prompt.md reads task_plan.md at start for work context
8. plan-agent-prompt.md requires writing findings immediately (not only at end)

These tests FAIL on current code and turn GREEN once the implementation is complete.

Test command:
    python3 -m pytest tests/test_bill138_behaviors.py -v
"""

from pathlib import Path
import pytest

REPO_ROOT = Path(__file__).parent.parent
AGENT_PROMPT = REPO_ROOT / "skills" / "plan" / "references" / "plan-agent-prompt.md"


@pytest.fixture(scope="module")
def prompt_text():
    return AGENT_PROMPT.read_text()


def test_agent_prompt_has_documentation_section(prompt_text):
    assert "# Documentation" in prompt_text, \
        "plan-agent-prompt.md must have a '# Documentation' section"


def test_agent_prompt_reads_findings_at_start(prompt_text):
    doc_section = prompt_text[prompt_text.find("# Documentation"):]
    assert "findings.md" in doc_section, \
        "Documentation section must instruct agents to read findings.md at start"


def test_agent_prompt_reads_task_plan_at_start(prompt_text):
    doc_section = prompt_text[prompt_text.find("# Documentation"):]
    assert "task_plan.md" in doc_section, \
        "Documentation section must instruct agents to read task_plan.md at start"


def test_agent_prompt_writes_findings_during_work(prompt_text):
    doc_section = prompt_text[prompt_text.find("# Documentation"):]
    assert "findings.md" in doc_section, \
        "Documentation section must instruct agents to append to findings.md"


def test_agent_prompt_findings_uses_named_agent_sections(prompt_text):
    doc_section = prompt_text[prompt_text.find("# Documentation"):]
    assert "## Agent" in doc_section, \
        "Documentation section must specify named '## Agent <id>' sections for concurrent-safe findings writes"


def test_agent_prompt_writes_findings_immediately_not_only_at_end(prompt_text):
    doc_section = prompt_text[prompt_text.find("# Documentation"):]
    # Must mention "immediately" or "as you" or "during" to signal proactive writing
    signals = ["immediately", "as you", "during work", "as they occur", "as it occurs", "when you discover"]
    assert any(s in doc_section.lower() for s in signals), \
        "Documentation section must instruct agents to write findings immediately during work, not only at completion"


def test_agent_prompt_appends_summary_to_progress(prompt_text):
    doc_section = prompt_text[prompt_text.find("# Documentation"):]
    assert "progress.md" in doc_section, \
        "Documentation section must instruct agents to append a summary to progress.md at completion"


def test_agent_prompt_progress_summary_uses_named_sections(prompt_text):
    doc_section = prompt_text[prompt_text.find("# Documentation"):]
    assert "## Agent" in doc_section, \
        "Documentation section must specify named '## Agent <id>' sections for progress.md to avoid concurrent conflicts"


def test_agent_prompt_progress_summary_covers_done_when(prompt_text):
    doc_section = prompt_text[prompt_text.find("# Documentation"):]
    # The summary must reference Done-when / criteria so orchestrator knows what completed
    signals = ["done-when", "done when", "criteria", "verification", "done_when"]
    assert any(s in doc_section.lower() for s in signals), \
        "Progress summary must reference Done-when criteria so the orchestrator knows completion status"


def test_agent_prompt_progress_summary_required_on_stop(prompt_text):
    doc_section = prompt_text[prompt_text.find("# Documentation"):]
    # Must apply on stop/blocked, not only on clean completion
    signals = ["stop", "blocked", "stuck", "early"]
    assert any(s in doc_section.lower() for s in signals), \
        "Progress summary must be required on early stop/blocked, not only clean completion"
