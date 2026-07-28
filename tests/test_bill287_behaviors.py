"""
Phase 0 red tests for BILL-287 — mechanically confirm the Phase 0 baseline was
actually RED, not merely that the frozen tests are unchanged.

https://github.com/iansmith/slopstop/issues/287

The tamper check in `run-verification.md` (Gate 0) already asks "did the frozen
tests change since RED?" — but nothing asks "were they ever red in the first
place?" An agent can write a test that already passes against unimplemented
code (SOP-110's shape: tests shipped in the same commit as the code, never
shown failing), stage it in a commit titled "Phase 0: red tests", and every
downstream gate reads it as a clean baseline. `:plan` Step 0e's rule ("only
tests observed FAILING at 0d may enter this commit") is prose the agent itself
enforces — nothing external re-checks it.

This gate re-runs the frozen tests at `$RED`, in a scratch worktree, and
classifies the result. Two outcomes are FAIL, one is PASS:

- Exit 0 at `$RED` -> the baseline was never red -> FAIL.
- Non-zero exit WITHOUT an assertion failure (a collection/import/setup error)
  -> the baseline is unverifiable, not proven red -> FAIL. This is the
  refinement recorded on the ticket itself (comment, 2026-07-28): a bare
  "assert non-zero exit" would let a test that errors on an import missing at
  $RED (a module the implementation later adds) launder through as "red" when
  nothing was ever asserted. Same distinction BILL-340 drew for the CC gate —
  a check that could not run must not read as a check that passed.
- Non-zero exit WITH an assertion failure -> genuinely red -> PASS.

Verified empirically against pytest 9.0.3 (`python3 -m pytest --version`) before
these tests were written: exit 1 for an assertion failure, exit 2 for a
collection error (ImportError or SyntaxError before any test runs), exit 0 for
a clean pass. These are the concrete signal the doc's classification rule
cites for this repo's own suite; other frameworks are classified by the same
principle (an assertion actually fired) stated generically, since this file
is read by an LLM agent, not executed as a literal parser.

Test command:
    python3 -m pytest tests/test_bill287_behaviors.py -v
"""

import re
import subprocess
import tempfile
from pathlib import Path

import pytest

from conftest import git, init_git_repo

REPO_ROOT = Path(__file__).parent.parent
RUN_VERIFICATION = REPO_ROOT / "skills" / "run" / "references" / "run-verification.md"


@pytest.fixture(scope="module")
def doc() -> str:
    return RUN_VERIFICATION.read_text()


@pytest.fixture
def redness_section(doc: str) -> str:
    """The redness-confirmation section's own text, bounded by the next `## `
    heading rather than a fixed character count.

    A fixed-size window (an earlier version used 3000 chars) is a silent trap:
    the section is 3507 chars long, so a window that size cut off the real PASS
    bullet entirely, and the test that checked for it passed anyway — satisfied
    by an unrelated "passed" fifteen lines earlier ("Run only if the tamper
    check passed"). Bounding by structure instead of a guessed size removes the
    whole failure class, not just this one instance of it.
    """
    start = doc.lower().find("redness")
    assert start != -1, "no 'redness' section found in run-verification.md"
    next_heading = doc.find("\n## ", start)
    end = next_heading if next_heading != -1 else len(doc)
    return doc[start:end]


# --- 1. the gate exists, in the right place -------------------------------------


def test_redness_gate_exists(doc: str) -> None:
    assert re.search(r"redness|baseline was.{0,20}red|confirm.{0,20}RED", doc, re.IGNORECASE), (
        "run-verification.md must add a mechanical check confirming the Phase 0 "
        "baseline was actually red, not merely unchanged since RED"
    )


def test_redness_gate_runs_before_the_subagents(doc: str) -> None:
    """Same placement discipline as the existing tamper check: a FAIL here must
    end verification before any subagent is spawned — a subagent is not free.
    """
    tamper_idx = doc.find("## Tamper check")
    subagents_idx = doc.find("## The two subagents")
    redness_idx = doc.lower().find("redness")
    assert tamper_idx != -1 and subagents_idx != -1, "expected section headings not found"
    assert tamper_idx < redness_idx < subagents_idx, (
        "the redness confirmation must sit between the tamper check and the two "
        "subagents — before the subagents matters as much as before is where the "
        "tamper check already runs, for the same cost reason"
    )


def test_redness_gate_uses_a_scratch_worktree_at_red(redness_section: str) -> None:
    assert re.search(r"git worktree add", redness_section), (
        "the gate must check out $RED in a scratch worktree — the ticket's own "
        "scope names this explicitly"
    )
    assert "$RED" in redness_section, "the gate must revert to $RED, the frozen baseline"


# --- 2. classification: exit code alone is not enough ----------------------------


def test_gate_does_not_accept_bare_nonzero_exit_as_proof_of_red(redness_section: str) -> None:
    """The ticket's own scope text says 'assert non-zero exit'. A comment on the
    ticket (2026-07-28) records why that is insufficient and must not survive
    into the implementation: a collection/import error at $RED is non-zero and
    proves nothing was ever asserted.
    """
    assert re.search(r"assertion", redness_section, re.IGNORECASE), (
        "the gate must require an assertion failure specifically, not just a "
        "non-zero exit code"
    )
    assert re.search(r"collection|import.{0,10}error|setup error", redness_section, re.IGNORECASE), (
        "the gate must name collection/import/setup errors as a distinct, "
        "non-red outcome — the case a bare exit-code check would launder through"
    )


def test_three_outcomes_stated(redness_section: str) -> None:
    # Structural: three distinct dispositions, not merely three sentences that
    # happen to mention related words.
    assert re.search(r"never-red|passed cleanly|exit(ed)? 0|exit 0", redness_section, re.IGNORECASE), (
        "the gate must state the exit-0-at-RED outcome (baseline never red)"
    )
    assert re.search(r"unverifiable|cannot confirm|not proven red", redness_section, re.IGNORECASE), (
        "the gate must state the collection/setup-error outcome as its own "
        "disposition (unverifiable), not silently folded into either PASS or the "
        "never-red FAIL"
    )
    assert re.search(r"genuinely-red|genuinely red|confirmed red", redness_section, re.IGNORECASE), (
        "the gate must state what a genuine assertion failure at RED means: PASS"
    )


def test_both_bad_outcomes_are_fail_not_a_shrug(redness_section: str) -> None:
    """Consistent with the tamper check's own stated doctrine two sections
    above ('a missing baseline is the strongest failure, not the absence of
    one') — a baseline this gate cannot verify must not read as a clean pass.
    """
    fail_mentions = len(re.findall(r"\bFAIL\b", redness_section))
    assert fail_mentions >= 2, (
        "both the never-red outcome and the unverifiable outcome must be stated "
        f"as FAIL — found {fail_mentions} FAIL mention(s) in the gate's section"
    )


# --- 3. scope and caching ---------------------------------------------------------


def test_gate_scopes_to_frozen_files_not_the_whole_suite(redness_section: str) -> None:
    assert "$FROZEN" in redness_section, (
        "the gate must reuse $FROZEN (already computed by the tamper check "
        "immediately above) rather than re-deriving the frozen file set or "
        "running the whole suite — the ticket's own scope names this cost concern"
    )


def test_gate_resolves_the_test_command_the_same_way_plan_does(redness_section: str) -> None:
    assert re.search(r"Test command|task_plan\.md", redness_section), (
        "the gate must resolve the test command the same way :plan Step 0a does "
        "(task_plan.md's Test command line, else auto-detect) — a second, "
        "divergent resolution mechanism is how these two silently drift"
    )


def test_gate_is_cached_by_red_sha(redness_section: str) -> None:
    assert re.search(r"cach(e|ed|ing)", redness_section, re.IGNORECASE), (
        "the gate must cache its result by $RED SHA — the ticket's own scope "
        "names the cost of a full checkout + test run per verification, and a "
        "relaunch on the same ticket must not re-pay it"
    )
    assert "scratch/runs/$RUN_ID" in redness_section, (
        "the cache must live under the run's own scratch directory, matching "
        "the existing scratch/runs/$RUN_ID/verdicts/ convention used two "
        "sections below for subagent findings"
    )


def test_caching_actually_gates_the_expensive_work(redness_section: str) -> None:
    """The cache check, the worktree checkout, and the test run must be ONE
    connected script — not three independent fenced snippets. A first version
    of this doc had exactly that shape: the `if [ -f "$CACHE" ]` block had no
    `else`, so the worktree checkout and test run below it ran unconditionally
    regardless of the cache, making the caching decorative rather than
    load-bearing. Caught by an efficiency review, not by any test above (they
    only checked that the WORDS "cache" and the cache path appear somewhere in
    the section, not that the cache actually short-circuits anything).
    """
    assert re.search(r"else\b", redness_section), (
        "the cache-hit branch must have a matching else that skips the worktree "
        "checkout and test run — three disconnected fenced snippets (an if with "
        "no else, then an unconditional checkout, then an unconditional run) "
        "look like caching but never skip the expensive work"
    )
    cache_if = redness_section.find("if [ -f \"$CACHE\" ]")
    worktree_add = redness_section.find("git worktree add")
    else_pos = redness_section.find("else", cache_if)
    assert cache_if != -1 and worktree_add != -1 and else_pos != -1, (
        "expected the cache check and the worktree checkout to both be present"
    )
    assert cache_if < else_pos < worktree_add, (
        "the worktree checkout must textually follow the else — placing it "
        "before the else (or in a separate fenced block with no else at all) "
        "is exactly the bug this test guards against"
    )


# --- 4. end-to-end, against the real tool -----------------------------------------


def test_pytest_exit_codes_match_the_documented_classification() -> None:
    """Pins the empirical premise the doc's classification rule depends on.
    If pytest's exit codes ever change shape, this is what will say so.
    """
    with tempfile.TemporaryDirectory() as raw_d:
        d = Path(raw_d)
        (d / "test_fail.py").write_text("def test_x():\n    assert 1 == 2\n")
        r = subprocess.run(["python3", "-m", "pytest", "test_fail.py", "-q"], cwd=d, capture_output=True, text=True)
        assert r.returncode == 1, f"expected exit 1 for an assertion failure, got {r.returncode}"
        assert "AssertionError" in r.stdout or "assert" in r.stdout

        (d / "test_broken_import.py").write_text("import nonexistent_module_xyz\ndef test_y():\n    assert True\n")
        r = subprocess.run(["python3", "-m", "pytest", "test_broken_import.py", "-q"], cwd=d, capture_output=True, text=True)
        assert r.returncode == 2, f"expected exit 2 for a collection error, got {r.returncode}"
        assert "AssertionError" not in r.stdout, "a collection error must not read as an assertion failure"

        (d / "test_pass.py").write_text("def test_z():\n    assert True\n")
        r = subprocess.run(["python3", "-m", "pytest", "test_pass.py", "-q"], cwd=d, capture_output=True, text=True)
        assert r.returncode == 0


def _classify(returncode: int) -> str:
    """Mirrors the classification rule the doc states, for pytest's exit codes:
    0 -> never-red, 2 -> unverifiable (collection error), else -> genuinely-red.

    An earlier version also inspected stdout for "AssertionError"/"assert" as
    a second signal — dead weight: for every case this file actually
    constructs, pytest's exit code alone already determines the outcome
    (verified above), so the stdout branch never changed a result and just
    obscured the rule behind an unparenthesized `or`/`and`. The doc's own
    prose covers other frameworks by principle, not this pytest-specific
    helper.
    """
    if returncode == 0:
        return "never-red"
    if returncode == 2:
        return "unverifiable"
    return "genuinely-red"


def _make_red_commit(repo: Path, test_source: str, other_files: dict[str, str] | None = None) -> str:
    """A repo with one commit titled like a Phase 0 red-test commit, containing
    `test_thing.py` plus any other files. Returns the commit SHA.
    """
    init_git_repo(repo)
    (repo / "test_thing.py").write_text(test_source)
    for name, content in (other_files or {}).items():
        (repo / name).write_text(content)
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "[TICKET] Phase 0: red tests")
    return git(repo, "rev-parse", "HEAD").stdout.strip()


def _run_at(repo: Path, worktree: Path, red_sha: str) -> subprocess.CompletedProcess:
    git(repo, "worktree", "add", "-q", str(worktree), red_sha)
    return subprocess.run(
        ["python3", "-m", "pytest", "test_thing.py", "-q"], cwd=worktree, capture_output=True, text=True
    )


def test_never_red_baseline_is_classified_as_fail(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    red_sha = _make_red_commit(repo, "def test_thing():\n    assert True\n")
    r = _run_at(repo, tmp_path / "wt", red_sha)
    assert _classify(r.returncode) == "never-red", (
        "a test that passes cleanly at RED must classify as never-red -> FAIL"
    )


def test_genuinely_red_baseline_is_classified_as_pass(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    red_sha = _make_red_commit(
        repo,
        "def test_thing():\n    from impl import compute\n    assert compute() == 42\n",
        {"impl.py": "def compute():\n    return 0\n"},  # wrong on purpose
    )
    r = _run_at(repo, tmp_path / "wt", red_sha)
    assert _classify(r.returncode) == "genuinely-red", (
        "a real assertion failure at RED must classify as genuinely-red -> PASS"
    )


def test_collection_error_baseline_is_classified_as_unverifiable_not_red(tmp_path: Path) -> None:
    """The refinement this ticket exists to add. A frozen test importing a
    module the implementation hasn't written yet errors at collection, not at
    an assertion — that is not proof the test was ever meaningfully red, and
    must not launder through as one under a bare exit-code check.
    """
    repo = tmp_path / "repo"
    repo.mkdir()
    # impl.py deliberately does not exist at RED — the module the agent adds later.
    red_sha = _make_red_commit(
        repo, "from impl import compute\ndef test_thing():\n    assert compute() == 42\n"
    )
    r = _run_at(repo, tmp_path / "wt", red_sha)
    assert r.returncode != 0, "sanity: this fixture must actually fail at RED"
    assert _classify(r.returncode) == "unverifiable", (
        "a collection error at RED (module not yet implemented) must classify as "
        "unverifiable, not genuinely-red — nothing was ever asserted"
    )
