"""
Phase 0 red tests for BILL-366 — non-satisfying stubs via a pre-Phase-0 commit.

Transcribed from the ticket's Test expectations
(https://github.com/iansmith/slopstop/issues/366). Transcription, not authorship:
every assertion is pinned by the ticket, and per the fleet brief's hard constraint 9
the implementer may not renegotiate them. If one is wrong, the sanctioned exit is
the TICKET UNDERSPECIFIED halt (TD-4a), not an edit to this file.

The design in one line: stubs get their OWN commit, before the red-test commit, so
the Phase 0 commit stays test-only and neither tamper gate is touched. Two earlier
designs were killed in adversary review — stubs inside the Phase 0 commit (which
would put production files in FROZEN), and a stub commit titled "Phase 0: stubs for
..." (which could collide with the baseline-capture grep).

Test command:
    python3 -m pytest tests/test_bill366_behaviors.py -v
"""

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent
PLAN_REFS = REPO_ROOT / "skills" / "plan" / "references"

MECHANICS = PLAN_REFS / "plan-phase0-mechanics.md"
TICKET_DRIVEN = PLAN_REFS / "plan-ticket-driven.md"
TEST_RESULTS = PLAN_REFS / "plan-test-results.md"
RED_TESTS = PLAN_REFS / "plan-red-tests.md"
ADVERSARY_GAPS = PLAN_REFS / "plan-adversary-gaps.md"
PLAN_SPINE = REPO_ROOT / "skills" / "plan" / "SKILL.md"
AGENT_BRIEF = REPO_ROOT / "skills" / "run" / "references" / "run-agent-brief.md"

# Stated in the ticket, not invented here.
TITLE_FORMAT = "[$TICKET] Stubs for "
SENTINEL_RULE = "non-satisfying by construction"
EXCLUSION_SENTENCE = (
    'panic("not implemented") and raise NotImplementedError are not permitted '
    "stub bodies: they fail without reaching the assertion."
)
SUBSTEP = "0c-stub"


def _text(path):
    if not path.is_file():
        pytest.fail(f"{path} does not exist")
    return path.read_text()


class TestMechanicsDocumentsTheStubSubStep:
    def test_mechanics_states_the_title_format_and_the_sentinel_rule(self):
        t = _text(MECHANICS)
        assert TITLE_FORMAT in t, (
            f"plan-phase0-mechanics.md must state the commit title format {TITLE_FORMAT!r}. "
            "It must NOT carry the substring 'Phase 0: red tests' — both gates capture the "
            "baseline with an unanchored grep for that, taking the earliest match, so a "
            "colliding stub title would become $RED and FROZEN would be production files."
        )
        assert SENTINEL_RULE in t, (
            f"the stub rule {SENTINEL_RULE!r} must be stated — a stub that can satisfy an "
            "assertion turns an observed-failing baseline into an accidentally-green one"
        )

    def test_mechanics_excludes_the_non_reaching_stub_forms(self):
        assert EXCLUSION_SENTENCE in _text(MECHANICS), (
            "the load-bearing safety property is missing. panic/NotImplementedError fail "
            "WITHOUT reaching the assertion, which is the same defect as the compile error "
            "this ticket exists to remove — permitting them reintroduces it under a new name."
        )

    def test_mechanics_names_the_substep_without_renumbering(self):
        t = _text(MECHANICS)
        assert SUBSTEP in t, f"the new sub-step must be labelled {SUBSTEP!r}"
        # 0e (freeze) and 0f (adversary gaps) are referenced BY NAME from
        # pr-slop-detection.md and run-verification.md, which the DoD requires
        # byte-identical. Renumbering them would deadlock the ticket.
        assert "Step 0e" in t and "Step 0f" in t, (
            "Step 0e and Step 0f must keep their labels — pr-slop-detection.md and "
            "run-verification.md reference them by name and are byte-identical-required"
        )

    def test_substep_requires_the_regression_baseline_rerun(self):
        t = _text(MECHANICS)
        i = t.find(SUBSTEP)
        assert i != -1, f"{SUBSTEP!r} not found"
        assert "regression baseline" in t[i : i + 2000], (
            "the stub sub-step must re-run the 0b regression baseline before committing — "
            "a stub introduces real production surface that can break existing tests, and "
            "unchecked that breakage surfaces later at Step 3a blamed on the wrong item"
        )


class TestNoStubsIsDisambiguated:
    def test_line_37_distinguishes_stub_tests_from_production_stubs(self):
        t = _text(MECHANICS)
        assert "stub tests" in t, (
            "plan-phase0-mechanics.md's 'no stubs' forbids stub TESTS (a test asserting "
            "nothing). Left ambiguous, one line forbids what another now permits."
        )
        assert "no stubs, no skipped tests" not in t, (
            "the bare 'no stubs' phrasing must be disambiguated"
        )


class TestFleetAgentSeesTheRule:
    def test_agent_brief_carries_the_stub_rule(self):
        t = _text(AGENT_BRIEF)
        assert TITLE_FORMAT in t, (
            "run-agent-brief.md must carry the stub commit title verbatim — a fleet agent "
            "starts with no prior context and will not follow a rule it never sees (§6)"
        )
        # Already true as of #365; kept because the ticket states it.
        m = re.search(r"^9\.\s.*?(?=^\d+\.\s|^```\s*$)", t, re.DOTALL | re.MULTILINE)
        assert m, "hard constraint 9 not found"
        assert "your test files" not in m.group(0), (
            "hard constraint 9 must not describe the gate as diffing 'your test files'"
        )


class TestTicketDrivenProfileIsCovered:
    def test_td3_has_a_stub_step(self):
        assert "Stubs for" in _text(TICKET_DRIVEN), (
            "plan-ticket-driven.md TD-3 must carry the stub step. The ticket-driven "
            "profile runs 'in place of Steps 0c-2' and is the profile EVERY fleet agent "
            "runs, so a sub-step added only between 0c and 0e never executes for them."
        )

    def test_plan_spine_enumeration_names_the_substep(self):
        assert SUBSTEP in _text(PLAN_SPINE), (
            "plan/SKILL.md's sub-step enumeration goes stale when a sub-step is added"
        )


class TestEveryChangedReferenceIsUpdated:
    """One assertion per changed file, so a partial implementation fails loudly."""

    @pytest.mark.parametrize("path", [RED_TESTS, ADVERSARY_GAPS, TEST_RESULTS],
                             ids=lambda p: p.name)
    def test_reference_mentions_the_stub_commit(self, path):
        assert "Stubs for" in _text(path), (
            f"{path.name} must account for the stub commit"
        )
