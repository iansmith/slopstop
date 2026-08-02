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
CLAUDE_MD = REPO_ROOT / "CLAUDE.md"
# The mirrored universal rules. Standalone since 2026-08-01; previously a
# BEGIN/END-delimited region inside CLAUDE.md.
UNIVERSAL_MD = REPO_ROOT / "CLAUDE-universal.md"


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
        # Guard against a conflated bare "step_0" SCHEMA KEY standing in for
        # 0b/0c (the gates.json key). The underscore form is always the
        # schema-key spelling in this codebase, so it is flagged in any
        # shape — bare, single-quoted, double-quoted, or backtick-quoted —
        # with no quote-adjacency requirement. Only the space-separated
        # prose form is exempt: "Step 0" (the umbrella pre-PR-health phase
        # covering 0a-0c) or "Step 0a" (the test-command sub-step) are
        # pre-existing, legitimate terminology unrelated to this ticket and
        # must not be flagged.
        assert re.search(r"step_0(?![bc0-9])", combined) is None, (
            "must never use a conflated 'step_0' schema key — only "
            "'step_0b' and 'step_0c' are valid, distinct gates.json keys"
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

        # Neither file may place "Step 1" or "simplify" inside the gated-set list
        # as a MEMBER of it (mentioning it nearby to explicitly exclude it is
        # fine and expected; the forbidden shape is listing it alongside 0b/2e/6
        # with no "never"/"not gated" qualifier attached).
        for path in (CLASSIFIER_REF, PR_SPINE):
            text = _text(path)
            lowered = text.lower()
            gated_set_paragraphs = [
                p
                for p in re.split(r"\n\s*\n", lowered)
                if "step 0b" in p and "step 2e" in p and "step 6" in p
            ]
            for p in gated_set_paragraphs:
                mentions_step1 = "step 1" in p or "simplify" in p
                if mentions_step1:
                    assert "never" in p or "not gated" in p, (
                        f"{path}: a paragraph naming the gated set {{0b,2e,6}} "
                        f"also mentions Step 1/simplify without explicitly "
                        f"excluding it — reads as though Step 1 is a member "
                        f"of the gated set"
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

    def test_override_flag_cannot_downgrade(self):
        # Adversary gap (coverage asymmetry): the "forces a higher tier" claim
        # was checked as a bare substring above, which would also pass a doc
        # that let the flag move the tier in EITHER direction as long as the
        # phrase "higher tier" appeared somewhere unrelated. Pin that the flag
        # is described as one-directional — it can only raise, never lower,
        # the computed tier.
        text = _classifier_text().lower()
        paragraphs = re.split(r"\n\s*\n", text)
        assert any(
            "override" in p and "higher" in p and ("never" in p or "only" in p or "cannot" in p or "not lower" in p or "not downgrade" in p)
            for p in paragraphs
        ), (
            "pr-size-classifier.md must state the override flag can only force "
            "a HIGHER tier and never downgrade the computed one"
        )


class TestClassifierDefinesConcreteSignals:
    def test_classifier_defines_concrete_signals(self):
        # Adversary gap (boundary omissions): a doc could satisfy every other
        # assertion in this suite with pure prose and never actually commit to
        # a concrete, checkable signal (line count, file count, path pattern,
        # etc.) for each tier — leaving the classifier's actual boundaries
        # unspecified. Require at least one concrete numeric or path-pattern
        # signal to be present.
        text = _classifier_text()
        has_number = re.search(r"\d+", text) is not None
        assert has_number, (
            "pr-size-classifier.md must define concrete, numeric signals/"
            "thresholds for tier boundaries — not prose alone"
        )
        lowered = text.lower()
        assert "signal" in lowered or "threshold" in lowered, (
            "pr-size-classifier.md must have a section naming its signals/"
            "thresholds explicitly"
        )


class TestGatesJsonNeverDecidesVerdict:
    def test_gates_json_never_decides_verdict(self):
        # Adversary gap (error-path / semantic gap): none of the other tests
        # pin the ticket's explicit "Do NOT let the classifier read gates.json
        # to decide a verdict — only to skip redundant work (C2)" out-of-scope
        # item. A classifier reference could satisfy every gated-set and
        # sha-matching test above while still using a gates.json hit as
        # evidence of pass/fail, which the ticket forbids.
        text = _classifier_text().lower()
        paragraphs = re.split(r"\n\s*\n", text)
        assert any(
            "gates.json" in p and ("skip" in p) and ("verdict" in p or "decide" in p or "pass" in p and "never" in p)
            for p in paragraphs
        ), (
            "pr-size-classifier.md must state gates.json is read only to skip "
            "redundant work, never to decide a gate's verdict (C2)"
        )


class TestSkipRequiresShaMatch:
    # BILL-361 re-aimed this at the RESUME skip specifically. It was written when
    # the classifier had a single, conflated skip path, so "the skip path for gate
    # entries" was unambiguous. It no longer is: BILL-361 split that into the tier
    # skip (reads no gates.json entry at all) and the resume skip (reads one, still
    # sha-gated). The sha rule survives on the resume skip only, which is what the
    # assertions below now pin — the tier skip must NOT acquire a sha precondition,
    # because requiring one is precisely the bug BILL-361 fixed.
    def test_skip_requires_sha_match(self):
        text = _classifier_text()
        lowered = text.lower()
        assert "sha" in lowered and "head" in lowered
        paragraphs = re.split(r"\n\s*\n", lowered)
        assert any(
            "sha" in p and ("current head" in p or "head sha" in p) and ("gate" in p or "gates.json" in p)
            for p in paragraphs
        ), (
            "pr-size-classifier.md must state the resume skip's gate-entry read "
            "fires only when sha == current HEAD"
        )
        assert any(
            "sha" in p and ("meta.tier" in p or "meta" in p and "tier" in p)
            for p in paragraphs
        ), (
            "pr-size-classifier.md must state the persisted meta.tier is also "
            "subject to the sha-match rule (C3 applies twice, independently)"
        )
        # Adversary gap (state interaction): "applies twice" could be read as
        # a single combined check — a classifier might only reclassify when
        # BOTH the gate entry AND meta.tier are stale, which is a weaker
        # guarantee than the ticket's "independently". Pin that the doc
        # states the two checks are independent of each other.
        assert "independent" in lowered, (
            "pr-size-classifier.md must state the two sha-match applications "
            "(gate entries, meta.tier) are INDEPENDENT of each other — a stale "
            "meta.tier forces reclassification even if a sibling gates.json "
            "entry still matches HEAD, and vice versa"
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


# --- Regression guards (SLOPSTOP PRAGMA coverage-backfill) -----------------
#
# These two pin pre-existing behavior this ticket must NOT change, per C17
# and the SKILL.md line-limit DoD item. They pass at Phase 0 (before this
# ticket touched anything) by construction — that is the point of a
# regression guard — so per the Phase 0 freeze rule ("only tests observed
# FAILING at 0d may enter that commit") they were withheld from the Phase 0
# red-test commit and land here instead, in their own commit, declared with
# the established coverage-backfill convention (see BILL-354 commits
# b91ed3f/46f47da for precedent).


class TestUniversalBlockUnchanged:
    """Guards the mirrored universal rules.

    Re-aimed 2026-08-01 (the "grand synchronization"): the rules moved out of a
    BEGIN/END-delimited region inside CLAUDE.md and into a standalone
    CLAUDE-universal.md, imported by a one-line `@CLAUDE-universal.md`. The old
    marker-bounded extraction is gone because the markers are gone; the guard
    itself is not weakened -- it now diffs the WHOLE file against the merge-base,
    which is strictly more coverage than the region ever gave.
    """

    IMPORT_LINE = "@CLAUDE-universal.md"

    def _at_merge_base(self, path_in_repo):
        """File content at the merge-base with master, or None if absent there."""
        import subprocess

        for ref in ("origin/master", "master"):
            mb = subprocess.run(
                ["git", "merge-base", "HEAD", ref],
                cwd=REPO_ROOT, capture_output=True, text=True,
            )
            if mb.returncode == 0 and mb.stdout.strip():
                break
        assert mb.returncode == 0 and mb.stdout.strip(), (
            "could not determine merge-base with master/origin/master"
        )
        got = subprocess.run(
            ["git", "show", f"{mb.stdout.strip()}:{path_in_repo}"],
            cwd=REPO_ROOT, capture_output=True, text=True,
        )
        return got.stdout if got.returncode == 0 else None

    def test_universal_rules_file_exists(self):
        assert UNIVERSAL_MD.is_file(), (
            f"{UNIVERSAL_MD.name} must exist at the repo root — it is the "
            "reference copy mirrored into every other project"
        )
        assert UNIVERSAL_MD.read_text().strip(), f"{UNIVERSAL_MD.name} is empty"

    def test_claude_md_imports_it_and_keeps_no_markers(self):
        lines = CLAUDE_MD.read_text().split("\n")
        n = sum(1 for l in lines if l.strip() == self.IMPORT_LINE)
        assert n == 1, (
            f"CLAUDE.md must contain exactly one whole-line '{self.IMPORT_LINE}' "
            f"import (found {n}). A backticked or indented mention does not count "
            "and does not import."
        )
        # An import inside a fenced block is silently inert: it looks correct and
        # loads nothing. Cheapest possible check for the most invisible failure.
        fenced, inside = False, False
        for l in lines:
            if l.lstrip().startswith("```"):
                fenced = not fenced
            elif l.strip() == self.IMPORT_LINE and fenced:
                inside = True
        assert not inside, (
            "the @CLAUDE-universal.md import sits inside a ``` fence — import "
            "parsing skips code blocks, so the rules would silently not load"
        )
        for marker in ("<!-- BEGIN UNIVERSAL SECTION -->",
                       "<!-- END UNIVERSAL SECTION -->"):
            assert marker not in lines, (
                f"CLAUDE.md still carries a live {marker} line; the marker/splice "
                "mechanism was retired 2026-08-01 in favour of CLAUDE-universal.md"
            )

    def test_universal_rules_unchanged_from_merge_base(self):
        current = UNIVERSAL_MD.read_text()
        base = self._at_merge_base(UNIVERSAL_MD.name)
        if base is None:
            pytest.skip(
                f"{UNIVERSAL_MD.name} does not exist at the merge-base — expected "
                "only on the branch that introduces it; the guard arms once merged"
            )
        assert current == base, (
            f"{UNIVERSAL_MD.name} must be byte-identical to its state at the "
            "merge-base (C17). It is mirrored into eight other repositories, so "
            "an edit here that is not deliberately propagated silently drifts the "
            "fleet. To change the rules: edit it, then run "
            "tools/fleet-sync/migrate-universal-block.py --apply."
        )


class TestPrSpineLineCeiling:
    # SLOPSTOP PRAGMA coverage-backfill: regression guard pinning the DoD's
    # explicit "SKILL.md <= 350 lines" ceiling — the spine sits at exactly
    # 150 lines (the BILL-325 target) after this ticket's edits, well under
    # the ceiling, so this legitimately passes at BASE too.
    def test_pr_spine_within_line_limit(self):
        line_count = len(_text(PR_SPINE).splitlines())
        assert line_count <= 350, (
            f"skills/pr/SKILL.md must stay <= 350 lines, is {line_count}"
        )
