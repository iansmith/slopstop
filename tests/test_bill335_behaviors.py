"""
Behavior tests for BILL-335 — decision provenance.

Source: post-mortem of the SlopCodeBench `file_backup` trial
(`~/slopmetrics/runs/file_backup/checkpoint_4-SUMMARY.md` §8). That trial produced 29
hidden-test failures from five root causes; two were PRD decisions that every
downstream gate ratified, and one was a crash on an invocation shape the
implementer's own tests never used.

These tests pin the four resulting changes:
  - `:design` can be told what the authoritative spec is (`--spec` / `[design] spec`)
  - every PRD decision is classified SPEC / DERIVED / UNDERDETERMINED
  - the ticket adversaries gain check F (provenance) and check G (circularity)
  - the ticket standard requires an entrypoint test run from outside the repo root

Test command:
    python3 -m pytest tests/test_bill335_behaviors.py -v
"""

import re
import tomllib
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent
DESIGN_SKILL = REPO_ROOT / "skills" / "design" / "SKILL.md"
TREE_ADVERSARY = REPO_ROOT / "skills" / "tickets" / "references" / "tickets-adversary.md"
SOLO_ADVERSARY = (
    REPO_ROOT / "skills" / "single-ticket" / "references" / "single-ticket-adversary.md"
)
TICKET_STANDARD = REPO_ROOT / "skills" / "tickets" / "references" / "ticket-standard.md"
CONFIG_MD = REPO_ROOT / "CONFIG.md"
EXAMPLE_CONF = REPO_ROOT / ".project-conf.toml.example"
CONF_OPTIONS = REPO_ROOT / "design" / "project-conf-options.md"

# The classification vocabulary is fixed by the ticket: exactly these three, uppercase.
CLASSIFICATIONS = ("SPEC", "DERIVED", "UNDERDETERMINED")

# Sentinel the PRD records when no spec is declared.
GREENFIELD_SENTINEL = "SPEC: none — greenfield"


def _section(text: str, heading: str, level: str = "## ") -> str:
    """Return the body of a markdown section, up to the next heading of the same level."""
    start = text.find(level + heading)
    if start == -1:
        return ""
    rest = text[start + len(level) + len(heading) :]
    end = rest.find("\n" + level)
    return rest if end == -1 else rest[:end]


def _round1_checks(text: str) -> str:
    """Return the check list inside an adversary's round-1 prompt template.

    Scoped deliberately: a check defined only in prose further down the file is not
    reachable by the adversary, which is handed the prompt template.
    """
    block = _section(text, "Prompt template (round 1)")
    start = block.find("Checks:")
    return "" if start == -1 else block[start:]


@pytest.fixture(scope="module")
def design_skill() -> str:
    return DESIGN_SKILL.read_text()


@pytest.fixture(scope="module")
def tree_adversary() -> str:
    return TREE_ADVERSARY.read_text()


@pytest.fixture(scope="module")
def solo_adversary() -> str:
    return SOLO_ADVERSARY.read_text()


@pytest.fixture(scope="module")
def ticket_standard() -> str:
    return TICKET_STANDARD.read_text()


def test_design_skill_documents_spec_argument(design_skill: str) -> None:
    """Behavior 1 — `:design` accepts a repeatable `--spec <path>`."""
    args = _section(design_skill, "Arguments")
    assert args, "skills/design/SKILL.md has no ## Arguments section"
    assert "--spec" in args, "--spec is not documented in :design's Arguments section"
    assert "repeatable" in args.lower(), (
        "--spec must be documented as repeatable — a run may cite more than one spec"
    )


def test_design_skill_records_spec_identity(design_skill: str) -> None:
    """Behavior 1 — the PRD records each spec's path and sha256, plus the absent case."""
    assert "sha256" in design_skill.lower(), (
        "the PRD must record each declared spec's sha256 so check F can prove it "
        "re-read the same document and detect drift"
    )
    assert GREENFIELD_SENTINEL in design_skill, (
        f"the no-spec sentinel {GREENFIELD_SENTINEL!r} must be documented — absent a "
        "spec the PRD records it rather than failing or adopting a file silently"
    )


def test_design_skill_requires_decision_provenance(design_skill: str) -> None:
    """Behavior 2 — every PRD decision carries a provenance classification."""
    step5 = _section(design_skill, "Step 5")
    assert step5, "skills/design/SKILL.md has no Step 5 section"
    for word in CLASSIFICATIONS:
        assert word in step5, (
            f"Step 5 must name the {word} classification; the vocabulary is exactly "
            f"{CLASSIFICATIONS}"
        )
    assert "Underdetermined decisions" in design_skill, (
        "the PRD format must mandate a `## Underdetermined decisions` section — that "
        "section is the first place to look when behavior turns out wrong"
    )


def test_adversary_has_provenance_and_circularity_checks(tree_adversary: str) -> None:
    """Behavior 3 and 4 — the tree adversary gains checks F and G."""
    checks = _round1_checks(tree_adversary)
    assert checks, "tickets-adversary.md round-1 prompt template has no Checks: block"
    assert re.search(r"^F\.\s", checks, re.M), (
        "check F (decision provenance) must appear in the round-1 check list, not "
        "only in prose elsewhere in the file"
    )
    assert re.search(r"^G\.\s", checks, re.M), (
        "check G (circular rationale) must appear in the round-1 check list"
    )
    # A–E must survive untouched; the ticket fences renumbering out of scope.
    for letter in "ABCDE":
        assert re.search(rf"^{letter}\.\s", checks, re.M), (
            f"existing check {letter} must not be renumbered or removed"
        )


def test_adversary_findings_format_admits_new_checks(tree_adversary: str) -> None:
    """Behavior 3 and 4 — a finding must be able to name check F or G."""
    assert re.search(r"check\s+A-G|checks?\s+A[–-]G", tree_adversary), (
        "the findings format still says 'check A-E'; a finding that cannot name F or "
        "G is a check the adversary cannot report"
    )


def test_single_ticket_adversary_covers_circularity(solo_adversary: str) -> None:
    """Behavior 4 — the single-ticket adversary gains G, and is explicit about F."""
    checks = _round1_checks(solo_adversary)
    assert checks, "single-ticket-adversary.md round-1 template has no Checks: block"
    assert re.search(r"^G\.\s", checks, re.M), (
        "check G (circular rationale) applies to the single-ticket path unchanged"
    )
    # NOT `"F" in solo_adversary` — the bare letter already appears in FACE-VALUE and
    # FIDELITY, so that assertion passes against unimplemented code (attack vector 5).
    assert re.search(r"check\s+F\b", solo_adversary, re.I), (
        "the file must name check F explicitly, not merely contain the letter F"
    )
    assert re.search(r"no PRD|without a PRD|no-op|not applicable", solo_adversary, re.I), (
        "the file must state explicitly whether check F applies here — the "
        "single-ticket path has no PRD, so F is either scoped to a declared spec or "
        "a documented no-op. Silent omission is the defect this ticket exists to stop."
    )


def test_ticket_standard_requires_out_of_root_entrypoint_test(
    ticket_standard: str,
) -> None:
    """Behavior 5 — at least one test runs the entrypoint from outside the repo root."""
    section = _section(ticket_standard, "5. Test expectations", level="### ")
    assert section, "ticket-standard.md has no '### 5. Test expectations' section"
    body = section.lower()
    assert "entrypoint" in body, (
        "the Test expectations section must require exercising the declared entrypoint"
    )
    assert "relative" in body, (
        "the requirement must name a relative path argument — the file_backup crash "
        "was a relative --mount resolved against the wrong base"
    )
    assert "not the project root" in body or "outside the project root" in body, (
        "the requirement must name a working directory that is not the project root"
    )

    template_start = ticket_standard.find("## Copyable template")
    assert template_start != -1, "ticket-standard.md has no copyable template"
    template = ticket_standard[template_start:]
    assert "entrypoint" in template.lower(), (
        "the copyable template must carry the entrypoint requirement too — authors "
        "copy the template, not the prose"
    )


def test_design_spec_key_documented_consistently() -> None:
    """Behavior 1 — `[design] spec` is documented in all three places, no drift."""
    conf_text = EXAMPLE_CONF.read_text()
    tomllib.loads(conf_text)  # the example must stay parseable

    assert "[design]" in conf_text, (
        ".project-conf.toml.example must carry a commented [design] table"
    )
    # NOT a bare `spec` substring — CONFIG.md already contains "full spec:" and
    # "specification", so a loose match passes against unimplemented code.
    assert re.search(r"^\s*#?\s*spec\s*=", conf_text, re.M), (
        ".project-conf.toml.example must show `spec = ...` as a key, commented or not"
    )
    for path in (CONFIG_MD, CONF_OPTIONS):
        text = path.read_text()
        assert "[design]" in text, f"{path.name} does not document the [design] table"
        assert re.search(r"`spec`|spec\s*=", text), (
            f"{path.name} must document `spec` as a config key, not merely use the "
            "word 'spec' in prose"
        )


def test_design_spec_key_accepts_string_or_array() -> None:
    """Behavior 1 boundary — `[design] spec` takes one path or several.

    Scoped to the `[design]` section deliberately. Searching the whole of CONFIG.md
    passes vacuously — the word "array" already appears elsewhere in it.
    """
    text = CONFIG_MD.read_text()
    design = _section(text, "`[design]`", level="### ") or _section(
        text, "[design]", level="### "
    )
    assert design, (
        "CONFIG.md has no `### [design]` section — the spec key must be documented "
        "in its own table like every other config block"
    )
    assert re.search(r"array|list of strings|string or", design, re.I), (
        "`[design] spec` must document that it accepts a string OR an array of "
        "strings — a run may cite more than one spec document, and the array form "
        "is the case an implementer is most likely to skip"
    )


def test_circularity_check_fires_only_on_sole_support(tree_adversary: str) -> None:
    """Behavior 4 error path — G must not ban all cross-decision citation.

    Scoped to check G's own text. Searching the whole file passes vacuously — the
    word "only" already appears in the findings instructions.
    """
    checks = _round1_checks(tree_adversary)
    match = re.search(r"^G\.\s(.*?)(?=^[A-Z]\.\s|\Z)", checks, re.M | re.S)
    assert match, "check G is not defined in the round-1 check list"
    g_text = match.group(1)
    assert re.search(r"\bsole\b|\bonly\b", g_text, re.I), (
        "check G must fire only when another decision is a decision's SOLE support. "
        "A rationale citing both spec text and a sibling decision is legitimate; an "
        "implementation that bans all cross-references is over-strict and would "
        "reject sound PRDs"
    )


def test_spec_hash_mismatch_is_itself_a_finding(tree_adversary: str) -> None:
    """Behavior 3 error path — spec drift after the PRD was written is reportable."""
    assert re.search(r"sha256", tree_adversary, re.I), (
        "check F must compare the declared spec's sha256 against the PRD header"
    )
    assert re.search(r"mismatch|changed|drift", tree_adversary, re.I), (
        "a sha256 mismatch must be a finding in its own right — it means the spec "
        "changed after the PRD was written, which silently invalidates every "
        "SPEC-classified decision"
    )
