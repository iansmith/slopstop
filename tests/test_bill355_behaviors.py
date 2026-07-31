"""
Phase 0 red tests for BILL-355 — `:pr` size classifier gating only the
expensive passes.

Transcribed from the ticket's Test expectations
(https://github.com/iansmith/slopstop/issues/355). Transcription, not
authorship: every assertion below is pinned by the ticket, and per the fleet
brief's hard constraint 9 the implementer may not renegotiate them. If one is
wrong, the sanctioned exit is the TICKET UNDERSPECIFIED halt (TD-4a), not an
edit to this file.

This ticket is documentation-only (a new reference file plus prose additions
across skills/pr/references/*.md and skills/pr/SKILL.md) — there is no
executable entrypoint to invoke, so every check here reads file content.

Test command:
    python3 -m pytest tests/test_bill355_behaviors.py -v
"""

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent
SKILLS_DIR = REPO_ROOT / "skills"
PR_DIR = SKILLS_DIR / "pr"
PR_REFS = PR_DIR / "references"
PR_SPINE = PR_DIR / "SKILL.md"
CLASSIFIER_REF = PR_REFS / "pr-size-classifier.md"
PR_MANIFEST = PR_REFS / "manifest.txt"
PR_TEST_GATES = PR_REFS / "pr-test-gates.md"
PR_SLOP = PR_REFS / "pr-slop-detection.md"
PR_CLAUDE_REVIEW = PR_REFS / "pr-claude-review.md"
PR_CR_POLLING = PR_REFS / "pr-cr-polling.md"
PR_GREPTILE_POLLING = PR_REFS / "pr-greptile-polling.md"
GATES_REF = SKILLS_DIR / "start" / "references" / "gates-json.md"

STEP6_BACKEND_FILES = [PR_CLAUDE_REVIEW, PR_CR_POLLING, PR_GREPTILE_POLLING]


def _text(path):
    if not path.is_file():
        pytest.fail(f"{path} does not exist")
    return path.read_text()


def _classifier_text():
    return _text(CLASSIFIER_REF)


class TestClassifierReferenceExistsAndManifested:
    def test_classifier_reference_exists_and_manifested(self):
        assert CLASSIFIER_REF.is_file(), (
            "skills/pr/references/pr-size-classifier.md missing — the ticket "
            "requires a new reference documenting the size classifier"
        )
        assert PR_MANIFEST.is_file(), "skills/pr/references/manifest.txt missing"
        listed = {
            line.strip() for line in PR_MANIFEST.read_text().splitlines() if line.strip()
        }
        assert "pr-size-classifier.md" in listed, (
            "pr-size-classifier.md must be listed in skills/pr/references/manifest.txt"
        )


class TestGatedSetIsExactlyThree:
    def test_gated_set_is_exactly_three(self):
        classifier_text = _classifier_text()
        lowered = classifier_text.lower()
        for key in ("step 0b", "step 2e", "step 6"):
            assert key in lowered, (
                f"pr-size-classifier.md must name '{key}' as part of the gated set"
            )
        for never in ("step 1", "step 2d", "step 2f"):
            # Named as never-gated somewhere in the doc (not necessarily absent —
            # they must be explicitly excluded, see test_simplify_never_gated /
            # test_mechanical_gates_never_gated for the stronger paragraph-scoped
            # version of this claim).
            assert never in lowered, (
                f"pr-size-classifier.md must explicitly discuss '{never}' as "
                f"never gated"
            )
        # Targeted Step 2 test run — distinct from "step 2e"/"step 2d"/"step 2f".
        assert re.search(r"step 2(?![a-z0-9])", lowered) or "step 2's targeted" in lowered, (
            "pr-size-classifier.md must name Step 2's targeted test run as never gated"
        )

        spine_text = _text(PR_SPINE).lower()
        assert "pr-size-classifier" in spine_text or "size classifier" in spine_text, (
            "skills/pr/SKILL.md must reference the size classifier"
        )


class TestCcGateNeverTierGated:
    def test_cc_gate_never_tier_gated(self):
        for path in (CLASSIFIER_REF, PR_SPINE, PR_TEST_GATES):
            text = _text(path)
            lowered = text.lower()
            if "step 0c" in lowered or "step_0c" in lowered:
                assert (
                    "never tier-gate" in lowered
                    or "never tier gated" in lowered
                    or "not tier-gate" in lowered
                    or "not gated" in lowered
                ), f"{path} mentions Step 0c but never states it is never tier-gated"
        # At least one of the three must state it explicitly.
        combined = "\n".join(_text(p).lower() for p in (CLASSIFIER_REF, PR_SPINE, PR_TEST_GATES))
        assert "step 0c" in combined and (
            "never tier-gate" in combined or "never tier gated" in combined
        ), (
            "the classifier reference and the spine must both state that Step 0c "
            "(the cyclomatic-complexity gate) runs at every tier and is never in "
            "the gated set"
        )
        # Guard against a conflated bare "step 0" key/label standing in for 0b/0c.
        assert re.search(r"step[ _]0(?![bc0-9])", combined) is None, (
            "must never use a conflated 'step 0' label — only 'Step 0b' and "
            "'Step 0c' are valid, distinct steps"
        )


class TestSimplifyNeverGated:
    def test_simplify_never_gated(self):
        for path in (CLASSIFIER_REF, PR_SPINE):
            text = _text(path)
            lowered = text.lower()
            paragraphs = re.split(r"\n\s*\n", lowered)
            assert any(
                ("step 1" in p or "simplify" in p) and ("every tier" in p or "no exception" in p or "never gated" in p or "always run" in p)
                for p in paragraphs
            ), f"{path} must state Step 1 (simplify) runs at every tier, with no exceptions"

        # Neither file may place "Step 1" or "simplify" inside the gated-set list.
        for path in (CLASSIFIER_REF, PR_SPINE):
            text = _text(path)
            lowered = text.lower()
            gated_set_paragraphs = [
                p
                for p in re.split(r"\n\s*\n", lowered)
                if "step 0b" in p and "step 2e" in p and "step 6" in p
            ]
            for p in gated_set_paragraphs:
                assert "step 1" not in p and "simplify" not in p.replace(
                    "never gate", ""
                ).replace("not gated", "") or "never" in p or "not gated" in p, (
                    f"{path}: a paragraph naming the gated set must not also "
                    f"include Step 1/simplify as a member of it"
                )


class TestMechanicalGatesNeverGated:
    def test_mechanical_gates_never_gated(self):
        for path in (CLASSIFIER_REF, PR_SLOP):
            text = _text(path)
            lowered = text.lower()
            for step in ("step 2d", "step 2f"):
                assert step in lowered, f"{path} must name '{step}'"
            paragraphs = re.split(r"\n\s*\n", lowered)
            assert any(
                ("step 2d" in p or "step 2f" in p)
                and ("never" in p or "no flag" in p or "unskippable" in p or "runs on every path" in p)
                for p in paragraphs
            ), f"{path} must state Steps 2d and 2f are never gated (C4)"


class TestThreeTierNames:
    def test_three_tier_names(self):
        text = _classifier_text()
        for tier in ("trivial", "standard", "large"):
            assert tier in text, f"pr-size-classifier.md must name tier '{tier}'"
        # Guard against a fourth invented tier name slipping in as a synonym.
        forbidden = ("small", "medium", "huge", "tiny", "xl", "extra-large")
        lowered_lines = [
            line.lower()
            for line in text.splitlines()
            if re.search(r"\btier\b", line, re.IGNORECASE) or "trivial" in line.lower() or "standard" in line.lower() or "large" in line.lower()
        ]
        for line in lowered_lines:
            for bad in forbidden:
                assert bad not in line, (
                    f"pr-size-classifier.md line {line!r} introduces a fourth tier "
                    f"name ('{bad}') — only trivial/standard/large are sanctioned"
                )


class TestClassifierAnnouncesBeforeSkipping:
    def test_classifier_announces_before_skipping(self):
        spine_text = _text(PR_SPINE).lower()
        classifier_text = _classifier_text().lower()
        combined = spine_text + "\n" + classifier_text
        assert "before" in combined and (
            "skip" in combined or "gate" in combined
        ), (
            "the spine or classifier reference must state the tier+signals line "
            "prints before any gate is skipped (C14)"
        )
        paragraphs = re.split(r"\n\s*\n", combined)
        assert any(
            ("announce" in p or "print" in p or "prints" in p)
            and "before" in p
            and "skip" in p
            for p in paragraphs
        ), (
            "must state, in one place, that the classifier announces tier+signals "
            "BEFORE any gate is skipped — never a silent skip (C14)"
        )


class TestOverrideFlagDocumented:
    def test_override_flag_documented(self):
        spine_text = _text(PR_SPINE)
        assert re.search(r"--[a-z][a-z-]*tier", spine_text, re.IGNORECASE) or "override" in spine_text.lower(), (
            "skills/pr/SKILL.md Arguments must document an override flag that "
            "forces a higher tier"
        )
        classifier_text = _classifier_text().lower()
        assert "override" in classifier_text and "higher tier" in classifier_text, (
            "pr-size-classifier.md must document that the override flag forces a "
            "HIGHER tier (never a lower one), so misclassification is always "
            "recoverable by the operator (C14)"
        )


class TestSkipRequiresShaMatch:
    def test_skip_requires_sha_match(self):
        text = _classifier_text()
        lowered = text.lower()
        assert "sha" in lowered and "head" in lowered
        paragraphs = re.split(r"\n\s*\n", lowered)
        assert any(
            "sha" in p and ("current head" in p or "head sha" in p) and ("gate" in p or "gates.json" in p)
            for p in paragraphs
        ), (
            "pr-size-classifier.md must state the skip path for gate entries fires "
            "only when sha == current HEAD"
        )
        assert any(
            "sha" in p and ("meta.tier" in p or "meta" in p and "tier" in p)
            for p in paragraphs
        ), (
            "pr-size-classifier.md must state the persisted meta.tier is also "
            "subject to the sha-match rule (C3 applies twice, independently)"
        )
        assert any(
            "mismatch" in p or "not equal" in p or "non-matching" in p or "stale" in p
            for p in paragraphs
            if "sha" in p
        ), "must state a mismatched sha is treated as absent"
        assert "expir" not in lowered, (
            "pr-size-classifier.md must not describe time-based expiry — "
            "staleness is sha-only (C3)"
        )


class TestStaleTierForcesReclassify:
    def test_stale_tier_forces_reclassify(self):
        text = _classifier_text().lower()
        paragraphs = re.split(r"\n\s*\n", text)
        assert any(
            "meta.tier" in p or ("meta" in p and "tier" in p)
            for p in paragraphs
            if "reclassif" in p
        ), (
            "pr-size-classifier.md must state a stale meta.tier (sha mismatch) "
            "forces RECLASSIFICATION, never reuse"
        )
        assert "reuse" in text or "reused" in text, (
            "pr-size-classifier.md must explicitly contrast reclassify vs reuse"
        )


class TestMissingOrCorruptGatesJsonRunsTheGate:
    def test_missing_or_corrupt_gates_json_runs_the_gate(self):
        text = _classifier_text().lower()
        for kw in ("missing", "unparseable", "corrupt"):
            assert kw in text, f"pr-size-classifier.md must mention the '{kw}' case"
        assert "run the gate" in text, (
            "pr-size-classifier.md must state missing/unparseable gates.json means "
            "'run the gate', never assume pass (C2)"
        )
        assert "assume pass" not in text.replace("never assume pass", ""), (
            "pr-size-classifier.md must never instruct assuming pass on bad "
            "gates.json data"
        )


class TestTierPersistedUnderMeta:
    def test_tier_persisted_under_meta(self):
        text = _classifier_text()
        assert '"value"' in text and '"sha"' in text, (
            "pr-size-classifier.md must document meta.tier as "
            '{"value": ..., "sha": ...}'
        )
        assert "meta" in text.lower()
        lowered = text.lower()
        assert "top-level" in lowered or "new gate key" in lowered or "not a" in lowered or "never" in lowered, (
            "pr-size-classifier.md must state the tier is NOT stored as an "
            "additional top-level gate key and not as a bare string"
        )
        for bad_tier_string in ("\"tier\": \"trivial\"", "\"tier\": \"standard\"", "\"tier\": \"large\""):
            assert bad_tier_string not in text.replace(
                'meta.tier = {"value": "trivial"', ""
            ), (
                f"pr-size-classifier.md must not show tier persisted as a bare "
                f"string ({bad_tier_string})"
            )


# --- Write-point coverage: pr/SKILL.md and the six touched references ------


class TestGateWritePointsMentionTierGating:
    @pytest.mark.parametrize(
        "ref_file,gate_key,step_label",
        [
            (PR_TEST_GATES, "step_0b", "0b"),
            (PR_SLOP, "step_2e", "2e"),
            (PR_CLAUDE_REVIEW, "step_6", "6"),
            (PR_CR_POLLING, "step_6", "6"),
            (PR_GREPTILE_POLLING, "step_6", "6"),
        ],
    )
    def test_reference_mentions_tier_gating_for_its_gate(self, ref_file, gate_key, step_label):
        text = _text(ref_file)
        lowered = text.lower()
        # Scoped to the paragraph(s) actually discussing this step, not merely
        # anywhere in the file — pr-test-gates.md already contains the word
        # "tier" in an unrelated sentence about Step 0c ("never tier-gateable"),
        # which would otherwise produce a false-negative (vacuous) pass here.
        paragraphs = re.split(r"\n\s*\n", lowered)
        step_paragraphs = [
            p for p in paragraphs if f"step {step_label}" in p or f"step_{step_label}" in p
        ]
        assert step_paragraphs, f"{ref_file.name} has no paragraph discussing step {step_label}"
        assert any("tier" in p for p in step_paragraphs), (
            f"{ref_file.name} must mention tier-gating in the same paragraph "
            f"that discusses {gate_key}"
        )
