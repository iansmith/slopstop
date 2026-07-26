"""
Phase 0 red tests for BILL-328 — a Definition-of-Done gate in :merge.

Transcribed from the ticket's Test expectations
(https://github.com/iansmith/slopstop/issues/328). Transcription, not authorship:
every assertion and every expected value below is pinned by the ticket, and per
the fleet brief's hard constraint 9 the implementer may not renegotiate them. If
one is wrong, the sanctioned exit is the TICKET UNDERSPECIFIED halt (TD-4a), not
an edit to this file.

The problem: `skills/merge/` has no DoD gate. `run-verification.md` scores the DoD
item by item but only on the `:run` path, and `:document` posts a DoD-confirmation
comment *after* the merge, best-effort. So `:plan` -> `:pr` -> `:merge` never checks
it, while the published site says the DoD is "the only way a ticket's implementation
can be merged".

The design, as settled in the grill and two adversary cycles:

- A shared scorer at `skills/run/references/dod-scoring.md`, adopted by THREE callers
  (`:merge`, `:run`, `:document`). Justified on universal §5 (one definition per
  value), NOT §4 (dedupe) — the two existing implementations are different in kind.
  `run-verification.md` is an adversary charter naming no evidence sources;
  `document-dod-assembly.md` is an evidence-source list. Nothing is extracted from
  `run-verification.md`; it adopts the scorer by pointer.
- Evidence is lifecycle-conditional. `:merge` runs pre-merge, where
  `gh pr list --state merged` returns nothing — a post-merge-only scorer would score
  every `:merge` item `unverifiable`.
- Two vacuous-test traps were removed before this file was written, and the reasoning
  is preserved here so nobody reintroduces them:
  * A `≤ 350` line-limit assertion on the merge spine would be green before AND after
    (the spine is 127 lines). The real budget is BILL-324's 150-line target, already
    covered by `test_bill324_behaviors.py::test_spine_is_within_the_line_target`.
    There is deliberately NO line-limit test here.
  * `test_shared_scoring_defined_once` asserts the marker heading appears exactly once
    AND that the file is `dod-scoring.md`. The count alone is already 1 today (in
    `document-dod-assembly.md`), so a count-only check would prove nothing.

These tests FAIL on current code and turn GREEN once the gate lands.

Test command:
    python3 -m pytest tests/test_bill328_behaviors.py -v
"""

import pytest

from conftest import SKILLS_DIR, ref, section, spine

# The one marker string. Both the DoD checkbox and the uniqueness test key on it.
MARKER = "## Evidence-gathering sources (per DoD item)"

# The cross-skill pointer every caller uses to reach the shared scorer. Cross-skill
# pointing is the established pattern — a dozen skills already read
# `slopstop-start-refs/tracking-dir-resolution.md`.
SHARED_POINTER = "slopstop-run-refs/dod-scoring.md"

# Pinned by the ticket. The implementer may not renegotiate these.
VERDICTS = ("met", "not-met", "unverifiable")
CONFIG_KEY = "on_dod_not_met"
CONFIG_VALUES = ("abort", "warn")

DOD_SCORING = SKILLS_DIR / "run" / "references" / "dod-scoring.md"
MERGE_DOD_GATE = SKILLS_DIR / "merge" / "references" / "merge-dod-gate.md"


def _read(path):
    """Read a file that does not exist yet without exploding the whole module."""
    return path.read_text() if path.exists() else ""


def _manifest(skill):
    path = SKILLS_DIR / skill / "references" / "manifest.txt"
    return [line.strip() for line in path.read_text().splitlines() if line.strip()]


def _files_containing(needle):
    """Every .md under skills/ whose text contains `needle`."""
    return sorted(
        p.relative_to(SKILLS_DIR).as_posix()
        for p in SKILLS_DIR.rglob("*.md")
        if needle in p.read_text()
    )


# --------------------------------------------------------------------------
# Behavior 1 — :merge reads the DoD, with a fallback source
# --------------------------------------------------------------------------


def test_merge_spine_has_dod_gate():
    """Step 1 names the DoD gate as a decision and points at its reference.

    Step headings are matched with a boundary, not as a bare substring: BILL-325
    records that `"Step 1" in spine` is satisfied by `## Step 10`.
    """
    text = spine("merge")
    step1 = section(text, "## Step 1")
    assert step1, "merge/SKILL.md has no '## Step 1' heading"
    assert "Definition of Done" in step1, (
        "Step 1 does not name the Definition of Done gate. The spine keeps the "
        "*decisions* (merge-pr-resolution.md:3); the gate is one of them."
    )
    assert "merge-dod-gate.md" in step1, (
        "Step 1 does not point at merge-dod-gate.md"
    )


def test_dod_gate_documents_fallback_source():
    """merge-dod-gate.md names BOTH DoD sources, not just the primary one.

    Guards behavior 1, which is otherwise satisfiable by a single-source lookup
    that silently disables the gate whenever the tracking dir is archived.
    """
    text = _read(MERGE_DOD_GATE)
    assert "task_plan.md" in text, "merge-dod-gate.md does not name task_plan.md"
    assert "## Definition of Done" in text, (
        "merge-dod-gate.md does not name the '## Definition of Done' section it reads"
    )
    assert "ticket body" in text.lower(), (
        "merge-dod-gate.md does not name the ticket-body fallback"
    )


def test_missing_dod_is_not_an_error():
    """No DoD anywhere is a proceed-and-say-so, distinct from the abort path.

    Guards behavior 4. The two must not collapse: a ticket with no DoD is not the
    same as a ticket whose DoD failed, and conflating them turns every un-planned
    ticket into a blocked merge.
    """
    text = _read(MERGE_DOD_GATE)
    assert "proceed" in text.lower(), (
        "merge-dod-gate.md does not document the no-DoD path as proceeding"
    )
    assert CONFIG_KEY in text, (
        f"merge-dod-gate.md does not mention {CONFIG_KEY}, so the no-DoD path "
        "cannot be textually distinguished from the abort path"
    )


# --------------------------------------------------------------------------
# Behavior 2 — three verdicts, lifecycle-conditional evidence
# --------------------------------------------------------------------------


def test_dod_scoring_names_three_verdicts():
    """The shared scorer pins the verdict vocabulary and both evidence sets.

    The three-verdict scheme is NEW in this ticket — neither existing caller has
    it — which makes it the single most renegotiable value in the contract, and
    the reason it gets an explicit test.
    """
    text = _read(DOD_SCORING)
    assert text, f"{DOD_SCORING.relative_to(SKILLS_DIR)} does not exist"
    for verdict in VERDICTS:
        assert verdict in text, f"dod-scoring.md does not name the verdict '{verdict}'"
    # Pre-merge evidence set (`:merge`, `:run`).
    for source in ("diff", "check-run", "Phase 0"):
        assert source.lower() in text.lower(), (
            f"dod-scoring.md does not name the pre-merge evidence source '{source}'"
        )
    # Post-merge evidence set (`:document`).
    for source in ("merge commit", "progress.md"):
        assert source.lower() in text.lower(), (
            f"dod-scoring.md does not name the post-merge evidence source '{source}'"
        )


# --------------------------------------------------------------------------
# Behavior 3 — the gate blocks, and has one configured escape hatch
# --------------------------------------------------------------------------


def test_dod_gate_is_a_blocking_gate():
    """The DoD gate is listed with the blocking gates, not the soft warnings.

    Placement IS the behavior: `merge-pr-resolution.md` splits
    `## Pre-merge gates (refuse-and-explain)` from `## Pre-merge soft warnings`,
    and everything in the latter can be confirmed past.
    """
    text = ref("merge", "merge-pr-resolution.md")
    gates = section(text, "## Pre-merge gates")
    warnings = section(text, "## Pre-merge soft warnings")
    assert gates, "merge-pr-resolution.md has no '## Pre-merge gates' section"
    assert "Definition of Done" in gates, (
        "The DoD gate is not listed under '## Pre-merge gates (refuse-and-explain)'"
    )
    assert "Definition of Done" not in warnings, (
        "The DoD gate is listed under '## Pre-merge soft warnings' — a soft warning "
        "can be confirmed past, which is not a gate"
    )


def test_on_dod_not_met_documented():
    """merge-autonomous.md documents the key, both values, and the default."""
    text = ref("merge", "merge-autonomous.md")
    assert CONFIG_KEY in text, f"merge-autonomous.md does not document {CONFIG_KEY}"
    for value in CONFIG_VALUES:
        assert f"`{value}`" in text or f'"{value}"' in text, (
            f"merge-autonomous.md does not document the value '{value}'"
        )
    key_section = text[text.index(CONFIG_KEY):]
    assert "default" in key_section[:600].lower(), (
        f"merge-autonomous.md does not state a default for {CONFIG_KEY} "
        "(the ticket pins it to 'abort')"
    )


# --------------------------------------------------------------------------
# Behavior 5 — one definition, three callers, and :document's own rendering
# --------------------------------------------------------------------------


def test_shared_scoring_defined_once():
    """The marker heading appears exactly once, and in dod-scoring.md.

    BOTH halves are load-bearing. The heading already appears exactly once today
    (in document-dod-assembly.md), so a count-only assertion is green before and
    after — it would enter the frozen baseline proving nothing.
    """
    carriers = _files_containing(MARKER)
    assert carriers == ["run/references/dod-scoring.md"], (
        f"Expected the marker heading in exactly dod-scoring.md, found it in: "
        f"{carriers or 'no file'}"
    )


@pytest.mark.parametrize(
    "skill,filename",
    [
        ("merge", "merge-dod-gate.md"),
        ("run", "run-verification.md"),
        ("document", "document-dod-assembly.md"),
    ],
)
def test_all_three_callers_read_shared_scorer(skill, filename):
    """Each of the three callers reaches the shared scorer by pointer.

    Parametrized so a two-of-three pass is a visible fail rather than a green run
    with one caller quietly left on its own scoring.
    """
    path = SKILLS_DIR / skill / "references" / filename
    text = _read(path)
    assert text, f"{skill}/references/{filename} does not exist"
    assert SHARED_POINTER in text, (
        f"{skill}/references/{filename} does not point at {SHARED_POINTER}"
    )


def test_run_verification_adopts_shared_scorer():
    """:run keeps its fleet-only charter AND adopts the scorer.

    Asserts adoption, not removal. Nothing is extracted from this file — a test
    asserting a block disappeared would assert the removal of something that was
    never there.
    """
    text = ref("run", "run-verification.md")
    assert SHARED_POINTER in text, (
        "run-verification.md does not point at the shared scorer"
    )
    for fleet_only in ("file map", "tamper", "shadow"):
        assert fleet_only.lower() in text.lower(), (
            f"run-verification.md lost its fleet-only check '{fleet_only}' — the "
            "charter stays, only the scoring vocabulary is shared"
        )


def test_document_maps_three_verdicts_to_two_states():
    """:document maps the scorer's three verdicts onto its two states.

    Guards behavior 5's "cannot disagree" claim, which an unspecified mapping
    defeats: three verdicts rendered into ✅/⚠️ with no stated rule is exactly
    where the paths would drift.
    """
    text = ref("document", "document-dod-assembly.md")
    for verdict in VERDICTS:
        assert verdict in text, (
            f"document-dod-assembly.md does not state how '{verdict}' renders"
        )
    assert "✅" in text and "⚠️" in text, (
        "document-dod-assembly.md lost its two-state vocabulary"
    )


def test_document_keeps_its_comment_template():
    """The move takes lines 22-26 only; :document's own rendering stays.

    Paired boundary guard for the move — the same moved-out/still-exists pattern
    BILL-324 used. Green before and after by design: its job is to fail if the
    move over-reaches.
    """
    text = ref("document", "document-dod-assembly.md")
    assert "Definition of Done — Confirmation" in text, (
        "document-dod-assembly.md lost its comment-assembly template"
    )
    assert "Never fake a confirmation" in text, (
        "document-dod-assembly.md lost line 28's honesty rule — only lines 22-26 move"
    )
    assert "$EXPECTED_DOD" in text, (
        "document-dod-assembly.md lost line 30's $EXPECTED_DOD assignment, leaving "
        "Step 3b with nothing that assigns its own variable"
    )


# --------------------------------------------------------------------------
# Both new reference files must be declared, or Desktop installs miss them
# --------------------------------------------------------------------------


def test_dod_gate_reference_declared():
    """Both new files exist AND appear in their directory's manifest.

    Both halves for each. `install-for-claude-desktop.sh:62` fetches only what a
    manifest names, so an undeclared file is silently absent from every Desktop
    install — and for dod-scoring.md it additionally dangles the pointer
    merge-dod-gate.md makes.
    """
    assert MERGE_DOD_GATE.exists(), "merge-dod-gate.md does not exist"
    assert "merge-dod-gate.md" in _manifest("merge"), (
        "merge-dod-gate.md is not declared in skills/merge/references/manifest.txt"
    )
    assert DOD_SCORING.exists(), "dod-scoring.md does not exist"
    assert "dod-scoring.md" in _manifest("run"), (
        "dod-scoring.md is not declared in skills/run/references/manifest.txt"
    )
