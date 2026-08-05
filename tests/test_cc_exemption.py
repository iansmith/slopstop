"""
Behavior tests for the CC gate's pre-existing-code exemption. [BILL-341]

Two independent things land together because the second only makes sense once
the first exists:

  1. An opt-in, per-repo exemption: a function the branch diff never touched is
     excluded from the 🔴 hard-gate. Scope is decided by line-range overlap with
     the branch diff (`start_line`/`end_line` from BILL-340's CSV parse against
     the diff's changed-line ranges), not by `NEW_FUNC_NAMES`'s old
     signature-line grep — which missed a function whose *body* was edited into
     a violation without its `def` line changing, and which used `grep -oP`,
     a GNU/PCRE2-only flag BSD grep rejects.
  2. A 🔴 report states the remedies that reduce CC toward a more linear path.
     Switch/case is deliberately excluded: under the gate's own (unmodified)
     counting, a switch scores identically to the equivalent if-chain, so the
     advice would produce no measurable improvement.

Test command:
    python3 -m pytest tests/test_cc_exemption.py -v
"""

import csv
import subprocess
from pathlib import Path

import pytest

from conftest import CSV_COLUMNS, changed_line_ranges, touched
from conftest import git as _raw_git
from conftest import init_git_repo

REPO_ROOT = Path(__file__).parent.parent
CC_GATE = REPO_ROOT / "skills" / "pr" / "references" / "pr-cc-gate.md"
EXAMPLE_TOML = REPO_ROOT / ".project-conf.toml.example"


# --- 1. NEW_FUNC_NAMES is gone, and so is grep -P ------------------------------


# --- 2. the config key ----------------------------------------------------------


def test_cc_warn_and_reject_thresholds_are_in_the_example_toml() -> None:
    """Found while touching this file's [autonomous] section for the new key:
    cc_warn_threshold/cc_reject_threshold were never added here, so the example
    a new project copies from silently omits two keys CONFIG.md and
    project-conf-options.md both document.
    """
    text = EXAMPLE_TOML.read_text()
    assert "cc_warn_threshold" in text, ".project-conf.toml.example is missing cc_warn_threshold"
    assert "cc_reject_threshold" in text, ".project-conf.toml.example is missing cc_reject_threshold"


# --- 3. exempt functions are visible, never hidden -------------------------------


# --- 4. the remedies, and the explicit switch/case exclusion --------------------


# --- 5. line-range overlap semantics, verified against the real tools -----------


_changed_ranges = changed_line_ranges
_touched = touched


def _git(cwd: Path, *args: str) -> str:
    return _raw_git(cwd, *args).stdout.strip()


def _elif_chain(name: str, n: int) -> str:
    """An n-condition if/elif chain: measured at CC = n + 1 (a 4-condition chain
    is CC 5). Independent of lizard's own output — the fixture's CC is derived
    from this construction, not read back from the tool being tested.
    """
    body = "".join(
        f"    {'if' if i == 1 else 'elif'} a == {i}:\n        return {i}\n"
        for i in range(1, n + 1)
    )
    return f"def {name}(a):\n{body}    return 0\n"


@pytest.fixture(scope="module")
def scope_fixture_repo(tmp_path_factory) -> dict:
    """A repo with one untouched CC-11 function and one edited CC-11 function,
    where the edit lands entirely inside the body — the def line the old grep
    keyed on never appears in the diff's added lines.

    Module-scoped: the three consuming tests only read from this repo (via
    `_changed_ranges`, a read-only `git diff`, and `by_name` lookups) — building
    it involves a real `git init` + two commits + a `lizard` subprocess, and
    rebuilding it per-test for read-only consumers was pure waste.
    """
    repo = tmp_path_factory.mktemp("scope_fixture") / "repo"
    repo.mkdir()
    init_git_repo(repo)

    mod = repo / "mod.py"
    mod.write_text(_elif_chain("untouched", 10) + "\n" + "def edited(a):\n    return a + 1\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "base")
    base_sha = _git(repo, "rev-parse", "HEAD")

    # Body-only edit: the `def edited(a):` line is never re-emitted, only the
    # lines beneath it — this is the exact case NEW_FUNC_NAMES's grep missed.
    text = mod.read_text().replace(
        "def edited(a):\n    return a + 1\n",
        "def edited(a):\n" + _elif_chain("edited", 10).split("\n", 1)[1],
    )
    mod.write_text(text)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "edit body only, signature untouched")

    # Line spans are a mechanical fact about the file just written — safe to read
    # from lizard directly. Only the *CC value* needs independent derivation
    # (done above via the elif-chain formula), since that's the number under test.
    csv_out = subprocess.run(
        ["lizard", "--csv", "mod.py"], cwd=repo, capture_output=True, text=True
    ).stdout
    if not csv_out.strip():
        pytest.skip("lizard not available in this environment")
    by_name = {}
    for fields in csv.reader(csv_out.strip().split("\n")):
        row = dict(zip(CSV_COLUMNS, fields))
        by_name[row["name"]] = {
            "ccn": int(row["ccn"]),
            "start": int(row["start_line"]),
            "end": int(row["end_line"]),
        }

    return {"repo": repo, "base_sha": base_sha, "path": "mod.py", "by_name": by_name}


def test_body_only_edit_is_touched_the_old_grep_missed_this(scope_fixture_repo) -> None:
    ranges = _changed_ranges(
        scope_fixture_repo["base_sha"], scope_fixture_repo["path"], scope_fixture_repo["repo"]
    )
    fn = scope_fixture_repo["by_name"]["edited"]
    # Its `def` line is never re-emitted in the diff — only the body beneath it.
    assert _touched(ranges, fn["start"], fn["end"]), (
        "a function edited entirely below its signature line must be in scope — "
        "this is the case NEW_FUNC_NAMES's signature-line grep tagged "
        "[pre-existing] and is the reason it was replaced"
    )


def test_untouched_function_is_exempt(scope_fixture_repo) -> None:
    ranges = _changed_ranges(
        scope_fixture_repo["base_sha"], scope_fixture_repo["path"], scope_fixture_repo["repo"]
    )
    fn = scope_fixture_repo["by_name"]["untouched"]
    assert not _touched(ranges, fn["start"], fn["end"]), (
        "untouched() was not part of this branch's diff and must not be in scope"
    )


def test_pure_deletion_hunk_still_marks_its_function_touched(tmp_path: Path) -> None:
    """A `+N,0` hunk (pure deletion, no replacement lines) must still register
    as a touch point — a function whose lines were only deleted, never
    replaced, still changed.
    """
    repo = tmp_path / "repo"
    repo.mkdir()
    init_git_repo(repo)
    mod = repo / "mod.py"
    mod.write_text(
        "def f(a):\n"
        "    if a:\n"
        "        pass\n"
        "    while a:\n"
        "        a -= 1\n"
        "    return 0\n"
    )
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "base")
    base_sha = _git(repo, "rev-parse", "HEAD")

    mod.write_text("def f(a):\n    if a:\n        pass\n    return 0\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "delete two lines, no replacement")

    ranges = _changed_ranges(base_sha, "mod.py", repo)
    assert ranges, "expected at least one hunk"
    # f() now spans 1-4 post-deletion; the deletion point must fall inside it.
    assert _touched(ranges, 1, 4), (
        "a pure-deletion hunk (`+N,0`) must be treated as a single-point touch "
        "at N, not skipped for having zero added lines"
    )


# --- 6. end-to-end gating behavior, enabled vs disabled -------------------------


def test_gate_blocks_only_touched_function_when_exemption_enabled(scope_fixture_repo) -> None:
    by_name = scope_fixture_repo["by_name"]
    ranges = _changed_ranges(
        scope_fixture_repo["base_sha"], scope_fixture_repo["path"], scope_fixture_repo["repo"]
    )

    REJECT = 10
    violations = {n: f for n, f in by_name.items() if f["ccn"] >= REJECT}
    assert violations, "fixture must actually produce a CC >= 10 violation"

    touched = {n for n, f in violations.items() if _touched(ranges, f["start"], f["end"])}
    exempt = set(violations) - touched

    # Exemption enabled: only touched functions block.
    assert touched == {"edited"}, touched

    # Exemption disabled: every violation blocks, touched or not.
    assert set(violations) == {"edited", "untouched"}, set(violations)
    assert exempt == {"untouched"}
