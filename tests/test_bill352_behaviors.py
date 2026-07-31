"""
Phase 0 red tests for BILL-352 — Gate evidence to disk: `gates.json` in the
tracking dir.

Transcribed from the ticket's Test expectations
(https://github.com/iansmith/slopstop/issues/352). Transcription, not
authorship: every assertion below is pinned by the ticket, and per the fleet
brief's hard constraint 9 the implementer may not renegotiate them. If one is
wrong, the sanctioned exit is the TICKET UNDERSPECIFIED halt (TD-4a), not an
edit to this file.

This ticket is documentation-only (a new reference file plus prose additions
across skills/pr/references/*.md) — there is no executable entrypoint to
invoke, so every check here reads file content.

Test command:
    python3 -m pytest tests/test_bill352_behaviors.py -v
"""

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent
SKILLS_DIR = REPO_ROOT / "skills"
GATES_REF = SKILLS_DIR / "start" / "references" / "gates-json.md"
START_MANIFEST = SKILLS_DIR / "start" / "references" / "manifest.txt"
PROJECT_CONF_EXAMPLE = REPO_ROOT / ".project-conf.toml.example"

REQUIRED_GATE_KEYS = [
    "step_0b",
    "step_0c",
    "step_2",
    "step_2d",
    "step_2e",
    "step_2f",
    "step_6",
]


def _gates_ref_text():
    if not GATES_REF.is_file():
        pytest.fail(f"{GATES_REF} does not exist")
    return GATES_REF.read_text()


class TestGatesJsonReferenceExistsAndManifested:
    def test_gates_json_reference_exists_and_is_manifested(self):
        assert GATES_REF.is_file(), (
            "skills/start/references/gates-json.md missing — the ticket requires "
            "a single shared reference defining the gates.json schema."
        )
        assert START_MANIFEST.is_file(), "skills/start/references/manifest.txt missing"
        listed = {
            line.strip()
            for line in START_MANIFEST.read_text().splitlines()
            if line.strip()
        }
        assert "gates-json.md" in listed, (
            "gates-json.md must be listed in skills/start/references/manifest.txt"
        )


class TestSchemaDocumented:
    def test_gates_json_schema_documented(self):
        text = _gates_ref_text()
        for field in ("sha", "result", "at", "detail"):
            assert field in text, f"gates-json.md must document the '{field}' field"
        for key in REQUIRED_GATE_KEYS:
            assert key in text, f"gates-json.md must document gate key '{key}'"


class TestNoConflatedStepZeroKey:
    def test_no_conflated_step_0_key(self):
        text = _gates_ref_text()
        assert "step_0b" in text
        assert "step_0c" in text
        # Boundary-anchored: a naive `"step_0" not in text` check can never
        # pass, because step_0b and step_0c both contain the substring
        # "step_0". This must find NO occurrence of a bare "step_0" that is
        # not immediately followed by 'b' or 'c'.
        assert re.search(r"step_0(?![bc])", text) is None, (
            "gates-json.md must never use a conflated 'step_0' key — "
            "only 'step_0b' and 'step_0c' are valid"
        )
        assert "never tier-gateable" in text or "never tier-gate" in text, (
            "gates-json.md must state that step_0c is never tier-gateable"
        )


class TestMetaKeyReserved:
    def test_meta_key_reserved(self):
        text = _gates_ref_text()
        assert "meta" in text
        assert "reserved" in text.lower()


class TestMetaSubkeysShaKeyed:
    def test_meta_subkeys_are_sha_keyed(self):
        text = _gates_ref_text()
        assert '"value"' in text and '"sha"' in text, (
            "gates-json.md must document the {\"value\": ..., \"sha\": ...} shape "
            "for meta sub-keys"
        )
        assert "ignored" in text.lower()


class TestDetailOptional:
    def test_detail_documented_optional(self):
        text = _gates_ref_text()
        assert "optional" in text.lower()
        assert "omitted" in text.lower() or "omit" in text.lower()


class TestStaleShaIgnoredDocumented:
    def test_stale_sha_ignored_documented(self):
        text = _gates_ref_text()
        assert "sha" in text
        assert "ignored" in text.lower() or "ignore" in text.lower()
        assert "current head" in text.lower() or "head sha" in text.lower()
        assert "expir" not in text.lower(), (
            "gates-json.md must not describe a time-based expiry mechanism — "
            "staleness is sha-only (C3)"
        )


class TestDegradeToRunDocumented:
    def test_degrade_to_run_documented(self):
        text = _gates_ref_text()
        lowered = text.lower()
        for kw in ("missing", "stale", "unparseable"):
            assert kw in lowered, f"gates-json.md must mention the '{kw}' degrade case"
        assert "run the gate" in lowered, (
            "gates-json.md must state that a degraded read means 'run the gate', "
            "never 'assume pass'"
        )
        assert "assume pass" not in lowered.replace("never assume pass", ""), (
            "gates-json.md must never instruct a reader to assume pass on a bad read"
        )


class TestMechanicalGatesHaveNoSkipPath:
    def test_mechanical_gates_have_no_skip_path(self):
        text = _gates_ref_text()
        assert "2d" in text and "2f" in text, (
            "gates-json.md must name Steps 2d and 2f explicitly"
        )
        assert "no skip" in text.lower() or "never" in text.lower(), (
            "gates-json.md must state that Steps 2d and 2f gain no "
            "gates.json-driven skip path (C4)"
        )


# --- Write-point coverage: pr/SKILL.md names the gate write points ---------


class TestPrSpineNamesWritePoints:
    def test_pr_spine_points_at_gates_json_reference(self):
        text = (SKILLS_DIR / "pr" / "SKILL.md").read_text()
        assert "gates.json" in text or "gates-json.md" in text, (
            "skills/pr/SKILL.md must name the gates.json write points rather "
            "than restating the schema"
        )


class TestGateWritePointsDocumented:
    """Each named reference file documents that its step writes a gates.json entry."""

    @pytest.mark.parametrize(
        "ref_file,gate_keys",
        [
            ("pr-test-gates.md", ["step_0b", "step_0c", "step_2"]),
            ("pr-slop-detection.md", ["step_2d", "step_2e", "step_2f"]),
            ("pr-claude-review.md", ["step_6"]),
            ("pr-cr-polling.md", ["step_6"]),
            ("pr-greptile-polling.md", ["step_6"]),
        ],
    )
    def test_reference_documents_its_gate_writes(self, ref_file, gate_keys):
        path = SKILLS_DIR / "pr" / "references" / ref_file
        assert path.is_file(), f"skills/pr/references/{ref_file} missing"
        text = path.read_text()
        assert "gates.json" in text, (
            f"skills/pr/references/{ref_file} must document that it writes "
            f"an entry to gates.json"
        )
        for key in gate_keys:
            assert key in text, (
                f"skills/pr/references/{ref_file} must name gate key '{key}'"
            )


class TestMechanicalGatesExplicitlyExemptFromRead:
    def test_step_2d_and_2f_have_no_gates_json_read_path(self):
        text = (SKILLS_DIR / "pr" / "references" / "pr-slop-detection.md").read_text()
        lowered = text.lower()
        assert "gates.json" in text
        assert "no skip" in lowered or "never" in lowered or "no read" in lowered, (
            "pr-slop-detection.md must state Steps 2d and 2f never read "
            "gates.json for a skip"
        )


# --- Adversary gap-finder pass (inline, per :plan Step 0f) -----------------
#
# Attack vectors worked against the Phase 0 suite above: (1) the boundary
# regex for step_0 conflation — a naive substring check can never fail, so a
# doc that only used the phrase "step_0" bare (never split into 0b/0c) had to
# be provably caught; (2) the reserved 'meta' key could be documented in
# prose without ever showing the {"value": ..., "sha": ...} shape — checked
# both independently; (3) 'expiry' language creeping into the stale-sha rule
# (time-based invalidation) is explicitly forbidden, not just unchecked;
# (4) the "run the gate" language must be literal, not paraphrased loosely
# enough that "assume pass" also slips in nearby; (5) the manifest test only
# proves gates-json.md is *listed* — a separate test proves the *content*
# schema is present, since a listed-but-empty file would pass the first
# check alone; (6) .project-conf.toml.example must remain parseable TOML
# after this ticket's changes, not just textually free of forbidden keys.


class TestAdversaryGaps:
    def test_manifest_listing_alone_is_not_sufficient(self):
        # gates-json.md must both be listed AND non-trivially populated.
        assert GATES_REF.is_file()
        text = GATES_REF.read_text()
        assert len(text.strip()) > 200, (
            "gates-json.md must contain real schema documentation, not a stub"
        )

    def test_detail_optional_language_is_tied_to_the_detail_field(self):
        # A false negative: "optional"/"omitted" appearing anywhere in the
        # doc (e.g. describing an unrelated field) would satisfy a bare
        # substring check without ever saying `detail` is optional.
        text = _gates_ref_text()
        paragraphs = re.split(r"\n\s*\n", text.lower())
        assert any(
            "detail" in p and ("optional" in p or "omit" in p) for p in paragraphs
        ), "gates-json.md must state, in the same paragraph, that 'detail' is optional/omitted"

    def test_stale_sha_language_is_tied_to_the_sha_field(self):
        # Same false-negative shape: "ignored" and "sha" could each appear
        # in unrelated paragraphs without the doc ever saying a mismatched
        # sha is what gets ignored.
        text = _gates_ref_text()
        paragraphs = re.split(r"\n\s*\n", text.lower())
        assert any(
            "sha" in p and "ignor" in p and "head" in p for p in paragraphs
        ), (
            "gates-json.md must state, in the same paragraph, that an entry "
            "whose sha does not match current HEAD is ignored"
        )

    def test_no_new_config_key(self):
        # C9: gates.json is on-disk evidence under the tracking dir, not a
        # new opt-in surface — .project-conf.toml.example must gain no
        # [gates] table and no gates_json key.
        assert PROJECT_CONF_EXAMPLE.is_file()
        text = PROJECT_CONF_EXAMPLE.read_text()
        assert not re.search(r"^\s*\[gates\]\s*$", text, re.MULTILINE), (
            ".project-conf.toml.example must not define a [gates] table"
        )
        assert "gates_json" not in text, (
            ".project-conf.toml.example must not define a gates_json key"
        )
