"""
Phase 0 red tests for BILL-371 — Step 2f's stub-backed BASE worktree.

Transcribed from the ticket's Test expectations
(https://github.com/iansmith/slopstop/issues/371).

Every assertion here is structural, not prose: a JSON example parsed and checked
for a set property, one identifier agreed across three documents, and the ref a
shell command resolves content at. That is the narrow exception the 2026-08-01
prose-only policy (5652d54) keeps — invariants a human cannot check by reading a
single file. No assertion below pins an English sentence.

The ticket's first test expectation asked for "a fixture gates.json containing
both". There is no fixture to write against: nothing here executes. Implemented
instead against the worked example in `gates-json.md` itself, which is the thing
agents transcribe — so the doc's own example is what gets validated. Recorded in
the PR rather than silently swapped.

Test command:
    python3 -m pytest tests/test_bill371_behaviors.py -v
"""

import json
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent
MECHANICS = REPO_ROOT / "skills" / "plan" / "references" / "plan-phase0-mechanics.md"
GATES_JSON = REPO_ROOT / "skills" / "start" / "references" / "gates-json.md"
PR_SLOP = REPO_ROOT / "skills" / "pr" / "references" / "pr-slop-detection.md"

#: The one name for the recorded stub list. Every consumer must spell it this way.
STUBS_KEY = "meta.stubs"


def _text(path):
    if not path.is_file():
        pytest.fail(f"{path} does not exist")
    return path.read_text()


def _fenced_blocks(text, lang):
    """Every ```<lang> block body in `text`, in document order."""
    return re.findall(rf"^```{lang}\n(.*?)^```", text, re.MULTILINE | re.DOTALL)


def _phase0_baseline_example():
    """The worked Phase 0 baseline `meta` block from gates-json.md, parsed.

    Located by content — the only json block declaring all three baseline keys —
    rather than by position, so inserting an example above it does not silently
    re-point this test at the wrong block.
    """
    for body in _fenced_blocks(_text(GATES_JSON), "json"):
        if all(k in body for k in ('"red_sha"', '"frozen"', '"stubs"')):
            try:
                return json.loads(body)
            except json.JSONDecodeError as exc:
                pytest.fail(f"the Phase 0 baseline example in gates-json.md is not valid JSON: {exc}")
    pytest.fail(
        "gates-json.md carries no worked json example declaring red_sha, frozen and "
        "stubs together. Agents transcribe the example, so an unexemplified key is a "
        "key that gets spelled differently by each writer."
    )


class TestRecordedStubList:
    """`:plan` Step 0e records what it staged; nothing downstream re-derives it."""

    def test_example_declares_all_three_baseline_keys(self):
        meta = _phase0_baseline_example().get("meta", {})
        for key in ("red_sha", "frozen", "stubs"):
            assert key in meta, f"the baseline example omits meta.{key}"

    def test_frozen_and_stubs_are_disjoint_in_the_example(self):
        meta = _phase0_baseline_example()["meta"]
        frozen = set(meta["frozen"]["value"])
        stubs = set(meta["stubs"]["value"])
        assert frozen and stubs, (
            "the example must show both lists non-empty — an example with an empty "
            "list demonstrates nothing about the relationship between them"
        )
        assert not (frozen & stubs), (
            f"meta.frozen and meta.stubs overlap in the example: {sorted(frozen & stubs)}. "
            "They are disjoint by construction — frozen is test files, stubs is the "
            "production surface staged alongside them — and a shared path would make a "
            "stub frozen, which is exactly what recording the two separately prevents."
        )

    def test_baseline_keys_carry_the_red_commit_sha_not_head(self):
        meta = _phase0_baseline_example()["meta"]
        red = meta["red_sha"]["value"]
        for key in ("frozen", "stubs"):
            assert meta[key]["sha"] == red, (
                f"meta.{key}'s sha must be the red-test commit, matching meta.red_sha's "
                "value — these three describe one fixed historical commit and are not "
                "sha-gated against current HEAD, or they would go stale on the next push"
            )

    def test_step_0e_records_the_stub_list(self):
        assert STUBS_KEY in _text(MECHANICS), (
            "Step 0e stages the stubs and therefore knows them. Recording the list is "
            "the same fix 5652d54 applied to red_sha and frozen; the alternative — "
            "deriving 'the non-test files in the Phase 0 commit' downstream — is the "
            "unanchored re-derivation that change removed."
        )

    def test_every_consumer_spells_the_key_identically(self):
        for path in (MECHANICS, GATES_JSON, PR_SLOP):
            assert STUBS_KEY in _text(path), (
                f"{path.name} does not name {STUBS_KEY}. A writer and a reader that "
                "disagree on this key produce no error: the reader finds nothing, "
                "falls back, and the gate silently degrades to today's behavior forever."
            )


class TestStep2fResolvesStubsAtTheRedCommit:
    """The one detail that inverts the gate if it is wrong."""

    def _stub_copy_block(self):
        """The shell block in Step 2f that builds the BASE worktree."""
        for body in _fenced_blocks(_text(PR_SLOP), "bash"):
            if "git worktree add" in body and "stub" in body.lower():
                return body
        pytest.fail(
            "Step 2f has no BASE-worktree block that copies stubs. Without them a "
            "stub-backed test cannot be collected at BASE and the gate returns "
            "inconclusive — the whole defect this ticket fixes."
        )

    def test_stub_content_comes_from_the_red_commit(self):
        block = self._stub_copy_block()
        stub_lines = [l for l in block.splitlines() if "git show" in l and "STUB" in l.upper()]
        assert stub_lines, "no `git show` line resolves the stub files"
        for line in stub_lines:
            assert "HEAD:" not in line, (
                "stubs must be copied at their Phase 0 commit content, never at HEAD. "
                "At HEAD the stub IS the finished implementation, so every changed test "
                "would pass against it and the gate would report the entire branch as "
                "vacuous. The red-commit content is the non-satisfying sentinel Step 0d "
                f"requires.\n  offending line: {line.strip()}"
            )

    def test_changed_tests_still_come_from_head(self):
        block = self._stub_copy_block()
        assert re.search(r'git show\s+HEAD:', block), (
            "the changed test files are still copied at HEAD — new tests on old code "
            "is what the gate measures; only the stubs are resolved at the red commit"
        )


class TestFallback:
    """Step 2f's unskippability is already guarded by test_bill354's
    `test_2d_2f_still_unskippable` and test_bill278. Not restated here — one
    definition per value (universal §5), and a second copy is a second thing to
    update when the wording moves."""

    def test_absent_stub_list_degrades_to_todays_behavior(self):
        t = _text(PR_SLOP)
        i = t.find(STUBS_KEY)
        assert i != -1
        window = t[i:i + 4000]
        assert re.search(r"\bfall(s|ing)? back\b|\bfallback\b", window), (
            "a gates.json predating this key — or one from a ticket that needed no "
            "stub — must still run Step 2f, copying tests only. Without a stated "
            "fallback a reader has to invent one, and 'skip the gate' is the cheapest "
            "thing to invent."
        )

