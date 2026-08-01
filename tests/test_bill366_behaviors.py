"""
Guards for the Phase 0 stub rule and the tamper-gate baseline.

Originally BILL-366's Phase 0 suite. Most of it asserted that particular English
sentences appeared in particular markdown files — a shape that pins the wording of
prose a model reads, not behavior. When the design was deliberately simplified on
2026-08-01 (stubs share the Phase 0 commit; `meta.frozen` records the test files),
eight of those assertions failed for the *right* reason: the prose they pinned was
supposed to change. They were retired rather than updated to chase the new wording.

What survives is the part that guards something real:

  * the Phase 0 invariant, which the design exists to leave alone
  * the tamper gates' frozen-set derivation
  * the safety property of a stub: non-satisfying by construction

Anything else about how these documents are worded belongs to review, not to a test.
"""

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent
MECHANICS = REPO_ROOT / "skills" / "plan" / "references" / "plan-phase0-mechanics.md"
PLAN_SPINE = REPO_ROOT / "skills" / "plan" / "SKILL.md"
PR_SLOP = REPO_ROOT / "skills" / "pr" / "references" / "pr-slop-detection.md"
RUN_VERIFY = REPO_ROOT / "skills" / "run" / "references" / "run-verification.md"

INVARIANT = "Only tests observed FAILING at 0d may enter this commit"
FROZEN_DERIVATION = 'FROZEN=$(git show --name-only --format= "$RED")'


def _text(path):
    if not path.is_file():
        pytest.fail(f"{path} does not exist")
    return path.read_text()


class TestPhase0InvariantSurvives:
    """Nothing about stubs may weaken this.

    A stub is production surface that shares the red-test commit; it is explicitly
    NOT a test, and never counts as one for the purpose of this rule.
    """

    @pytest.mark.parametrize("path", [MECHANICS, PLAN_SPINE], ids=lambda p: p.name)
    def test_invariant_present_verbatim(self, path):
        assert INVARIANT in _text(path), (
            f"{path.name} lost the Phase 0 invariant. Stubs sharing the commit does "
            "not relax it: `meta.frozen` records the TEST files, so a stub is simply "
            "not part of the frozen set — the rule about what may be frozen is unchanged."
        )

    def test_lowercase_confirmation_line_present(self):
        # Deliberately a different string from INVARIANT — asserting INVARIANT
        # against this line would be red for the wrong reason.
        assert "only tests observed failing at 0d" in _text(MECHANICS)


class TestStubsAreNonSatisfying:
    """The one property that makes stubs safe rather than a loophole."""

    def test_sentinel_rule_stated(self):
        assert "non-satisfying by construction" in _text(MECHANICS), (
            "a stub that can satisfy an assertion turns an observed-failing baseline "
            "into an accidentally-green one — this is the whole safety property"
        )

    def test_non_reaching_forms_excluded(self):
        t = _text(MECHANICS)
        assert "not permitted stub bodies" in t and "without reaching the assertion" in t, (
            "panic/NotImplementedError fail WITHOUT reaching the assertion, which is the "
            "same defect as the compile error stubs exist to remove. Excluding them by "
            "name is what stops the exemption reintroducing the bug under a new name."
        )


class TestTamperGateBaselineIsRecordedNotGuessed:
    def test_gates_still_carry_a_frozen_derivation(self):
        # Now the FALLBACK path — `meta.frozen` is preferred — but it must survive,
        # because an old gates.json written before meta.frozen existed relies on it.
        for path in (PR_SLOP, RUN_VERIFY):
            assert FROZEN_DERIVATION in _text(path), (
                f"{path.name} lost the frozen-set fallback; a gates.json predating "
                "meta.frozen would then have no way to resolve the frozen set"
            )

    @pytest.mark.parametrize("path", [PR_SLOP, RUN_VERIFY], ids=lambda p: p.name)
    def test_gates_prefer_the_recorded_baseline(self, path):
        t = _text(path)
        assert "meta.red_sha" in t and "meta.frozen" in t, (
            f"{path.name} must read what Step 0e recorded before falling back to "
            "grepping commit subjects and listing the commit's files. Deriving is what "
            "made an unanchored subject grep load-bearing and made everything in the "
            "Phase 0 commit frozen."
        )
