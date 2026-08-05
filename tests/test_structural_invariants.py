"""Structural invariants — properties a careful reader cannot check by eye.

This file replaces roughly 11,000 lines of doc-assertion tests deleted in the
2026-08-01 prune. Those tests asserted that particular English sentences appeared
in particular markdown files. They pinned *wording*, not behavior: they could not
fail for a reason review would miss, and they turned every legitimate reword into
a red suite — which is pure overhead on a repo whose product is mostly prose.

The policy that governs what belongs here is `plan-phase0-mechanics.md`
§ "When Phase 0 does not apply: prose-only changes". Its exception is narrow and
this file is the whole of it:

    structural invariants that a human cannot check by reading — a mirrored file
    matching its reference byte-for-byte, a derivation still present in the
    script that implements a gate, a file existing where a manifest says it does.

Before adding a test here, ask whether it would fail for a reason a careful
reviewer reading the diff would have missed. If the answer is no, it does not
belong — write it as prose in the skill and let review catch it.

Companion structural suites, kept for the same reason:
  - test_skill_structure.py           spine line limits, references/ dirs, manifests
  - test_fleet_sync_residual_scan.py  the marker scan in migrate-universal-block.py
"""

import re
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent
SKILLS_DIR = REPO_ROOT / "skills"
CLAUDE_MD = REPO_ROOT / "CLAUDE.md"
UNIVERSAL_MD = REPO_ROOT / "CLAUDE-universal.md"

IMPORT_LINE = "@CLAUDE-universal.md"

# The prose-only exemption marker. `:plan` writes it; `:pr` Step 2d matches it.
# Two files must agree on this literal string or the tamper gate silently stops
# exempting prose-only changes — a drift no reader would notice.
PHASE0_MARKER = "**Phase 0:** none"
PHASE0_WRITER = SKILLS_DIR / "plan" / "references" / "plan-phase0-mechanics.md"
PHASE0_READERS = (
    SKILLS_DIR / "pr" / "SKILL.md",
    SKILLS_DIR / "pr" / "references" / "pr-slop-detection.md",
)


def _all_skill_markdown():
    return sorted(SKILLS_DIR.rglob("*.md"))


# --------------------------------------------------------------------------
# The mirrored universal rules
# --------------------------------------------------------------------------


class TestUniversalRulesMirror:
    """`CLAUDE-universal.md` is the reference copy, mirrored byte-identically
    into every other project (`CLAUDE.md` §10). Nothing about a diff to it looks
    wrong on the page — the failure mode is silent divergence across six repos.
    """

    def test_universal_rules_file_exists_and_is_nonempty(self):
        assert UNIVERSAL_MD.is_file(), (
            f"{UNIVERSAL_MD.name} must exist at the repo root — it is the "
            "reference copy mirrored into every other project"
        )
        assert UNIVERSAL_MD.read_text().strip(), f"{UNIVERSAL_MD.name} is empty"

    def test_claude_md_imports_it_exactly_once_with_no_markers(self):
        lines = CLAUDE_MD.read_text().split("\n")
        n = sum(1 for line in lines if line.strip() == IMPORT_LINE)
        assert n == 1, (
            f"CLAUDE.md must contain exactly one whole-line '{IMPORT_LINE}' "
            f"import (found {n}). A backticked or indented mention does not count."
        )
        # The pre-2026-08-01 design spliced the rules into CLAUDE.md between
        # BEGIN/END markers whose names appeared in the prose that described
        # them, so every loose extraction terminated at the wrong place —
        # silently. The markers must not come back.
        #
        # Matched as a WHOLE LINE holding the actual HTML comment, never as a
        # substring: CLAUDE.md's own §10 discusses these marker names in prose,
        # so a substring test fires on the documentation of the trap rather than
        # the trap. That is the identical mistake the scar describes, and it is
        # why the rule there is "anchor the pattern to whole lines".
        marker_re = re.compile(r"^\s*<!--\s*(BEGIN|END)\s+UNIVERSAL\s+SECTION\s*-->\s*$")
        offenders = [line for line in lines if marker_re.match(line)]
        assert not offenders, (
            f"CLAUDE.md still carries a splice marker: {offenders!r}. The "
            "whole-file design exists to remove that failure mode; see "
            "CLAUDE.md's 'Why a whole file, and not a marked region'."
        )

    def test_universal_rules_unchanged_from_merge_base(self):
        """Changing the reference is legitimate — but only deliberately, and it
        obliges a propagation run. A silent edit riding along in an unrelated
        branch is the failure this catches.
        """
        for ref in ("origin/master", "master"):
            mb = subprocess.run(
                ["git", "merge-base", "HEAD", ref],
                cwd=REPO_ROOT, capture_output=True, text=True,
            )
            if mb.returncode == 0 and mb.stdout.strip():
                break
        if not (mb.returncode == 0 and mb.stdout.strip()):
            pytest.skip("no merge-base with master — shallow clone or detached tree")

        base = subprocess.run(
            ["git", "show", f"{mb.stdout.strip()}:CLAUDE-universal.md"],
            cwd=REPO_ROOT, capture_output=True, text=True,
        )
        if base.returncode != 0:
            pytest.skip("CLAUDE-universal.md absent at merge-base")

        assert base.stdout == UNIVERSAL_MD.read_text(), (
            "CLAUDE-universal.md differs from the merge-base. This is the "
            "reference copy for six repos. If the change is intentional, run:\n"
            "  python3 tools/fleet-sync/migrate-universal-block.py --apply\n"
            "  python3 tools/fleet-sync/migrate-universal-block.py --verify\n"
            "and say so explicitly — otherwise revert it."
        )


# --------------------------------------------------------------------------
# Cross-file string contracts
# --------------------------------------------------------------------------


class TestPhase0MarkerContract:
    """`:plan` writes a literal marker into task_plan.md; `:pr` Step 2d matches
    it to exempt prose-only changes from the red-test tamper gate. If the two
    sides drift, the gate stops exempting and every docs-only PR hard-stops —
    and nothing in either file looks wrong on its own.
    """

