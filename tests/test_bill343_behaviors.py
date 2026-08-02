"""
Mechanics of the `:pr` vacuity gate (BILL-343) — the executable half.

https://github.com/iansmith/slopstop/issues/343

The gate re-runs every test changed since the merge-base against the BASE
implementation, so a test written or edited AFTER Phase 0 still has to pin
something. `:plan` Step 0e and Step 0f both fire before implementation, so a
test added during a review or simplify round passes through neither.

**Pruned 2026-08-01.** This file used to also assert that particular sentences
appeared in `pr-slop-detection.md` and `pr/SKILL.md` describing the gate. Those
went with the rest of the doc-assertion suites — they pinned wording, not
behavior. What remains executes:

  - end-to-end gate scenarios against real git repos in tmp_path (a body-only
    edit is detected; a test green at BASE is flagged; a declared backfill is
    not; a genuinely red test is confirmed; a collection error is inconclusive;
    a same-directory conftest is copied at HEAD content);
  - two library/platform facts the gate's algorithm depends on and that are
    NOT safe to assume — that a Python `ast` function span covers the body, so
    a hunk touching only an assertion still overlaps its function; and that
    pytest reports a collection error as exit **4** when a specific node-id is
    selected, not the exit 2 a whole-file run gives. The second was verified
    empirically before the gate's classification rule was written, because
    carrying BILL-287's whole-file premise across would have been wrong.

The BSD-vs-GNU grep portability check that used to live here is now generalized
over every skill markdown file in `test_structural_invariants.py`.

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

PRAGMA = "SLOPSTOP PRAGMA coverage-backfill"


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


def test_same_directory_conftest_is_copied_at_head_content(tmp_path: Path) -> None:
    """Pins the doc's partial mitigation for the altitude review's finding: a
    same-directory conftest.py the branch also changed must be copied at its
    HEAD content into the BASE worktree, not left at BASE's stale content —
    otherwise a changed test re-run against a stale fixture can produce a
    silently wrong verdict. Verified directly against the shell recipe
    pr-slop-detection.md documents, not assumed from reading it.
    """
    repo = tmp_path / "repo"
    sub = repo / "sub"
    sub.mkdir(parents=True)
    init_git_repo(repo)
    (sub / "conftest.py").write_text("def fixture_value():\n    return 1\n")
    (sub / "test_a.py").write_text("def test_a():\n    assert True\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "base")
    base_sha = git(repo, "rev-parse", "HEAD").stdout.strip()

    (sub / "conftest.py").write_text("def fixture_value():\n    return 2\n")
    (sub / "test_a.py").write_text(
        "def test_a():\n    assert True\ndef test_b():\n    assert True\n"
    )
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "head")

    all_changed = git(repo, "diff", "--name-only", f"{base_sha}..HEAD").stdout.strip().split("\n")
    changed_test_files = [
        f for f in all_changed if re.search(r"test_.*\.py$|_test\.go$", f)
    ]
    assert changed_test_files == ["sub/test_a.py"]

    worktree = tmp_path / "wt"
    git(repo, "worktree", "add", "-q", str(worktree), base_sha)
    for f in changed_test_files:
        (worktree / f).parent.mkdir(parents=True, exist_ok=True)
        (worktree / f).write_text(git(repo, "show", f"HEAD:{f}").stdout)
    dirs = sorted({str(Path(f).parent) for f in changed_test_files})
    for d in dirs:
        r = git(repo, "show", f"HEAD:{d}/conftest.py", check=False)
        if r.returncode == 0:
            (worktree / d / "conftest.py").write_text(r.stdout)

    assert (worktree / "sub" / "conftest.py").read_text() == "def fixture_value():\n    return 2\n", (
        "the copied conftest.py must carry HEAD's content, not BASE's stale one"
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
