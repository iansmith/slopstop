"""
Phase 0 red tests for BILL-316 — meaningful gate names.

Transcribed from the ticket's Test expectations
(https://github.com/iansmith/slopstop/issues/316). Structural assertions over
skill and design text, matching the test_skill_structure.py convention.

The bare numbered labels G1/G2/G4 tell a new user nothing; G-final was already
named descriptively, so the numbers were the outlier. `Gate 0` is a mechanical
tamper check, not a human gate, and is renamed so the `G-` prefix means "a human
answers this".

CHANGELOG.md is deliberately excluded from every assertion — its entries describe
past releases in which the gates genuinely were called G1/G2.

These tests FAIL on current code and turn GREEN once the rename is applied.

Test command:
    python3 -m pytest tests/test_bill316_behaviors.py -v
"""

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent
SEARCH_ROOTS = [REPO_ROOT / "skills", REPO_ROOT / "design"]
TOP_LEVEL_DOCS = [REPO_ROOT / "CONFIG.md"]
PROCESS_DOC = REPO_ROOT / "design" / "slopstop-process.md"

OLD_GATE_TOKENS = ["G1", "G2", "G4"]
# All four human gates, post-rename. G-final is already correct on current code.
NEW_GATE_NAMES = ["G-design", "G-tickets", "G-failure", "G-final"]
# Only the three this ticket introduces. G-final is deliberately excluded here: it
# already passes, and a green test must not enter the frozen Phase 0 baseline. Its
# survival is still guarded — both the process-doc and skill-description tests below
# assert all four, and both are red until the rename lands.
RENAMED_GATES = ["G-design", "G-tickets", "G-failure"]


def _searchable_files():
    files = []
    for root in SEARCH_ROOTS:
        files.extend(p for p in root.rglob("*.md") if p.is_file())
    files.extend(p for p in TOP_LEVEL_DOCS if p.is_file())
    return files


def _hits(token: str) -> list[str]:
    """Files containing `token` as a standalone word, with line numbers."""
    pattern = re.compile(rf"\b{re.escape(token)}\b")
    out = []
    for f in _searchable_files():
        for n, line in enumerate(f.read_text().splitlines(), 1):
            if pattern.search(line):
                out.append(f"{f.relative_to(REPO_ROOT)}:{n}")
    return out


@pytest.mark.parametrize("token", OLD_GATE_TOKENS)
def test_old_numbered_gate_label_is_gone(token):
    """No bare G1/G2/G4 survives in shipped skill or design text."""
    hits = _hits(token)
    assert not hits, (
        f"Bare gate label `{token}` still present in {len(hits)} place(s) — rename it "
        f"per the BILL-316 mapping (G1→G-design, G2→G-tickets, G4→G-failure). "
        f"First few: {hits[:5]}"
    )


@pytest.mark.parametrize("name", RENAMED_GATES)
def test_new_gate_name_is_used(name):
    """Each newly-renamed gate is present under its descriptive name."""
    assert _hits(name), f"Gate name `{name}` does not appear anywhere in skills/ or design/."


def test_gate_zero_is_renamed():
    """`Gate 0` is a mechanical tamper check, not a human gate — the `G-`/gate-number
    vocabulary should be reserved for gates a human actually answers."""
    hits = [h for h in _hits("Gate 0")]
    assert not hits, (
        f"`Gate 0` still present in {len(hits)} place(s). It is a mechanical red-test "
        f"tamper check that prompts nobody; rename it so gate vocabulary means "
        f"'a human answers this'. First few: {hits[:5]}"
    )


def test_process_doc_gate_table_lists_new_names():
    """The canonical gate table is where a new user learns the vocabulary."""
    text = PROCESS_DOC.read_text()
    for name in NEW_GATE_NAMES:
        assert name in text, (
            f"design/slopstop-process.md must name `{name}` in its gate table."
        )


def test_skill_descriptions_use_new_names():
    """`description:` frontmatter is what shows in the skill listing — a user sees
    these before reading anything else."""
    for skill, expected in [("design", "G-design"), ("run", "G-final")]:
        text = (REPO_ROOT / "skills" / skill / "SKILL.md").read_text()
        frontmatter = text.split("---")[1] if text.startswith("---") else text[:800]
        assert expected in frontmatter, (
            f"skills/{skill}/SKILL.md's description: frontmatter should reference "
            f"`{expected}` — it is the first thing a user reads about the skill."
        )
