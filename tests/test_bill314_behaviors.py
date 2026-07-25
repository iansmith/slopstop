"""
Phase 0 red tests for BILL-314 — :merge adopts an already-merged PR.

Transcribed from the ticket's Test expectations
(https://github.com/iansmith/slopstop/issues/314). These are structural
assertions over skill text, matching the convention in test_skill_structure.py:
the "behavior" of a skill IS its documented procedure.

These tests FAIL on current code (the pre-merge gate refuses any state != OPEN
with no adopt path) and turn GREEN once the fix is applied.

Test command:
    python3 -m pytest tests/test_bill314_behaviors.py -v
"""

import re
from pathlib import Path

import pytest

from conftest import ref

REPO_ROOT = Path(__file__).parent.parent
MERGE_SKILL = REPO_ROOT / "skills" / "merge" / "SKILL.md"


@pytest.fixture(scope="module")
def merge_text():
    """The :merge spine plus its references, concatenated.

    Widened by BILL-324, which cut the spine from 346 lines to ~126 by moving Step 1's
    backend detection, PR resolution and gate lists into
    `references/merge-pr-resolution.md`, and Step 4's mechanics into
    `references/merge-execute.md`.

    BILL-314's invariants are about the *procedure* — that the gate names CLOSED
    explicitly rather than blanket-refusing non-OPEN, and that Step 4 is skipped in
    adopt mode. Those live wherever the procedure lives, and after BILL-324 that is
    the reference files.

    **One test must NOT use this fixture:** the Step 1c `--json` field-list check.
    That assertion is a claim about *which command* the field list belongs to, and
    concatenation destroys it — `re.search` takes the first `pr view` match, which in
    sorted-glob order is `merge-execute.md`'s Step 4 read-back
    (`state,mergedAt,mergedBy,mergeCommit`), not Step 1c's list. Proven by mutation:
    with the widened fixture, deleting `mergeCommit` from Step 1c left all six tests
    passing, so the exact BILL-314 bug (adopt mode with no `$MERGE_COMMIT`, because
    Step 4 never runs to produce it) was unguarded. That test now reads
    merge-pr-resolution.md directly.

    The spine's own share of the contract — that adopt mode exists, and that CLOSED
    refuses while MERGED adopts — is separately pinned by
    tests/test_bill324_behaviors.py, so widening this fixture does not leave the spine
    unguarded.
    """
    parts = [MERGE_SKILL.read_text()]
    parts += [p.read_text() for p in sorted((MERGE_SKILL.parent / "references").glob("*.md"))]
    return "\n".join(parts)


def test_step1c_cli_fetch_includes_merge_commit():
    """Adopt mode needs the merge SHA from Step 1c, since Step 4 never runs to
    produce it. The MCP path returns it already; the CLI --json list must ask.

    Deliberately does NOT take the `merge_text` fixture — see its docstring. This is a
    claim about Step 1c's command specifically, so it reads the file that owns Step 1c
    and anchors on `headRefName`, a field only 1c's list requests. Against the
    concatenated fixture it silently matched Step 4's read-back instead and passed
    with `mergeCommit` deleted from 1c.
    """
    text = ref("merge", "merge-pr-resolution.md")
    m = re.search(r"pr view \$PR --json ([^\s`]*headRefName[^\s`]*)", text)
    assert m, (
        "Could not find Step 1c's `gh pr view --json` field list in "
        "merge-pr-resolution.md (matched on headRefName to distinguish it from "
        "Step 4's read-back)."
    )
    fields = {f.strip() for f in m.group(1).split(",")}
    assert "mergeCommit" in fields, (
        "Step 1c's --json field list must include `mergeCommit` so adopt mode can "
        f"capture $MERGE_COMMIT without a second round-trip. Found: {sorted(fields)}"
    )


def test_gate_distinguishes_merged_from_closed(merge_text):
    """A MERGED PR is adoptable; a CLOSED-unmerged PR is abandoned work and must
    still refuse. The old gate (`state != OPEN`) conflated them."""
    assert 'state == "CLOSED"' in merge_text or "state == 'CLOSED'" in merge_text, (
        "The pre-merge gate must name the CLOSED state explicitly so an abandoned "
        "PR still refuses while a MERGED one is adopted."
    )
    assert not re.search(r"`state != OPEN`\s*—\s*`\"PR #\$PR is in state", merge_text), (
        "The old blanket `state != OPEN` refusal must be gone — it is what makes an "
        "already-merged PR unrecoverable."
    )


def test_adopt_mode_is_documented(merge_text):
    """Adopt mode must be a named, findable concept, keyed on MERGED."""
    assert "adopt" in merge_text.lower(), (
        "skills/merge/SKILL.md must document adopt mode by name."
    )
    idx = merge_text.lower().find("adopt")
    window = merge_text[max(0, idx - 500):idx + 1500]
    assert "MERGED" in window, (
        "Adopt mode must be keyed on the PR's MERGED state, stated near where it is "
        "introduced."
    )


def test_step4_is_skipped_in_adopt_mode(merge_text):
    """Step 4 performs the merge; adopting a merged PR must not re-merge it."""
    idx = merge_text.find("## Step 4 — Merge the PR")
    assert idx != -1, "Could not locate Step 4."
    step4 = merge_text[idx:idx + 1200]
    assert "adopt" in step4.lower() and "skip" in step4.lower(), (
        "Step 4 must state that it is skipped in adopt mode — otherwise the skill "
        "would attempt to merge an already-merged PR."
    )


def test_confirm_states_no_merge_performed(merge_text):
    """The operator must never be left thinking :merge merged something it didn't."""
    idx = merge_text.find("## Step 3 — Confirm")
    assert idx != -1, "Could not locate Step 3."
    step3 = merge_text[idx:idx + 2000]
    assert "adopt" in step3.lower(), (
        "Step 3's confirmation must surface adopt mode so the plan shown to the "
        "operator makes clear no merge will be performed."
    )


def test_rules_no_longer_claim_no_recovery(merge_text):
    """BILL-312 documented that re-running :merge cannot recover an already-merged
    PR. BILL-314 makes that false; the note must be corrected, not left stale."""
    assert "no recovery path through" not in merge_text.lower(), (
        "The BILL-312 Rules note claiming there is no recovery path through :merge "
        "is now false — adopt mode IS the recovery path. Update that note."
    )


# NOTE — the ticket's observable behavior 6 (branch cleanup tolerates an
# already-deleted remote/local branch) is ALREADY satisfied on current code:
# merge-cleanup.md step 3 reads "the branch exists only remotely or was already
# cleaned up. Skip — nothing to delete locally." A test here would assert a
# pre-existing invariant, not new behavior, so it is deliberately absent rather
# than frozen green into the Phase 0 baseline.
