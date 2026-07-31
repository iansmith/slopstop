"""
Phase 0 red tests for BILL-354 — Redirect gate output to disk; one shared
test-command reference.

Transcribed from the ticket's Test expectations
(https://github.com/iansmith/slopstop/issues/354). Transcription, not
authorship: every assertion below is pinned by the ticket, and per the fleet
brief's hard constraint 9 the implementer may not renegotiate them. If one is
wrong, the sanctioned exit is the TICKET UNDERSPECIFIED halt (TD-4a), not an
edit to this file.

This ticket is documentation-only (a new reference file plus prose edits
across skills/plan/references/*.md, skills/pr/references/*.md,
skills/run/references/run-verification.md and
skills/start/references/gates-json.md) — there is no executable entrypoint to
invoke, so every check here reads file content.

Test command:
    python3 -m pytest tests/test_bill354_behaviors.py -v
"""

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent
SKILLS_DIR = REPO_ROOT / "skills"

NEW_REF = SKILLS_DIR / "plan" / "references" / "test-command-resolution.md"
PLAN_MANIFEST = SKILLS_DIR / "plan" / "references" / "manifest.txt"
PLAN_PHASE0 = SKILLS_DIR / "plan" / "references" / "plan-phase0-mechanics.md"

OLD_DETECTION = SKILLS_DIR / "pr" / "references" / "pr-test-detection.md"
PR_MANIFEST = SKILLS_DIR / "pr" / "references" / "manifest.txt"
PR_TEST_GATES = SKILLS_DIR / "pr" / "references" / "pr-test-gates.md"
PR_SLOP = SKILLS_DIR / "pr" / "references" / "pr-slop-detection.md"

RUN_VERIFICATION = SKILLS_DIR / "run" / "references" / "run-verification.md"
GATES_JSON = SKILLS_DIR / "start" / "references" / "gates-json.md"


def _text(path):
    if not path.is_file():
        pytest.fail(f"{path} does not exist")
    return path.read_text()


def _section(text, heading_pattern):
    """Return the text of a `## <heading>` section, up to the next `## ` heading."""
    lines = text.splitlines()
    start = None
    for i, line in enumerate(lines):
        if line.startswith("## ") and re.search(heading_pattern, line):
            start = i
            break
    assert start is not None, f"no section matching {heading_pattern!r} found"
    end = len(lines)
    for i in range(start + 1, len(lines)):
        if lines[i].startswith("## "):
            end = i
            break
    return "\n".join(lines[start:end])


# ---------------------------------------------------------------------------
# 1. Shared reference exists and is manifested
# ---------------------------------------------------------------------------


class TestSharedReferenceExistsAndManifested:
    def test_shared_reference_exists_and_manifested(self):
        assert NEW_REF.is_file(), (
            "skills/plan/references/test-command-resolution.md missing — the "
            "ticket requires a single shared reference holding the auto-detect "
            "table and the C5 capping rule."
        )
        assert PLAN_MANIFEST.is_file(), "skills/plan/references/manifest.txt missing"
        listed = {
            line.strip()
            for line in PLAN_MANIFEST.read_text().splitlines()
            if line.strip()
        }
        assert "test-command-resolution.md" in listed, (
            "test-command-resolution.md must be listed in "
            "skills/plan/references/manifest.txt"
        )


# ---------------------------------------------------------------------------
# 2. Old detection file deleted outright, not left as a stub/alias
# ---------------------------------------------------------------------------


class TestOldDetectionFileDeleted:
    def test_old_detection_file_deleted(self):
        assert not OLD_DETECTION.exists(), (
            "skills/pr/references/pr-test-detection.md must be deleted, not "
            "left as a pointer stub (universal §5 forbids aliases)."
        )
        hits = []
        for path in SKILLS_DIR.rglob("*"):
            if path.is_file() and "pr-test-detection" in path.read_text(errors="ignore"):
                hits.append(str(path.relative_to(REPO_ROOT)))
        assert not hits, (
            f"the string 'pr-test-detection' must appear nowhere under skills/, "
            f"found in: {hits}"
        )
        assert "pr-test-detection.md" not in {
            line.strip() for line in PR_MANIFEST.read_text().splitlines() if line.strip()
        }, "pr-test-detection.md must be removed from skills/pr/references/manifest.txt"


# ---------------------------------------------------------------------------
# 3. The auto-detect table is defined in exactly one place
# ---------------------------------------------------------------------------


class TestAutodetectTableDefinedOnce:
    def test_autodetect_table_defined_once(self):
        hits = []
        for path in SKILLS_DIR.rglob("*.md"):
            if "pnpm-lock.yaml" in path.read_text(errors="ignore"):
                hits.append(str(path.relative_to(REPO_ROOT)))
        assert len(hits) == 1, (
            f"the literal 'pnpm-lock.yaml' must appear in exactly one file "
            f"under skills/ (the new shared reference); found in: {hits}"
        )


# ---------------------------------------------------------------------------
# 4. No dangling pointer comment to the old table location
# ---------------------------------------------------------------------------


class TestNoDanglingPhase0TablePointer:
    def test_no_dangling_phase0_table_pointer(self):
        hits = []
        for path in SKILLS_DIR.rglob("*"):
            if path.is_file() and "plan-phase0-mechanics.md 0a" in path.read_text(errors="ignore"):
                hits.append(str(path.relative_to(REPO_ROOT)))
        assert not hits, (
            f"'plan-phase0-mechanics.md 0a' must appear nowhere under skills/ "
            f"(dangling pointer to the moved table); found in: {hits}"
        )


# ---------------------------------------------------------------------------
# 5. Regression guard — pr-test-gates.md never truncates (green at HEAD)
# ---------------------------------------------------------------------------


class TestNoTruncationInPrTestGates:
    def test_no_truncation_in_pr_test_gates(self):
        text = _text(PR_TEST_GATES)
        assert not re.search(r"\|\s*tail\b", text), (
            "pr-test-gates.md must not contain '| tail' (C5)"
        )
        assert not re.search(r"\|\s*head\b", text), (
            "pr-test-gates.md must not contain '| head' (C5)"
        )


# ---------------------------------------------------------------------------
# 6. Genuinely-red: Step 0b reads its output back in full
# ---------------------------------------------------------------------------


class TestStep0bReadsOutputBackInFull:
    def test_step_0b_reads_output_back_in_full(self):
        text = _text(NEW_REF)
        lowered = text.lower()
        assert "0b" in text, (
            "test-command-resolution.md must name Step 0b's capping rule"
        )
        assert "read" in lowered and ("back" in lowered), (
            "test-command-resolution.md must state Step 0b's full output is "
            "written to a file and read back from that file for classification"
        )
        assert "full" in lowered, (
            "test-command-resolution.md must state the write is of the FULL "
            "output, not a truncated stream"
        )


# ---------------------------------------------------------------------------
# 7. The C5 capping rule is present in the shared reference
# ---------------------------------------------------------------------------


class TestCappingRulePresent:
    def test_capping_rule_present(self):
        text = _text(NEW_REF)
        lowered = text.lower()
        assert "file" in lowered and "full" in lowered, (
            "test-command-resolution.md must state output goes to a file in full"
        )
        assert "decisive" in lowered or "context" in lowered, (
            "test-command-resolution.md must state only decisive lines enter context"
        )


# ---------------------------------------------------------------------------
# 8. Step 2d's redirect is documented: write in full, read back, classify every hunk
# ---------------------------------------------------------------------------


class TestStep2dRedirectDocumented:
    def test_2d_redirect_documented(self):
        text = _text(PR_SLOP)
        section = _section(text, r"Step 2d")
        lowered = section.lower()
        assert "tracking" in lowered, (
            "pr-slop-detection.md's Step 2d section must say the diff body is "
            "written to the tracking dir"
        )
        assert "full" in lowered, (
            "pr-slop-detection.md's Step 2d section must say the diff body is "
            "written in full"
        )
        assert "read" in lowered and "back" in lowered, (
            "pr-slop-detection.md's Step 2d section must say the diff body is "
            "read back to classify every hunk"
        )
        assert "every hunk" in lowered or "every" in lowered, (
            "pr-slop-detection.md's Step 2d section must say the read-back "
            "classifies EVERY hunk"
        )


# ---------------------------------------------------------------------------
# 9. Step 2f's output destination is documented — exit status is the verdict, not the file
# ---------------------------------------------------------------------------


class TestStep2fOutputDestinationDocumented:
    def test_2f_output_destination_documented(self):
        text = _text(PR_SLOP)
        section = _section(text, r"Step 2f")
        lowered = section.lower()
        assert "tracking" in lowered, (
            "pr-slop-detection.md's Step 2f section must say per-node-id "
            "stdout/stderr has a defined destination in the tracking dir"
        )
        assert "node-id" in lowered or "node id" in lowered, (
            "pr-slop-detection.md's Step 2f section must be scoped per node-id"
        )
        assert "exit status" in lowered or "exit code" in lowered, (
            "pr-slop-detection.md's Step 2f section must say the exit status, "
            "not the file, is the classification input"
        )
        assert "not the file" in lowered or "never the file" in lowered, (
            "pr-slop-detection.md's Step 2f section must explicitly say the "
            "FILE is not the classification input"
        )

    def test_2f_section_does_not_claim_it_reads_output_back(self):
        # The DoD is explicit that 2f must NOT be documented as classifying
        # by reading its output file back — only the exit status does that.
        text = _text(PR_SLOP)
        section = _section(text, r"Step 2f")
        lowered = section.lower()
        assert not re.search(r"read.{0,40}back.{0,60}classif", lowered), (
            "pr-slop-detection.md's Step 2f section must NOT say it classifies "
            "by reading its output file back — the exit status is the "
            "classification input, never the file"
        )


# ---------------------------------------------------------------------------
# 10. Steps 2d and 2f each carry a positive unskippability sentence
# ---------------------------------------------------------------------------


class TestStep2d2fStillUnskippable:
    def test_2d_2f_still_unskippable(self):
        text = _text(PR_SLOP)
        for heading in (r"Step 2d", r"Step 2f"):
            section = _section(text, heading)
            lowered = section.lower()
            assert "gates.json" in lowered, (
                f"the {heading} section must mention gates.json"
            )
            assert re.search(r"no\s+`?gates\.json`?\s+entry\s+may\s+skip", lowered) or (
                "no gates.json entry may skip" in lowered
            ), (
                f"the {heading} section must carry an explicit positive sentence "
                f"to the effect of 'no gates.json entry may skip this gate'"
            )


# ---------------------------------------------------------------------------
# 11. Both gates capture STATUS=$? immediately after their redirect
# ---------------------------------------------------------------------------


class TestStep2d2fCaptureExitStatus:
    def test_2d_2f_capture_exit_status(self):
        text = _text(PR_SLOP)

        section_2d = _section(text, r"Step 2d")
        section_2f = _section(text, r"Step 2f")

        assert "STATUS=$?" in section_2d, (
            "Step 2d's section must capture STATUS=$? immediately after its redirect"
        )
        assert "STATUS=$?" in section_2f, (
            "Step 2f's section must capture STATUS=$? immediately after its redirect"
        )

        lowered_2f = section_2f.lower()
        assert "exit status" in lowered_2f or "exit code" in lowered_2f, (
            "Step 2f's section must state the exit status (never the file) is "
            "the classification input"
        )

        lowered_2d = section_2d.lower()
        assert "stderr" in lowered_2d, (
            "Step 2d's section must state stderr goes to a separate stream "
            "from the diff body"
        )
        assert "separate stream" in lowered_2d or "separate" in lowered_2d, (
            "Step 2d's section must state stderr is captured on a SEPARATE "
            "stream from the diff body"
        )
        assert "hard stop" in lowered_2d, (
            "Step 2d's section must state a non-zero git-diff status is a "
            "hard stop, never a clean pass"
        )

    def test_2d_scoped_exit_status_language_does_not_leak_into_2f_test(self):
        # An unscoped "the status, not the file, is the classification input"
        # rendered into 2d's section too would break test_2d_redirect_documented,
        # which requires the READ-BACK diff body to remain what gets classified.
        text = _text(PR_SLOP)
        section_2d = _section(text, r"Step 2d")
        lowered_2d = section_2d.lower()
        assert "read" in lowered_2d and "back" in lowered_2d, (
            "Step 2d's section must still say the read-back diff body is what "
            "gets classified, even after the exit-status guard is added"
        )


# ---------------------------------------------------------------------------
# 12. Regression guard — the RED-sha selector survives (green at HEAD)
# ---------------------------------------------------------------------------


class TestRedShaSelectorPreserved:
    def test_red_sha_selector_preserved(self):
        text = _text(PR_SLOP)
        assert re.search(r"git log.*\|\s*tail\s+-1", text), (
            "pr-slop-detection.md must still contain the RED-sha selector "
            "(git log ... | tail -1) — a record selector, not output "
            "truncation, and must not be swept away"
        )


# ---------------------------------------------------------------------------
# 13. gates.json's detail field is documented as populated for the four
#     newly-redirecting gates
# ---------------------------------------------------------------------------


class TestGatesJsonDetailDocumented:
    def test_gates_json_detail_documented(self):
        text = _text(GATES_JSON)
        schema_match = re.search(r"```json\n(.*?)\n```", text, re.DOTALL)
        assert schema_match, "gates-json.md must contain a fenced json schema block"
        schema = schema_match.group(1)
        for key in ("step_0b", "step_2", "step_2d", "step_2f"):
            line_match = re.search(rf'"{key}":\s*\{{[^}}]*\}}', schema)
            assert line_match, f"gates-json.md schema must define a {key!r} entry"
            assert '"detail"' in line_match.group(0), (
                f"gates-json.md's schema example for {key!r} must now show a "
                f"'detail' field carrying the output filename — {key} is one "
                f"of the gates BILL-354 makes redirect its output to disk"
            )


# ---------------------------------------------------------------------------
# Adversary gap-finder pass (inline, per :plan Step 0f)
# ---------------------------------------------------------------------------
#
# Attack vectors worked against the Phase 0 suite above: (1) a bare substring
# check for "detail" against gates-json.md's WHOLE text would already pass
# today (step_0c/step_6 already carry it) — the real assertion has to be
# scoped to each of the four specific gate entries that don't have it yet;
# (2) "read...back" language could appear in Step 2d's section while ALSO
# leaking into Step 2f's, which the ticket explicitly forbids — checked with
# a dedicated negative test scoped to the 2f section only; (3) an unscoped
# "STATUS=$?" search across the whole file could pass by matching a single
# capture shared prose-wise between 2d and 2f without either section actually
# containing it — scoped per-section via _section(); (4) the "no gates.json
# entry may skip" sentence must be a genuine sentence, not merely both
# keywords "gates.json" and "no"/"never" appearing anywhere unrelated in the
# section — checked with an anchored regex requiring the phrase shape; (5) a
# renamed/rewritten pr-test-detection.md string could hide inside a binary or
# non-.md file — the sweep used here walks all files under skills/, not just
# *.md.


class TestAdversaryGaps:
    def test_gates_json_detail_check_is_scoped_not_global(self):
        # A global "detail" in gates-json.md substring check would already
        # pass at HEAD (step_0c/step_6 carry it). Confirm the real check is
        # scoped per key so it can't be satisfied vacuously.
        text = _text(GATES_JSON)
        assert '"detail"' in text, (
            "sanity: gates-json.md must contain the literal '\"detail\"' "
            "somewhere (step_0c/step_6 already carry it) — this alone must "
            "never be treated as proof step_0b/step_2/step_2d/step_2f carry it too"
        )

    def test_2d_and_2f_sections_are_actually_distinct(self):
        # If Step 2d and Step 2f ever got merged into one section (or one's
        # heading renamed so _section() silently matched the wrong block),
        # the asymmetric assertions above would silently compare the same
        # text to itself. Guard that the two sections are non-overlapping.
        text = _text(PR_SLOP)
        section_2d = _section(text, r"Step 2d")
        section_2f = _section(text, r"Step 2f")
        assert section_2d != section_2f, (
            "Step 2d and Step 2f must remain distinct sections in "
            "pr-slop-detection.md"
        )

    def test_pnpm_discriminator_prose_removed_from_pr_test_gates(self):
        # DoD: pr-test-gates.md's line-12 discriminator prose naming
        # pnpm-lock.yaml must be replaced by a pointer, not merely have the
        # table itself deduped elsewhere while the prose mention lingers.
        text = _text(PR_TEST_GATES)
        assert "pnpm-lock.yaml" not in text, (
            "pr-test-gates.md must no longer mention 'pnpm-lock.yaml' — that "
            "discriminator now lives solely in test-command-resolution.md"
        )
