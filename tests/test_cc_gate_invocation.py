"""
Behavior tests for how the :pr CC gate invokes and parses lizard. [BILL-340]

The gate was specified against `lizard --json`, a flag lizard has never had. The
invocation failed with a usage error on every run, `2>/dev/null` swallowed the
diagnostic, and the documented rule for empty output was to skip the gate with a
warning. So the CC hard-gate and the NLOC check were inert everywhere, and the
failure looked like an environment problem rather than a broken command.

These tests pin the three things that let that survive:

  1. the flag actually passed to lizard,
  2. that stderr is not discarded,
  3. that a gate which could not measure says so instead of passing quietly.

Plus an end-to-end check against the real binary, because every one of the six
existing threshold tests passed against a gate that never ran — asserting on prose
cannot tell you the command works.

Test command:
    python3 -m pytest tests/test_cc_gate_invocation.py -v
"""

import csv
import functools
import io
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import CSV_COLUMNS

REPO_ROOT = Path(__file__).parent.parent
CC_GATE = REPO_ROOT / "skills" / "pr" / "references" / "pr-cc-gate.md"
TEST_GATES = REPO_ROOT / "skills" / "pr" / "references" / "pr-test-gates.md"

# A fixture whose complexity is derived by hand, not read back from the gate.
# branchy: 1 (base) + if a + if b + elif c + for + if i>5 + while = 7
FIXTURE = """\
def simple(a):
    return a + 1

def branchy(a, b, c):
    if a:
        if b:
            return 1
        elif c:
            return 2
    for i in range(10):
        if i > 5:
            break
    while a:
        a -= 1
    return 0
"""
FIXTURE_EXPECTED_CC = {"simple": 1, "branchy": 7}


@pytest.fixture(scope="module")
def cc_gate() -> str:
    return CC_GATE.read_text()


@functools.lru_cache(maxsize=None)
def _lizard_cmd() -> tuple[str, ...]:
    """Resolve lizard the way the gate's own cascade does, or fail loudly.

    Deliberately not a skip. A missing tool silently disabling the test that
    guards against a silently disabled gate is the same bug one level up.

    Cached: when lizard is importable but off PATH — the `pip install --user`
    layout the gate's own cascade exists for — the fallback probe is a ~77 ms
    subprocess, and three calls would be a third of the whole suite's runtime.
    `pytest.fail` raises, so a failure is never cached.
    """
    if shutil.which("lizard"):
        return ("lizard",)
    probe = subprocess.run(
        [sys.executable, "-c", "import lizard"], capture_output=True
    )
    if probe.returncode == 0:
        return (sys.executable, "-m", "lizard")
    pytest.fail(
        "lizard is not installed, so the CC gate's invocation cannot be verified. "
        "Fix: pip install lizard"
    )


# --- 1. the flag ---------------------------------------------------------------


def test_documented_invocation_works_from_outside_the_repo_with_a_relative_path(
    tmp_path: Path,
) -> None:
    """Run the real tool the documented way and check the contract holds.

    Deliberately run from a directory outside the repo, addressing the fixture by
    a relative path — the gate runs against whatever cwd :pr was invoked from.
    """
    workdir = tmp_path
    src_dir = workdir / "pkg"
    src_dir.mkdir()
    (src_dir / "sample.py").write_text(FIXTURE)

    outside = workdir / "elsewhere"
    outside.mkdir()

    result = subprocess.run(
        list(_lizard_cmd()) + ["--csv", "../pkg/sample.py"],
        cwd=outside,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        f"lizard --csv exited {result.returncode}: {result.stderr}"
    )
    assert result.stdout.strip(), (
        "lizard --csv produced no output for a file with two functions"
    )

    rows = list(csv.reader(io.StringIO(result.stdout)))
    assert all(len(r) == len(CSV_COLUMNS) for r in rows), (
        f"expected {len(CSV_COLUMNS)} columns per row, got {[len(r) for r in rows]}"
    )

    by_name = {r[CSV_COLUMNS.index("name")]: r for r in rows}
    assert set(by_name) == set(FIXTURE_EXPECTED_CC)

    for name, expected_cc in FIXTURE_EXPECTED_CC.items():
        row = by_name[name]
        assert int(row[CSV_COLUMNS.index("ccn")]) == expected_cc, (
            f"{name}: expected hand-derived CC {expected_cc}, "
            f"got {row[CSV_COLUMNS.index('ccn')]}"
        )
        start = int(row[CSV_COLUMNS.index("start_line")])
        end = int(row[CSV_COLUMNS.index("end_line")])
        assert start < end, f"{name}: start_line/end_line not a usable range"

    # The multi-parameter signature is why a delimiter split cannot be used.
    assert "," in by_name["branchy"][CSV_COLUMNS.index("signature")]


def test_lizard_exits_zero_on_unmeasurable_input(tmp_path: Path) -> None:
    """The premise behind the inconclusive outcome, pinned against the real tool.

    If lizard ever starts signalling these through its exit code, the gate can be
    simplified — and this test is what will tell us.
    """
    missing = subprocess.run(
        list(_lizard_cmd()) + ["--csv", str(tmp_path / "does-not-exist.py")],
        capture_output=True,
        text=True,
    )
    unparseable = tmp_path / "bad.py"
    unparseable.write_text("def broken(\n")
    broken = subprocess.run(
        list(_lizard_cmd()) + ["--csv", str(unparseable)], capture_output=True, text=True
    )
    assert (missing.returncode, missing.stdout.strip()) == (0, "")
    assert (broken.returncode, broken.stdout.strip()) == (0, "")
