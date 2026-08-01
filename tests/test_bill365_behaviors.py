"""
Phase 0 red tests for BILL-365 — the tamper-gate docs describe the wrong file set.

Transcribed from the ticket's Test expectations
(https://github.com/iansmith/slopstop/issues/365). Transcription, not authorship:
every assertion below is pinned by the ticket, and per the fleet brief's hard
constraint 9 the implementer may not renegotiate them. If one is wrong, the
sanctioned exit is the TICKET UNDERSPECIFIED halt (TD-4a), not an edit to this
file.

Both tamper gates derive their frozen set from the WHOLE Phase 0 commit --
`FROZEN=$(git show --name-only --format= "$RED")` in pr-slop-detection.md and
run-verification.md -- but two documents tell the agent it diffs "test files".
Today those name the same set, because the Phase 0 commit is test-only by
invariant, so the error is inert. It is still a wrong description of a mechanical
gate, in the two documents an agent reads to decide what is safe.

This ticket is documentation-only; every check here reads file content.

Test command:
    python3 -m pytest tests/test_bill365_behaviors.py -v
"""

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent
AGENT_BRIEF = REPO_ROOT / "skills" / "run" / "references" / "run-agent-brief.md"
PR_SPINE = REPO_ROOT / "skills" / "pr" / "SKILL.md"

# The correction the ticket mandates. Stated in the ticket, not invented here.
CORRECT_PHRASE = "every file in the Phase 0 commit"
DERIVATION = "git show --name-only"


def _text(path):
    if not path.is_file():
        pytest.fail(f"{path} does not exist")
    return path.read_text()


class TestAgentBriefDescribesTheFrozenSetCorrectly:
    """run-agent-brief.md hard constraint 9 — the one doc a fleet agent reads."""

    def test_agent_brief_drops_the_test_files_description(self):
        assert "diffs your test files" not in _text(AGENT_BRIEF), (
            "run-agent-brief.md hard constraint 9 still says handoff verification "
            "'diffs your test files'. It diffs every file in the Phase 0 commit — "
            "FROZEN comes from `git show --name-only` against the red-test commit "
            "(run-verification.md), deliberately, so inline tests inside source "
            "files are covered by the same mechanism."
        )

    def test_agent_brief_states_the_real_file_set(self):
        assert CORRECT_PHRASE in _text(AGENT_BRIEF), (
            f"run-agent-brief.md must state the gate covers {CORRECT_PHRASE!r}"
        )


class TestPrSpineDescribesTheFrozenSetCorrectly:
    """skills/pr/SKILL.md Step 2d — the solo path's copy of the same claim."""

    def test_pr_spine_drops_the_test_files_description(self):
        assert "Diff the test files" not in _text(PR_SPINE), (
            "pr/SKILL.md Step 2d still says 'Diff the test files across the range'. "
            "Step 2d's frozen set is every file in the Phase 0 commit "
            "(pr-slop-detection.md's FROZEN derivation), not a test-file glob."
        )

    def test_pr_spine_states_the_real_file_set(self):
        assert CORRECT_PHRASE in _text(PR_SPINE), (
            f"pr/SKILL.md Step 2d must state the gate covers {CORRECT_PHRASE!r}"
        )


class TestDerivationIsCheckableFromTheDocsAnAgentReads:
    def test_at_least_one_doc_names_the_derivation(self):
        # The ticket asks for the derivation to be named in at least one of the two,
        # so a reader can verify the claim instead of trusting it.
        named_in = [
            p.name for p in (AGENT_BRIEF, PR_SPINE) if DERIVATION in _text(p)
        ]
        assert named_in, (
            f"neither run-agent-brief.md nor pr/SKILL.md names the {DERIVATION!r} "
            "derivation — an agent has no way to check the corrected claim against "
            "the script that implements it"
        )


# --- Adversary gap tests (Step 0f) -----------------------------------------
# Added by the Phase 0 adversary pass. All five tests above are unscoped
# substring checks over the WHOLE file, which decouples each "drop X / add Y"
# pair: an implementer could reword the flagged clause so the literal no longer
# matches, leave the claim still wrong, and drop the corrected phrase somewhere
# unrelated in a 189-line file. Every one of the five would pass.

CONSTRAINT_9 = r"^9\.\s.*?(?=^\d+\.|\Z)"


def _constraint_9(text):
    import re
    m = re.search(CONSTRAINT_9, text, re.DOTALL | re.MULTILINE)
    assert m, "hard constraint 9 not found by its numbered marker in run-agent-brief.md"
    return m.group(0)


def _step_2d(text):
    import re
    m = re.search(r"(?:^|\n)(?:#+ )?.*Step 2d.*?(?=\n#{1,4} |\Z)", text, re.DOTALL)
    assert m, "Step 2d section not found in pr/SKILL.md"
    return m.group(0)


class TestCorrectionLandsInTheClaimItself:
    """Gap 5a — scope the assertions to the unit that actually makes the claim."""

    def test_constraint_9_itself_names_the_full_file_set(self):
        block = _constraint_9(_text(AGENT_BRIEF))
        assert "diffs your test files" not in block, (
            "hard constraint 9 still scopes the gate to test files"
        )
        assert CORRECT_PHRASE in block, (
            f"the corrected phrase {CORRECT_PHRASE!r} is not inside hard constraint 9 — "
            "satisfying the file-wide check by adding it elsewhere leaves the constraint "
            "an agent actually reads still wrong"
        )

    def test_step_2d_itself_names_the_full_file_set(self):
        block = _step_2d(_text(PR_SPINE))
        assert "Diff the test files" not in block, (
            "pr/SKILL.md Step 2d still scopes the gate to test files"
        )
        assert CORRECT_PHRASE in block, (
            f"the corrected phrase {CORRECT_PHRASE!r} is not inside Step 2d"
        )


class TestDerivationIsStatedWhereTheClaimIs:
    """Gap 5c — the derivation exists so a reader can CHECK the claim."""

    def test_derivation_is_near_the_corrected_claim(self):
        near = False
        for path in (AGENT_BRIEF, PR_SPINE):
            text = _text(path)
            if DERIVATION in text and CORRECT_PHRASE in text:
                if abs(text.find(DERIVATION) - text.find(CORRECT_PHRASE)) < 400:
                    near = True
        assert near, (
            f"{DERIVATION!r} is not stated near the corrected file-set claim in either "
            "doc — pasting it into an unrelated snippet satisfies the file-wide check "
            "while defeating its stated purpose (verify, don't trust)"
        )


# --- Regression guards (SLOPSTOP PRAGMA coverage-backfill) -----------------
# These pass at BASE by construction — they pin text this ticket must NOT
# change, and one bans a bad outcome that does not exist yet. Per the Phase 0
# invariant ("only tests observed FAILING at 0d may enter this commit") they
# were withheld from the red-test commit and land here instead, following the
# convention established in test_bill355_behaviors.py.

PR_SLOP = REPO_ROOT / "skills" / "pr" / "references" / "pr-slop-detection.md"
FROZEN_DERIVATION = 'FROZEN=$(git show --name-only --format= "$RED")'


class TestCorrectionIsAffirmative:
    """Gap 5b — the phrase must assert the claim, not deny it.

    Deliberately NOT the adversary's suggested negation-window heuristic:
    "diffs every file in the Phase 0 commit, not just your test files" is
    CORRECT prose containing `not `, and a window check would fail a good
    implementation. Targeted negative literals instead — they ban the wrong
    claim without banning legitimate contrast.
    """

    # SLOPSTOP PRAGMA coverage-backfill: passes at BASE (the bad literals were
    # never present); it guards against a future edit reintroducing the claim.
    def test_neither_doc_reasserts_the_test_files_only_claim(self):
        for path in (AGENT_BRIEF, PR_SPINE):
            low = _text(path).lower()
            for bad in ("only diffs test files", "only your test files",
                        "only the test files", "diffs only test files"):
                assert bad not in low, (
                    f"{path.name} contains {bad!r} — the corrected phrase can be present "
                    "while the document still asserts the gate is test-file-scoped"
                )


class TestConstraint9ProhibitionsSurvive:
    # SLOPSTOP PRAGMA coverage-backfill: this ticket rewrites the sentence these
    # prohibitions live beside, so they legitimately pass at BASE and the guard
    # exists to prove the description fix did not eat the constraint around it.
    def test_constraint_9_still_forbids_what_it_always_forbade(self):
        block = _constraint_9(_text(AGENT_BRIEF))
        assert "You may ADD" in block
        assert "Amending or rebasing the Phase 0 commit is the same offense" in block, (
            "the description fix must not disturb constraint 9's prohibitions"
        )


class TestGateSourceOfTruthUnchanged:
    # SLOPSTOP PRAGMA coverage-backfill: pins the derivation this ticket corrects
    # the other two docs AGAINST. run-verification.md's copy is already pinned by
    # test_bill278_behaviors.py:209, so only pr-slop-detection.md's is added here
    # (universal §5 — one definition, no duplicate assertion).
    def test_slop_detection_still_derives_frozen_from_the_commit(self):
        assert FROZEN_DERIVATION in _text(PR_SLOP), (
            "pr-slop-detection.md's FROZEN derivation changed — this ticket documents "
            "that mechanism and must never edit it"
        )


# --- Correctly-scoped replacements (review finding, PR #367) ---------------
# `_step_2d` above uses re.DOTALL with a greedy `.*`, so it backtracks to the
# LAST of nine "Step 2d" occurrences and captures 63% of the file starting at
# the frontmatter. `_constraint_9` starts correctly but nothing matches
# `^\d+\.` after constraint 9, so it runs to EOF and captures 35%.
#
# Both are frozen (Phase 0 gap-test commit), so they are not edited — the freeze
# permits ADDING tests, never retargeting an existing one. These are strictly
# stronger additions; the weaker originals keep passing alongside them.
#
# Each assertion below also pins the extracted block's SIZE. That is the part
# the originals lacked: without it, an extractor silently widening back out to
# most of the file goes unnoticed, which is exactly how this defect survived
# the adversary pass that produced it.

import re as _re

_FENCE = r"^```\s*$"
_NUMBERED = r"^\d+\.\s"


def _constraint_9_bounded(text):
    """Constraint 9 only — terminated by the next numbered item or the closing fence."""
    start = text.index("9. Red tests are frozen")
    rest = text[start:]
    ends = [m.start() for pat in (_NUMBERED, _FENCE)
            for m in [_re.search(pat, rest[1:], _re.MULTILINE)] if m]
    return rest[: min(ends) + 1] if ends else rest


def _step_2d_bounded(text):
    """The `## Step 2d` section only — terminated by the next `## ` heading."""
    start = text.index("## Step 2d")
    nxt = text.find("\n## ", start + 1)
    return text[start : nxt if nxt != -1 else len(text)]


class TestScopedToTheClaimForReal:
    """Review finding on PR #367 — the gap-5a helpers did not actually scope."""

    def test_constraint_9_block_is_narrow_and_carries_the_claim(self):
        block = _constraint_9_bounded(_text(AGENT_BRIEF))
        assert block.startswith("9. Red tests are frozen"), "extractor lost its anchor"
        assert len(block) < 1000, (
            f"constraint-9 extraction widened to {len(block)} chars — it is one "
            "numbered item, not a region of the file; a wide block silently turns "
            "this into the whole-file check it replaced"
        )
        assert "diffs your test files" not in block
        assert CORRECT_PHRASE in block, (
            "constraint 9 itself must carry the corrected claim — not merely the file"
        )

    def test_step_2d_block_is_narrow_and_carries_the_claim(self):
        block = _step_2d_bounded(_text(PR_SPINE))
        assert block.startswith("## Step 2d"), "extractor lost its anchor"
        assert len(block) < 4000, (
            f"Step 2d extraction widened to {len(block)} chars — the section is "
            "~2.3k; anything near file-size means the greedy-backtrack bug is back"
        )
        assert "Diff the test files" not in block
        assert CORRECT_PHRASE in block, (
            "Step 2d itself must carry the corrected claim — not merely the file"
        )

    def test_derivation_sits_inside_the_claiming_sections(self):
        # Stronger than the 400-char proximity window: the derivation must be in
        # the same bounded section as the claim, in at least one of the two docs.
        blocks = (_constraint_9_bounded(_text(AGENT_BRIEF)),
                  _step_2d_bounded(_text(PR_SPINE)))
        assert any(DERIVATION in b and CORRECT_PHRASE in b for b in blocks), (
            f"{DERIVATION!r} is not inside a section that makes the claim"
        )
