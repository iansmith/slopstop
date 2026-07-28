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

REPO_ROOT = Path(__file__).parent.parent
CC_GATE = REPO_ROOT / "skills" / "pr" / "references" / "pr-cc-gate.md"
TEST_GATES = REPO_ROOT / "skills" / "pr" / "references" / "pr-test-gates.md"

# lizard --csv emits headerless rows in this column order. Verified against
# lizard 1.23.0; `long_name` and `signature` are quoted and may contain commas.
CSV_COLUMNS = [
    "nloc",
    "ccn",
    "token_count",
    "param_count",
    "length",
    "long_name",
    "filename",
    "name",
    "signature",
    "start_line",
    "end_line",
]

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


def _tracked_files() -> list[Path]:
    out = subprocess.run(
        ["git", "ls-files"], cwd=REPO_ROOT, capture_output=True, text=True, check=True
    ).stdout
    return [REPO_ROOT / p for p in out.split("\n") if p]


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


def test_no_tracked_file_invokes_lizard_with_json() -> None:
    """`--json` is not a lizard flag. Any occurrence is a gate that cannot run.

    Excludes this file itself: it necessarily says "lizard --json" in its own
    docstring and assertion message while describing the defect it guards
    against, and that prose is not an invocation.
    """
    offenders = []
    for path in _tracked_files():
        if path == Path(__file__).resolve():
            continue
        try:
            text = path.read_text()
        except (UnicodeDecodeError, OSError):
            continue
        for n, line in enumerate(text.split("\n"), 1):
            if re.search(r"(lizard|CC_CMD)[^\n]*--json", line):
                offenders.append(f"{path.relative_to(REPO_ROOT)}:{n}: {line.strip()}")
    assert not offenders, (
        "lizard has no --json flag (exit 2, usage error, empty stdout):\n  "
        + "\n  ".join(offenders)
    )


def test_gate_invokes_lizard_with_csv(cc_gate: str) -> None:
    assert re.search(r"\$CC_CMD[^\n]*--csv", cc_gate), (
        "pr-cc-gate.md must invoke lizard with --csv, the supported output mode"
    )


def test_gate_documents_the_csv_columns_in_order(cc_gate: str) -> None:
    """A headerless format is only parseable if the doc states the column order.

    Matched against one declared contract line rather than first-occurrence
    positions across the file: several column names (`name`, `filename`, `length`)
    also occur in unrelated prose and flags — `--name-only` alone would decide the
    ordering — so a scan would be measuring the wrong thing.
    """
    declared = [
        l.strip().lstrip("#").strip()
        for l in cc_gate.split("\n")
        if l.count(",") == len(CSV_COLUMNS) - 1 and "nloc" in l and "end_line" in l
    ]
    assert declared, (
        "pr-cc-gate.md must declare the lizard --csv column order on one line, "
        f"comma-separated: {','.join(CSV_COLUMNS)}"
    )
    for line in declared:
        got = [f.strip().strip("`") for f in line.split(",")]
        assert got == CSV_COLUMNS, (
            f"declared column order does not match lizard's output order: {got}"
        )


def test_gate_requires_a_quote_aware_parser(cc_gate: str) -> None:
    """`"branchy( a , b , c )"` splits into four on a naive delimiter split.

    Scoped to fenced code blocks. Prose is where the doc *warns against* delimiter
    splitting, and a whole-file regex cannot tell a prohibition from a recipe — it
    flagged the warning itself.
    """
    fenced = re.findall(r"```(?:bash|sh)?\n(.*?)```", cc_gate, re.DOTALL)
    assert fenced, "pr-cc-gate.md has no fenced code blocks"
    naive = [
        line
        for block in fenced
        for line in block.split("\n")
        if re.search(r"cut\s+-d\s*[\"']?,|\.split\(\s*[\"'],[\"']\s*\)", line)
    ]
    assert not naive, (
        "a fenced recipe splits CSV on the comma; the quoted long_name and "
        "signature fields contain commas for any multi-parameter function, which "
        f"shifts every later column: {naive}"
    )
    # Not `"csv" in block` — the measurement line `CC_CSV=$($CC_CMD --csv ...)`
    # contains that substring, so the check would pass with the parse example
    # deleted outright.
    assert any(re.search(r"import csv|csv\.reader", b) for b in fenced), (
        "pr-cc-gate.md must show a quote-aware CSV parse, not just describe one"
    )


# --- 2. stderr -----------------------------------------------------------------


def test_measurement_does_not_discard_stderr(cc_gate: str) -> None:
    """2>/dev/null on the measurement is what hid this defect for its whole life."""
    measurement = [
        l for l in cc_gate.split("\n") if "$CC_CMD" in l and "--csv" in l
    ]
    # Asserted, not assumed: a loop over an empty match list is a vacuous pass,
    # and this test would then "pass" against the very gate it exists to check.
    assert measurement, (
        "pr-cc-gate.md has no `$CC_CMD --csv` measurement line to check"
    )
    for line in measurement:
        assert "2>/dev/null" not in line, (
            "the lizard measurement discards stderr; lizard reports usage and "
            "parse errors there, and suppressing it is why a broken flag looked "
            f"like a missing tool: {line.strip()}"
        )


# --- 3. failure is not a silent pass -------------------------------------------


def test_nonzero_exit_is_a_gate_error_not_a_skip(cc_gate: str) -> None:
    assert re.search(
        r"exits?\s+non-?zero[^\n]*", cc_gate, re.IGNORECASE
    ), "pr-cc-gate.md must state what happens when lizard exits non-zero"
    section = re.search(
        r"exits?\s+non-?zero(.{0,400})", cc_gate, re.IGNORECASE | re.DOTALL
    ).group(1)
    assert "🔴" in section, (
        "a lizard that exited non-zero measured nothing; that must be a 🔴 gate "
        "error, not a warning the run continues past"
    )


def test_empty_output_with_changed_files_is_not_a_silent_skip(cc_gate: str) -> None:
    """lizard exits 0 with no rows for a missing file AND for an unparseable one.

    So emptiness cannot distinguish "no functions here" from "measurement failed",
    and the old rule resolved that ambiguity by passing the PR.

    Pinned structurally — on the outcome list rather than on any sentence. Matching
    the removed prose would go green again the moment a fail-open was reintroduced
    in different words, which is the only way this test can matter.
    """
    lines = cc_gate.split("\n")
    start = next(
        (i for i, l in enumerate(lines) if l.startswith("###") and "outcomes" in l), None
    )
    assert start is not None, (
        "pr-cc-gate.md must enumerate the measurement outcomes under their own heading"
    )
    bullets: list[str] = []
    for line in lines[start + 1 :]:
        if line.startswith("- "):
            bullets.append(line[2:])
        elif line.startswith(("#", "**")):  # next heading or paragraph ends the list
            break
        elif line.startswith("  ") and bullets:  # continuation of the current bullet
            bullets[-1] += " " + line.strip()
    assert len(bullets) == 3, (
        f"expected 3 measurement outcomes (error / inconclusive / measured), "
        f"got {len(bullets)}"
    )
    dispositions = [b.lower() for b in bullets]
    assert not any(re.search(r"\bskip\w*\b", d) for d in dispositions), (
        "no measurement outcome may dispose of itself by skipping the gate — that "
        "is the rule that turned a broken invocation into a silent pass"
    )
    assert any("🔴" in b for b in bullets), "a measurement failure must be a 🔴"
    assert any("⚠️" in b for b in bullets), (
        "zero rows against a non-empty CHANGED_CODE must be surfaced explicitly, "
        "naming the files, rather than passed over"
    )


# The threshold-drift check that BILL-340 also needed — `pr-test-gates.md` was
# left at the old 10/15 by 747c87e — lives in test_cc_thresholds.py, added to the
# existing `test_docs_agree_with_the_gate` parametrize rather than duplicated here
# with a second regex dialect.


# --- 4. end-to-end against the real binary --------------------------------------


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
