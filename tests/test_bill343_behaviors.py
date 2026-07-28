"""
Phase 0 red tests for BILL-343 — a vacuity gate that re-runs every test changed
since the merge-base against the base implementation, so a test written or
edited AFTER Phase 0 still has to pin something.

https://github.com/iansmith/slopstop/issues/343

`:plan` Step 0e (red-at-Phase-0) and Step 0f (the adversary's vacuous-test
vector) both fire before implementation. A test written or edited afterward —
a review-round or simplify-round edit, or anything an implementation agent
adds outside the Phase 0 commit — passes through neither. This bit twice in
BILL-340 itself: one vacuous assertion was introduced during the simplify
round, after both Phase-0 gates had already fired, and was only caught by
hand — mutating the doc and noticing the test stayed green.

Complementary to BILL-287, not a duplicate (recorded on both tickets):

|                          | BILL-287                  | this ticket                     |
|--------------------------|----------------------------|----------------------------------|
| question                 | was the baseline ever red? | does each changed test pin anything? |
| tests in scope           | the frozen set              | every test changed since merge-base |
| reverts to                | $RED                        | merge-base(origin/BASE, HEAD)    |
| covers post-Phase-0 tests | no                          | yes — the whole point            |
| home                      | :run handoff verification   | :pr, beside Step 2d              |

Design decisions this file pins:

- Changed test functions are found by AST line-range overlap with the diff
  (BILL-341's technique — a `def`/`func` signature grep would miss a test
  whose body was edited without its signature line changing, which is
  exactly BILL-340's second vacuous assertion: the assertion line changed,
  the `def test_gate_requires_a_quote_aware_parser(...)` line did not).
- A test that passes cleanly at BASE is 🔴 UNLESS it carries a
  `SLOPSTOP PRAGMA coverage-backfill` comment — the existing pragma
  convention this repo already uses for the CC gate's NLOC opt-out
  (`pr-cc-gate.md`), not an invented mechanism.
- A collection/import error at BASE is a distinct `inconclusive` outcome,
  not proof of redness — same distinction BILL-340 drew for the CC gate and
  BILL-287 drew for the Phase 0 baseline.

Test command:
    python3 -m pytest tests/test_bill343_behaviors.py -v
"""

import ast
import re
import subprocess
import tempfile
from pathlib import Path

import pytest

from conftest import changed_line_ranges, git, init_git_repo, touched

REPO_ROOT = Path(__file__).parent.parent
PR_SKILL = REPO_ROOT / "skills" / "pr" / "SKILL.md"
SLOP_DETECTION = REPO_ROOT / "skills" / "pr" / "references" / "pr-slop-detection.md"
CONFIG_MD = REPO_ROOT / "CONFIG.md"
CONF_OPTIONS = REPO_ROOT / "design" / "project-conf-options.md"
ADVERSARY_GAPS = REPO_ROOT / "skills" / "plan" / "references" / "plan-adversary-gaps.md"

PRAGMA = "SLOPSTOP PRAGMA coverage-backfill"


@pytest.fixture(scope="module")
def pr_skill() -> str:
    return PR_SKILL.read_text()


@pytest.fixture(scope="module")
def slop_detection() -> str:
    return SLOP_DETECTION.read_text()


@pytest.fixture
def vacuity_section(slop_detection: str) -> str:
    start = slop_detection.lower().find("vacuity")
    assert start != -1, "no 'vacuity' section found in pr-slop-detection.md"
    next_heading = slop_detection.find("\n## ", start)
    end = next_heading if next_heading != -1 else len(slop_detection)
    return slop_detection[start:end]


# --- 1. the gate exists, beside Step 2d, unskippable -----------------------------


def test_vacuity_gate_exists(pr_skill: str) -> None:
    assert re.search(r"vacuity|changed test.{0,20}(re-?run|BASE)", pr_skill, re.IGNORECASE), (
        "skills/pr/SKILL.md must add a step re-running every test changed since "
        "the merge-base against the base implementation"
    )


def test_vacuity_gate_is_not_skipped_by_any_flag(pr_skill: str) -> None:
    """DoD: 'No flag skips it; verified by a test asserting the skip conditions
    match Step 2d's.' Step 2d's own no-skip statement names --no-test,
    --no-adversary, and on_slop_findings explicitly as flags that do NOT skip
    it. The new gate must make the identical claim, not a shorter or looser one.
    """
    # Anchored on the actual heading, not a bare substring: "Step 2d" and
    # "Step 2e" both appear earlier as forward-references inside Step 2's own
    # text (e.g. "skip Step 2's test run and Step 2e's slop gate"), so
    # `.find("Step 2d")` lands there first — before the real "## Step 2d"
    # heading — and produces an inverted, empty slice. Caught by running this
    # test: it failed with "test bug" against the real doc on the first try.
    step_2d_start = pr_skill.find("## Step 2d")
    step_2e_start = pr_skill.find("## Step 2e")
    assert step_2d_start != -1 and step_2e_start != -1 and step_2d_start < step_2e_start
    step_2d = pr_skill[step_2d_start:step_2e_start]
    vacuity_start = pr_skill.lower().find("vacuity")
    assert vacuity_start != -1
    vacuity_step = pr_skill[vacuity_start : vacuity_start + 1500]

    for flag in ["--no-test", "--no-adversary", "on_slop_findings"]:
        assert flag in step_2d, f"test bug: Step 2d itself should name {flag}"
        assert flag in vacuity_step, (
            f"the vacuity gate must name {flag} as a flag that does NOT skip it, "
            "matching Step 2d's own no-skip statement — otherwise the fleet agent "
            "that composes its own :pr invocation controls the switch that polices it"
        )


def test_no_config_key_can_disable_the_gate() -> None:
    """DoD out-of-scope: 'Do NOT add a config key that disables the gate.'
    An on_vacuity_findings-style knob (mirroring on_redtest_tamper) may exist
    to control autonomous FAILURE HANDLING (hard-stop vs warn), but it must
    not offer a 'skip' value — same reasoning on_redtest_tamper's own doc
    gives for why IT has no skip value.
    """
    for doc in (CONFIG_MD, CONF_OPTIONS, SLOP_DETECTION):
        text = doc.read_text()
        assert not re.search(r"on_vacuity\w*.{0,60}\bskip\b", text, re.IGNORECASE), (
            f"{doc.name}: an on_vacuity_* knob must not offer a skip value — "
            "the whole point of DoD behavior 6 is that no flag disables this gate"
        )


# --- 2. changed-test-function identification: line-range, not signature grep ------


def test_gate_uses_ast_or_line_range_not_a_signature_grep(vacuity_section: str) -> None:
    """A `def test_x(` grep on added lines only catches BRAND NEW test
    functions — a body-only edit to an EXISTING test (BILL-340's actual
    second vacuous assertion: the assertion line changed, `def
    test_gate_requires_a_quote_aware_parser(...)` did not) would be invisible
    to it. This is the exact blind spot BILL-341 fixed for the CC gate by
    replacing a signature grep with line-range overlap; the vacuity gate must
    not reintroduce it.
    """
    assert re.search(r"\bast\b|line.?range|overlap", vacuity_section, re.IGNORECASE), (
        "the gate must identify changed test functions by line-range overlap "
        "(or an AST-derived function span), not merely by matching added def lines"
    )


def test_gate_does_not_use_grep_dash_capital_p() -> None:
    """The repeat offender. Checked directly rather than assumed."""
    text = SLOP_DETECTION.read_text()
    assert not re.search(r"grep\s+-\w*P\w*\b|\\K", text), (
        "grep -P / \\K is PCRE2-only and BSD grep (macOS default) rejects it "
        "with exit 2 and empty stdout — the same class of defect BILL-340 and "
        "BILL-341 both fixed elsewhere; do not reintroduce it here"
    )


def test_ast_correctly_spans_a_body_only_edit() -> None:
    """Pins the actual mechanism against Python's real ast module: a test
    function's line span covers its whole body, so a diff touching only the
    body (never the `def` line) still overlaps the function's ast span.
    """
    src = (
        "def test_a():\n"
        "    assert True\n"
        "\n"
        "def test_b():\n"
        "    x = 1\n"
        "    assert x == 1\n"
    )
    tree = ast.parse(src)
    spans = {
        n.name: (n.lineno, n.end_lineno)
        for n in ast.walk(tree)
        if isinstance(n, ast.FunctionDef) and n.name.startswith("test")
    }
    assert spans == {"test_a": (1, 2), "test_b": (4, 6)}
    # A hunk touching only line 6 (the assertion, not the def on line 4) must
    # still fall inside test_b's span.
    assert spans["test_b"][0] <= 6 <= spans["test_b"][1]


def test_pytest_node_id_selection_reports_collection_errors_as_exit_4_not_2() -> None:
    """This gate selects specific test node-ids (`file.py::test_x`), unlike
    BILL-287's whole-file invocation, which already pins the whole-file
    premise (exit 2) — not re-derived here. Verified directly, since assuming
    the same exit code applies across both invocation styles would have been
    wrong: the identical broken import that exits 2 whole-file exits 4
    (pytest's usage-error code) when a specific node-id is requested —
    confirmed empirically before writing the gate's classification rule.
    """
    with tempfile.TemporaryDirectory() as raw_d:
        d = Path(raw_d)
        (d / "test_b.py").write_text("import nonexistent_xyz\ndef test_y():\n    assert True\n")
        node_id = subprocess.run(
            ["python3", "-m", "pytest", "test_b.py::test_y", "-q"], cwd=d, capture_output=True, text=True
        )
        assert node_id.returncode == 4, (
            f"expected exit 4 for a node-id-scoped collection error, got {node_id.returncode}"
        )

        # A node-id that simply doesn't exist (e.g. a test only added at HEAD,
        # not present at BASE at all) reports the same exit 4 — both must
        # classify as inconclusive, not confirmed-red.
        (d / "test_c.py").write_text("def test_real():\n    assert True\n")
        missing = subprocess.run(
            ["python3", "-m", "pytest", "test_c.py::test_does_not_exist", "-q"],
            cwd=d, capture_output=True, text=True,
        )
        assert missing.returncode == 4


# --- 3. classification: pins-new-behavior vs backfill vs inconclusive -------------


def test_pragma_convention_matches_existing_house_style(vacuity_section: str) -> None:
    """Not an invented mechanism — the exact `SLOPSTOP PRAGMA <name>` shape
    pr-cc-gate.md already uses for the NLOC opt-out.
    """
    assert PRAGMA in vacuity_section, (
        f"the gate must use the existing pragma convention verbatim: {PRAGMA!r}"
    )
    cc_gate_text = (REPO_ROOT / "skills" / "pr" / "references" / "pr-cc-gate.md").read_text()
    assert "SLOPSTOP PRAGMA" in cc_gate_text, (
        "test bug: the existing pragma convention this test cites must actually "
        "exist in pr-cc-gate.md"
    )


def test_backfill_is_declared_counted_and_listed(vacuity_section: str) -> None:
    assert re.search(r"declar\w+", vacuity_section, re.IGNORECASE), (
        "backfills must be declared (via the pragma), not silently exempted"
    )
    assert re.search(r"count\w*", vacuity_section, re.IGNORECASE), (
        "the backfill count must be visible in the summary — the count is the "
        "control that stops an agent from quietly relabeling everything as backfill"
    )


def test_pass_at_base_without_pragma_is_red(vacuity_section: str) -> None:
    assert "🔴" in vacuity_section, (
        "a changed test that passes cleanly at BASE, without the backfill "
        "pragma, must be a 🔴 finding naming the test"
    )


def test_collection_error_is_inconclusive_not_red(vacuity_section: str) -> None:
    assert re.search(r"inconclusive", vacuity_section, re.IGNORECASE), (
        "a BASE that cannot even collect/import must report inconclusive, not "
        "pass silently and not count as a confirmed red test either — DoD "
        "behavior 5, same discipline BILL-340 applied to the CC gate"
    )
    assert re.search(r"collection|import.{0,10}error", vacuity_section, re.IGNORECASE), (
        "the gate must name collection/import errors as the inconclusive case, "
        "distinct from a genuine assertion failure"
    )


# --- 4. plan-adversary-gaps.md gets the cross-reference ---------------------------


def test_adversary_gaps_notes_the_mechanical_backstop() -> None:
    text = ADVERSARY_GAPS.read_text()
    assert re.search(r"BILL-343|mechanical.{0,30}backstop|vacuity gate", text, re.IGNORECASE), (
        "plan-adversary-gaps.md's vector 5 (false negatives / vacuous tests) "
        "must note it is now mechanically backstopped post-Phase-0 by the "
        "vacuity gate — the ticket's own file map requires this cross-reference"
    )


# --- 5. end-to-end against real git + real pytest ---------------------------------


# Hunk-header parsing (_git_diff_line_range) reuses conftest's
# `changed_line_ranges` — the second occurrence of that exact algorithm as of
# this ticket (test_cc_exemption.py had its own copy); see conftest.py.
_git_diff_line_range = changed_line_ranges


def _changed_test_functions(source: str, ranges: list[tuple[int, int]]) -> list[str]:
    tree = ast.parse(source)
    changed = []
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name.startswith("test"):
            if touched(ranges, node.lineno, node.end_lineno):
                changed.append(node.name)
    return changed


def _classify(test_id: str, cwd: Path, has_pragma: bool) -> str:
    r = subprocess.run(
        ["python3", "-m", "pytest", test_id, "-q"], cwd=cwd, capture_output=True, text=True
    )
    if has_pragma:
        return "backfill"
    if r.returncode == 0:
        return "vacuous"
    # Selecting a SPECIFIC node-id (this gate's invocation style, unlike
    # BILL-287's whole-file run) reports collection errors AND a genuinely
    # missing node-id as exit 4 — pytest's usage-error code — not exit 2.
    # Verified empirically: `pytest file.py::test_x` on a broken import exits
    # 4; `pytest file.py` on the same file exits 2. Both are non-assertion
    # failures either way.
    if r.returncode in (2, 4):
        return "inconclusive"
    return "confirmed-red"


def test_body_only_edit_to_existing_test_is_detected_and_classified(tmp_path: Path) -> None:
    """The regression fixture for BILL-340's SECOND vacuous assertion, in its
    original shape: an existing test's assertion line changes; its `def`
    line does not. A signature grep sees nothing changed. Line-range overlap
    does.
    """
    repo = tmp_path / "repo"
    repo.mkdir()
    init_git_repo(repo)
    (repo / "test_thing.py").write_text(
        "def test_gate_requires_a_quote_aware_parser():\n"
        "    fenced = ['CC_CSV=$($CC_CMD --csv $CHANGED_CODE)']\n"
        "    assert any('csv' in block for block in fenced)\n"
    )
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "base")
    base_sha = git(repo, "rev-parse", "HEAD").stdout.strip()

    # Body-only edit: the def line is untouched, only the assertion changes —
    # matching BILL-340's actual defect exactly (the vacuous "csv" in block
    # check was never tightened by touching the signature).
    (repo / "test_thing.py").write_text(
        "def test_gate_requires_a_quote_aware_parser():\n"
        "    fenced = ['CC_CSV=$($CC_CMD --csv $CHANGED_CODE)']\n"
        "    assert any('csv' in block for block in fenced)  # still vacuous\n"
    )
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "simplify round: reword comment, assertion unchanged")

    ranges = _git_diff_line_range(base_sha, "test_thing.py", repo)
    changed = _changed_test_functions((repo / "test_thing.py").read_text(), ranges)
    assert changed == ["test_gate_requires_a_quote_aware_parser"], (
        "line-range overlap must detect the change even though the def line "
        "never appears in the diff"
    )


def test_gate_flags_a_test_that_passes_cleanly_at_base(tmp_path: Path) -> None:
    """Vacuity, direct: a brand-new test that already passes against the base
    implementation — asserts nothing the branch actually did.
    """
    repo = tmp_path / "repo"
    repo.mkdir()
    init_git_repo(repo)
    (repo / "test_thing.py").write_text("")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "base")
    base_sha = git(repo, "rev-parse", "HEAD").stdout.strip()

    (repo / "test_thing.py").write_text(
        "def test_new_behavior():\n    assert 1 == 1\n"  # vacuous — always true
    )
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "add test")

    worktree = tmp_path / "wt"
    git(repo, "worktree", "add", "-q", str(worktree), base_sha)
    (worktree / "test_thing.py").write_text((repo / "test_thing.py").read_text())

    assert _classify("test_thing.py::test_new_behavior", worktree, has_pragma=False) == "vacuous"


def test_declared_backfill_is_not_flagged_even_when_green_at_base(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    init_git_repo(repo)
    (repo / "test_thing.py").write_text(
        "def test_existing_behavior():\n    assert 1 + 1 == 2\n"
    )
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "base")
    base_sha = git(repo, "rev-parse", "HEAD").stdout.strip()

    source_with_pragma = (
        f"# {PRAGMA}: covering pre-existing behavior, not part of this branch\n"
        "def test_existing_behavior():\n    assert 1 + 1 == 2\n"
    )
    (repo / "test_thing.py").write_text(source_with_pragma)
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "declare backfill")

    worktree = tmp_path / "wt"
    git(repo, "worktree", "add", "-q", str(worktree), base_sha)
    (worktree / "test_thing.py").write_text((repo / "test_thing.py").read_text())

    has_pragma = PRAGMA in source_with_pragma
    assert has_pragma
    assert (
        _classify("test_thing.py::test_existing_behavior", worktree, has_pragma=has_pragma)
        == "backfill"
    )


def test_gate_confirms_a_genuinely_red_test(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    init_git_repo(repo)
    (repo / "test_thing.py").write_text("")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "base")
    base_sha = git(repo, "rev-parse", "HEAD").stdout.strip()

    (repo / "test_thing.py").write_text(
        "def test_new_behavior():\n    assert 1 == 2\n"  # genuinely fails at BASE
    )
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "add test")

    worktree = tmp_path / "wt"
    git(repo, "worktree", "add", "-q", str(worktree), base_sha)
    (worktree / "test_thing.py").write_text((repo / "test_thing.py").read_text())

    assert (
        _classify("test_thing.py::test_new_behavior", worktree, has_pragma=False)
        == "confirmed-red"
    )


def test_collection_error_at_base_is_inconclusive(tmp_path: Path) -> None:
    """A test importing a module the branch adds later errors at collection,
    not at an assertion — must not launder through as confirmed-red.
    """
    repo = tmp_path / "repo"
    repo.mkdir()
    init_git_repo(repo)
    (repo / "test_thing.py").write_text("")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "base")
    base_sha = git(repo, "rev-parse", "HEAD").stdout.strip()

    (repo / "test_thing.py").write_text(
        "from impl import compute\ndef test_new_behavior():\n    assert compute() == 42\n"
    )
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "add test")

    worktree = tmp_path / "wt"
    git(repo, "worktree", "add", "-q", str(worktree), base_sha)
    (worktree / "test_thing.py").write_text((repo / "test_thing.py").read_text())
    # impl.py deliberately NOT copied — it does not exist at BASE.

    assert (
        _classify("test_thing.py::test_new_behavior", worktree, has_pragma=False)
        == "inconclusive"
    )


# --- 6. DoD's combined scenario: outside the project root, one fixture, three tests


def test_combined_scenario_flags_exactly_the_vacuous_test(tmp_path: Path) -> None:
    """DoD: 'a fixture repo with (a) a genuinely-red new test, (b) a vacuous test
    asserting a string already present at base, (c) a declared backfill. The
    gate flags exactly (b).' Run from outside the project root, addressing the
    worktree by a relative path — the gate runs against whatever cwd :pr was
    invoked from, same discipline BILL-340's own e2e test established.
    """
    repo = tmp_path / "myrepo"
    repo.mkdir()
    init_git_repo(repo)

    greet_impl = "def greet(name):\n    return f'hello {name}'\n"
    test_base = (
        "from impl import greet\n\n"
        "def test_existing_greet():\n"
        "    assert greet('a') == 'hello a'\n"
    )
    test_head = (
        "from impl import greet\n\n"
        "def test_existing_greet():\n"
        "    assert greet('a') == 'hello a'\n"
        "\n"
        "# (a) genuinely red: greet() doesn't uppercase yet at BASE.\n"
        "def test_greet_shouts():\n"
        "    assert greet('a') == 'HELLO a'\n"  # genuinely false against BASE's greet()
        "\n"
        "# (b) vacuous: the string it asserts already appears at BASE, so this\n"
        "# passes whether or not the branch did anything.\n"
        "def test_greet_contains_hello():\n"
        "    assert 'hello' in greet('a')\n"
        "\n"
        f"# (c) {PRAGMA}: new test, covers pre-existing greet() behavior another way\n"
        "def test_greet_is_a_non_empty_string():\n"
        "    assert len(greet('a')) > 0\n"
    )

    (repo / "impl.py").write_text(greet_impl)
    (repo / "test_thing.py").write_text(test_base)
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "base")
    base_sha = git(repo, "rev-parse", "HEAD").stdout.strip()

    (repo / "test_thing.py").write_text(test_head)
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "add tests")

    ranges = _git_diff_line_range(base_sha, "test_thing.py", repo)
    source_at_head = (repo / "test_thing.py").read_text()
    changed = _changed_test_functions(source_at_head, ranges)
    assert set(changed) == {"test_greet_shouts", "test_greet_contains_hello", "test_greet_is_a_non_empty_string"}

    pragma_lines = {
        i + 1 for i, line in enumerate(source_at_head.split("\n")) if PRAGMA in line
    }
    tree = ast.parse(source_at_head)
    spans = {n.name: (n.lineno, n.end_lineno) for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}

    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    worktree = tmp_path / "wt"
    git(repo, "worktree", "add", "-q", str(worktree), base_sha)
    (worktree / "test_thing.py").write_text(source_at_head)

    # Genuinely "outside the project root, addressed by a relative path": cwd
    # is a sibling directory, and the worktree is reached via "../wt", not an
    # absolute path.
    rel_worktree = Path("..") / worktree.name

    results = {}
    for name in changed:
        fn_start, fn_end = spans[name]
        has_pragma = any(fn_start - 2 <= p <= fn_start for p in pragma_lines)
        r = subprocess.run(
            ["python3", "-m", "pytest", f"{rel_worktree}/test_thing.py::{name}", "-q"],
            cwd=elsewhere, capture_output=True, text=True,
        )
        if has_pragma:
            results[name] = "backfill"
        elif r.returncode == 0:
            results[name] = "vacuous"
        elif r.returncode in (2, 4):
            results[name] = "inconclusive"
        else:
            results[name] = "confirmed-red"

    assert results == {
        "test_greet_shouts": "confirmed-red",
        "test_greet_contains_hello": "vacuous",
        "test_greet_is_a_non_empty_string": "backfill",
    }, results

    vacuous = {name for name, verdict in results.items() if verdict == "vacuous"}
    assert vacuous == {"test_greet_contains_hello"}, (
        f"the gate must flag exactly the vacuous test — flagged {vacuous}"
    )
