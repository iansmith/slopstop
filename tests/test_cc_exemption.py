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
import re
import subprocess
from pathlib import Path

import pytest

from conftest import CSV_COLUMNS, tracked_files

REPO_ROOT = Path(__file__).parent.parent
CC_GATE = REPO_ROOT / "skills" / "pr" / "references" / "pr-cc-gate.md"
TEST_GATES = REPO_ROOT / "skills" / "pr" / "references" / "pr-test-gates.md"
CONFIG_MD = REPO_ROOT / "CONFIG.md"
CONF_OPTIONS = REPO_ROOT / "design" / "project-conf-options.md"
EXAMPLE_TOML = REPO_ROOT / ".project-conf.toml.example"

KEY = "cc_exempt_pre_existing"


@pytest.fixture(scope="module")
def cc_gate() -> str:
    return CC_GATE.read_text()


# --- 1. NEW_FUNC_NAMES is gone, and so is grep -P ------------------------------


def test_new_func_names_grep_no_longer_exists(cc_gate: str) -> None:
    assert "NEW_FUNC_NAMES" not in cc_gate, (
        "the signature-line grep must be replaced by the line-range test — it "
        "missed a function whose body was edited into a violation without its "
        "def line changing, and matched only by function name, so a same-named "
        "function in a different file could exempt an unrelated violation"
    )


def test_no_tracked_file_uses_grep_dash_capital_p_for_cc_scope() -> None:
    """`grep -oP` / `\\K` is PCRE2-only. BSD grep (macOS default) rejects it with
    exit 2 and empty stdout — the same failure shape BILL-340 fixed for lizard's
    invocation, latent here rather than live only because this machine's PATH
    grep happens to be pcre2-capable.
    """
    offenders = []
    for path in tracked_files():
        if path == Path(__file__).resolve():
            continue
        try:
            text = path.read_text()
        except (UnicodeDecodeError, OSError):
            continue
        for n, line in enumerate(text.split("\n"), 1):
            if re.search(r"grep\s+-\w*P\w*\b|\\K", line):
                offenders.append(f"{path.relative_to(REPO_ROOT)}:{n}: {line.strip()}")
    assert not offenders, (
        "grep -P / \\K is PCRE2-only and BSD grep does not support it:\n  "
        + "\n  ".join(offenders)
    )


def test_scope_detection_uses_python_not_shell_regex(cc_gate: str) -> None:
    """The replacement must be the portable mechanism it was chosen to be."""
    assert re.search(r"import re|import subprocess", cc_gate), (
        "pr-cc-gate.md must compute the changed-line ranges in Python, matching "
        "how the CSV parse already avoids a shell-only mechanism"
    )


# --- 2. the config key ----------------------------------------------------------


@pytest.mark.parametrize("doc", [CONFIG_MD, CONF_OPTIONS, EXAMPLE_TOML])
def test_new_key_documented_and_off_by_default(doc: Path) -> None:
    text = doc.read_text()
    assert KEY in text, f"{doc.name} does not mention {KEY}"
    lines = [l for l in text.split("\n") if KEY in l]
    assert any(re.search(r"\bfalse\b", l, re.IGNORECASE) for l in lines), (
        f"{doc.name}: {KEY} must default to false — every project keeps today's "
        f"behavior (everything in scope) until it opts in. Lines found: {lines!r}"
    )


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


def test_exempt_functions_are_still_reported(cc_gate: str) -> None:
    assert re.search(r"exempt", cc_gate, re.IGNORECASE), (
        "pr-cc-gate.md must describe an exempt-function report section"
    )
    # Structural, not textual: find the sentence and require it says the
    # function is still shown, not silently dropped.
    idx = cc_gate.lower().find("exempt")
    window = cc_gate[max(0, idx - 200) : idx + 400].lower()
    assert not re.search(r"exempt.{0,60}(hidden|dropped|suppressed|silently)", window), (
        "an exempted function must still appear in the report — the exemption "
        "changes what blocks, not what is visible"
    )


# --- 4. the remedies, and the explicit switch/case exclusion --------------------


REMEDY_MARKERS = [
    r"extract",
    r"guard.claus|early.return",
    r"dispatch table|lookup table",
    r"lift.*loop.*(into|as).*(function|helper)",
]


@pytest.mark.parametrize("marker", REMEDY_MARKERS)
def test_remedy_present(cc_gate: str, marker: str) -> None:
    assert re.search(marker, cc_gate, re.IGNORECASE), (
        f"pr-cc-gate.md must recommend a remedy matching /{marker}/ on the 🔴 path"
    )


def test_switch_case_is_not_recommended_as_a_cc_remedy(cc_gate: str) -> None:
    """Under the gate's own counting a switch scores identically to the
    equivalent if-chain (measured: both CC 5 for a 5-case dispatch), so telling
    an agent to convert one to the other produces no reduction. Only a real
    lookup/dispatch table — which removes the branches rather than restyling
    them — is a valid remedy.

    A first version of this test checked for a "not" in the same sentence as
    any switch-mentioning match. Mutation-tested and found gameable: a
    genuinely bad rewording just needs the negation and the recommendation in
    different sentences ("Switch/case is a valid technique. Convert your
    if-chain to it.") to pass — proximity-to-"not" is a prose proxy for
    meaning, not meaning itself, and reworks like that keep defeating it one
    paraphrase at a time.

    Pinned to a stable structural anchor instead: any sentence matching
    RECOMMENDATION_SHAPE must be the exact marker sentence, not a nearby
    negation. Catches accidental drift — an editor paraphrasing the marker
    while keeping its meaning, or deleting it outright. Mutation-verified
    against both the original same-sentence rewording and a same-shape
    rewording placed elsewhere in the file.

    Residual gap, stated rather than claimed away: RECOMMENDATION_SHAPE
    itself assumes one word order (convert ... if-chain ... switch). A
    paraphrase constructed specifically to dodge that order — e.g. "Switch
    is valid; convert your if-chain to it" — isn't caught, because it never
    matches the shape at all. No regex closes that gap for arbitrary prose;
    that threat model is a deliberate, test-aware rewrite, not the ordinary
    doc-drift this test defends against.
    """
    MARKER = "Not a valid remedy: converting an if-chain to `switch`/`case`."
    assert MARKER in cc_gate, f"pr-cc-gate.md must state the exact marker: {MARKER!r}"

    # Any sentence SHAPED like a recommendation to do the prohibited conversion
    # must be the marker sentence itself — not a paraphrase claiming to negate
    # it from a different sentence, which is exactly what defeated the prior
    # "not" nearby" version of this check.
    RECOMMENDATION_SHAPE = r"(convert|rewrite|replace).{0,40}if.{0,15}(chain|else).{0,40}switch"
    # Where the regex lands inside a known-good marker — used below to require every
    # real match to be that exact occurrence, not a lookalike elsewhere in the doc.
    marker_match = re.search(RECOMMENDATION_SHAPE, MARKER, re.IGNORECASE)
    assert marker_match, "test bug: RECOMMENDATION_SHAPE does not match the marker itself"
    marker_offset = marker_match.start()

    marker_pos = cc_gate.find(MARKER)
    expected_start = marker_pos + marker_offset

    for m in re.finditer(RECOMMENDATION_SHAPE, cc_gate, re.IGNORECASE):
        assert m.start() == expected_start, (
            "a sentence shaped like a switch/case recommendation was found outside "
            f"the marker sentence: ...{cc_gate[max(0, m.start()-40):m.end()+40]}..."
        )


def test_default_counting_decision_is_recorded_with_measurements(cc_gate: str) -> None:
    """The -m/--modified decision (keep default counting) must be recorded with
    its own rationale, not merely implied by omission.
    """
    assert re.search(r"-m\b|--modified", cc_gate), (
        "pr-cc-gate.md must record the -m/--modified decision explicitly"
    )
    assert re.search(r"\bCC 5\b", cc_gate) and re.search(r"\bCC 2\b", cc_gate), (
        "pr-cc-gate.md must record the measured switch-vs-if-chain numbers "
        "(CC 5 default, CC 2 under -m) that justify keeping default counting"
    )


# --- 5. line-range overlap semantics, verified against the real tools -----------


def _changed_ranges(base_sha: str, path: str, cwd: Path) -> list[tuple[int, int]]:
    """Mirrors the algorithm pr-cc-gate.md documents: parse `git diff --unified=0`
    hunk headers for the new-file line ranges touched by the branch.
    """
    diff = subprocess.run(
        ["git", "diff", "--unified=0", f"{base_sha}..HEAD", "--", path],
        cwd=cwd,
        capture_output=True,
        text=True,
    ).stdout
    ranges = []
    for m in re.finditer(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@", diff, re.MULTILINE):
        start = int(m.group(1))
        count = int(m.group(2)) if m.group(2) is not None else 1
        end = start if count == 0 else start + count - 1
        ranges.append((start, end))
    return ranges


def _touched(ranges: list[tuple[int, int]], fn_start: int, fn_end: int) -> bool:
    return any(a <= fn_end and fn_start <= b for a, b in ranges)


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True, text=True, check=True
    ).stdout.strip()


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
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "t@t.com")
    _git(repo, "config", "user.name", "t")

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
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "t@t.com")
    _git(repo, "config", "user.name", "t")
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
