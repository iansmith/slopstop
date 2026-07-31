"""
Phase 0 red tests for BILL-353 — Stage resume state and `Next: … (fresh
session)` lines.

Transcribed from the ticket's Test expectations
(https://github.com/iansmith/slopstop/issues/353). Transcription, not
authorship: every assertion below is pinned by the ticket, and per the fleet
brief's hard constraint 9 the implementer may not renegotiate them. If one is
wrong, the sanctioned exit is the TICKET UNDERSPECIFIED halt (TD-4a), not an
edit to this file.

This ticket is documentation-only (prose additions to the plan/pr/merge
SKILL.md spines under a shared `## Stage end — resume state and Next:`
heading) — there is no executable entrypoint to invoke, so every check here
reads file content.

Test command:
    python3 -m pytest tests/test_bill353_behaviors.py -v
"""

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent
SKILLS_DIR = REPO_ROOT / "skills"

SPINES = {
    "plan": SKILLS_DIR / "plan" / "SKILL.md",
    "pr": SKILLS_DIR / "pr" / "SKILL.md",
    "merge": SKILLS_DIR / "merge" / "SKILL.md",
}

HEADING = "## Stage end — resume state and Next:"


def _spine_text(name):
    path = SPINES[name]
    assert path.is_file(), f"{path} missing"
    return path.read_text()


def _spine_lines(name):
    return _spine_text(name).splitlines()


def _section_text(name):
    """Text of the `## Stage end — resume state and Next:` section only,
    from that heading to the next `## ` heading (or EOF)."""
    lines = _spine_lines(name)
    try:
        start = next(i for i, l in enumerate(lines) if l == HEADING)
    except StopIteration:
        pytest.fail(f"skills/{name}/SKILL.md is missing the heading {HEADING!r}")
    end = len(lines)
    for i in range(start + 1, len(lines)):
        if lines[i].startswith("## "):
            end = i
            break
    return "\n".join(lines[start:end])


class TestThreeSpinesPrintNextLine:
    @pytest.mark.parametrize("name", ["plan", "pr", "merge"])
    def test_three_spines_print_next_line(self, name):
        text = _spine_text(name)
        assert "(fresh session)" in text, (
            f"skills/{name}/SKILL.md must contain the literal substring "
            f"'(fresh session)' — the Next: line format"
        )


class TestWritePrecedesNextLine:
    @pytest.mark.parametrize("name", ["plan", "pr", "merge"])
    def test_write_precedes_next_line(self, name):
        lines = _spine_lines(name)

        write_idx = next(
            (i for i, l in enumerate(lines) if re.search(r"write resume state", l, re.IGNORECASE)),
            None,
        )
        assert write_idx is not None, (
            f"skills/{name}/SKILL.md must state the resume-state write "
            f"(prose containing 'write resume state')"
        )

        next_idx = next(
            (i for i, l in enumerate(lines) if "(fresh session)" in l),
            None,
        )
        assert next_idx is not None, (
            f"skills/{name}/SKILL.md must state the Next: line "
            f"(prose containing '(fresh session)')"
        )

        assert write_idx < next_idx, (
            f"skills/{name}/SKILL.md: the resume-state write (line {write_idx + 1}) "
            f"must precede the Next: line (line {next_idx + 1}) — write, then verify, "
            f"then print Next: (C7)"
        )


class TestAdvisoryNotBlocking:
    @pytest.mark.parametrize("name", ["plan", "pr", "merge"])
    def test_advisory_not_blocking(self, name):
        section = _section_text(name)
        assert "hard stop" not in section, (
            f"skills/{name}/SKILL.md's {HEADING!r} section must not contain "
            f"'hard stop' — the resume advice is advisory, never a hard gate (D2)"
        )
        assert "refuse" not in section, (
            f"skills/{name}/SKILL.md's {HEADING!r} section must not contain "
            f"'refuse' — the resume advice is advisory, never a hard gate (D2)"
        )


class TestNoSessionBoundaryRequired:
    @pytest.mark.parametrize("name", ["plan", "pr", "merge"])
    def test_no_session_boundary_required(self, name):
        section = _section_text(name).lower()
        assert "session boundary" in section, (
            f"skills/{name}/SKILL.md's {HEADING!r} section must state that "
            f"the fleet's single-process :plan -> :pr flow stays valid, with "
            f"no required session boundary between stages (C6)"
        )
        assert ":plan" in section and ":pr" in section, (
            f"skills/{name}/SKILL.md's {HEADING!r} section must name the "
            f":plan -> :pr single-process path explicitly (C6)"
        )


class TestTrackingDirNotRederived:
    """Regression guard, green at HEAD by design — none of the three spines
    restates the tracking-dir *resolution* ladder (a different artifact from
    the four-tier model ladder in .project-conf.toml); each already just
    points at tracking-dir-resolution.md. Must stay true after this ticket's
    changes and is not counted toward this ticket's red-first evidence."""

    @pytest.mark.parametrize("name", ["plan", "pr", "merge"])
    def test_tracking_dir_not_rederived(self, name):
        text = _spine_text(name)
        assert "tracking-dir-resolution.md" in text, (
            f"skills/{name}/SKILL.md must point at "
            f"tracking-dir-resolution.md rather than re-deriving the "
            f"resolution ladder"
        )
        assert "Tier 1 — an explicit key" not in text, (
            f"skills/{name}/SKILL.md must not restate the tracking-dir "
            f"resolution ladder inline — point at tracking-dir-resolution.md "
            f"instead"
        )


# --- Adversary gap-finder pass (inline, per :plan Step 0f) -----------------
#
# Attack vectors worked against the Phase 0 suite above: (1) the section-scope
# boundary for test_advisory_not_blocking — an unscoped substring check would
# false-positive immediately at HEAD (all three spines already contain
# 'refuse', pr/SKILL.md also contains 'hard stop', none related to resume), so
# the scoping to the exact heading-to-next-`## ` window is itself
# load-bearing and checked by a dedicated regression test below;
# (2) 'session boundary' could appear in prose without actually naming the
# :plan -> :pr path — checked as a conjunction, not two independent
# assertions in different tests; (3) the write/Next ordering check could pass
# vacuously if either marker string were absent — both existence and order
# are asserted, not just relative position; (4) a spine could satisfy
# 'write resume state' and '(fresh session)' by restating them outside the
# new heading entirely (e.g. copy-pasted into an unrelated step) — the
# heading-existence assertion in _section_text catches a spine that never
# added the heading at all.


class TestAdversaryGaps:
    @pytest.mark.parametrize("name", ["plan", "pr", "merge"])
    def test_heading_present_verbatim(self, name):
        lines = _spine_lines(name)
        assert HEADING in lines, (
            f"skills/{name}/SKILL.md must carry the heading {HEADING!r} "
            f"verbatim (identical across all three spines)"
        )

    def test_advisory_check_is_section_scoped_not_whole_file(self):
        # Sanity check on the fixture itself: at HEAD (before this ticket's
        # section exists) every spine already contains 'refuse' somewhere,
        # and pr/SKILL.md contains 'hard stop' — proving an unscoped check
        # would be meaningless. This guards against someone "fixing" the
        # test above to check the whole file instead of the section.
        for name in ("plan", "pr", "merge"):
            text = _spine_text(name)
            assert "refuse" in text or "hard stop" in text, (
                f"fixture assumption broken: skills/{name}/SKILL.md no "
                f"longer contains 'refuse' or 'hard stop' anywhere — the "
                f"section-scoped test above may no longer be meaningful"
            )

    @pytest.mark.parametrize("name", ["plan", "pr", "merge"])
    def test_next_line_format_is_exact(self, name):
        text = _spine_text(name)
        assert re.search(r"Next: .+ \(fresh session\)", text), (
            f"skills/{name}/SKILL.md must contain the Next: line in exactly "
            f"the form 'Next: <command> (fresh session)'"
        )
