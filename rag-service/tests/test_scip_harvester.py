"""Unit tests for the SCIP code-graph harvester (BILL-121).

Layer-1 — no subprocess, no HTTP, no filesystem writes outside tmp_path.
Exercises detect_languages, check_preflight, and build_ingest_payload directly.
"""

from pathlib import Path
from unittest.mock import patch

import pytest

from rag_service.harvesters.scip import (
    PreflightError,
    build_ingest_payload,
    check_preflight,
    detect_languages,
)


# ---------------------------------------------------------------------------
# detect_languages
# ---------------------------------------------------------------------------


def test_detect_languages_empty_dir(tmp_path):
    assert detect_languages(tmp_path, skip=[]) == []


def test_detect_languages_python_only(tmp_path):
    (tmp_path / "main.py").write_text("x = 1")
    (tmp_path / "utils.py").write_text("pass")
    result = detect_languages(tmp_path, skip=[])
    assert result == ["python"]


def test_detect_languages_go_only(tmp_path):
    (tmp_path / "main.go").write_text("package main")
    result = detect_languages(tmp_path, skip=[])
    assert result == ["go"]


def test_detect_languages_typescript(tmp_path):
    (tmp_path / "index.ts").write_text("export {}")
    result = detect_languages(tmp_path, skip=[])
    assert result == ["typescript"]


def test_detect_languages_tsx_counts_as_typescript(tmp_path):
    (tmp_path / "App.tsx").write_text("export default () => null")
    result = detect_languages(tmp_path, skip=[])
    assert result == ["typescript"]


def test_detect_languages_multi(tmp_path):
    (tmp_path / "main.go").write_text("package main")
    (tmp_path / "script.py").write_text("pass")
    result = detect_languages(tmp_path, skip=[])
    assert set(result) == {"go", "python"}


def test_detect_languages_skips_vendor(tmp_path):
    vendor = tmp_path / "vendor"
    vendor.mkdir()
    (vendor / "dep.go").write_text("package dep")
    # only a non-vendor file triggers go detection
    result = detect_languages(tmp_path, skip=[])
    assert result == []


def test_detect_languages_skips_git(tmp_path):
    git_dir = tmp_path / ".git"
    git_dir.mkdir()
    (git_dir / "hook.py").write_text("pass")
    result = detect_languages(tmp_path, skip=[])
    assert result == []


def test_detect_languages_skips_node_modules(tmp_path):
    nm = tmp_path / "node_modules"
    nm.mkdir()
    (nm / "dep.ts").write_text("export {}")
    result = detect_languages(tmp_path, skip=[])
    assert result == []


def test_detect_languages_skips_pycache(tmp_path):
    cache = tmp_path / "__pycache__"
    cache.mkdir()
    (cache / "mod.cpython-311.pyc").write_bytes(b"\x00" * 4)
    # .pyc not in the extension map, but __pycache__ should be skipped regardless
    result = detect_languages(tmp_path, skip=[])
    assert result == []


def test_detect_languages_config_skip_patterns(tmp_path):
    """Files matching project-conf skip patterns are excluded from detection."""
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_foo.py").write_text("pass")
    # with skip=["tests/"], the tests/ dir should not count
    result = detect_languages(tmp_path, skip=["tests/"])
    assert result == []


def test_detect_languages_config_skip_does_not_affect_other_dirs(tmp_path):
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_foo.py").write_text("pass")
    src = tmp_path / "src"
    src.mkdir()
    (src / "main.py").write_text("pass")
    result = detect_languages(tmp_path, skip=["tests/"])
    assert result == ["python"]


def test_detect_languages_unknown_extensions_ignored(tmp_path):
    (tmp_path / "README.md").write_text("# hello")
    (tmp_path / "data.json").write_text("{}")
    result = detect_languages(tmp_path, skip=[])
    assert result == []


# ---------------------------------------------------------------------------
# check_preflight
# ---------------------------------------------------------------------------


def _which_all_present(name):
    """Fake shutil.which that always finds the tool."""
    return f"/usr/local/bin/{name}"


def _which_missing(missing_name):
    """Return a shutil.which fake that pretends one tool is absent."""
    def fake_which(name):
        if name == missing_name:
            return None
        return f"/usr/local/bin/{name}"
    return fake_which


def test_preflight_all_present_python(tmp_path):
    with patch("shutil.which", side_effect=_which_all_present):
        check_preflight(["python"])  # must not raise


def test_preflight_all_present_go(tmp_path):
    with patch("shutil.which", side_effect=_which_all_present):
        check_preflight(["go"])  # must not raise


def test_preflight_missing_scip_python_raises(tmp_path):
    with patch("shutil.which", side_effect=_which_missing("scip-python")):
        with pytest.raises(PreflightError) as exc_info:
            check_preflight(["python"])
    assert "pip install scip-python" in str(exc_info.value)


def test_preflight_missing_scip_cli_raises(tmp_path):
    with patch("shutil.which", side_effect=_which_missing("scip")):
        with pytest.raises(PreflightError) as exc_info:
            check_preflight(["python"])
    assert "scip" in str(exc_info.value)


def test_preflight_missing_scip_go_raises(tmp_path):
    with patch("shutil.which", side_effect=_which_missing("scip-go")):
        with pytest.raises(PreflightError) as exc_info:
            check_preflight(["go"])
    assert "scip-go" in str(exc_info.value)


def test_preflight_python_does_not_require_scip_go(tmp_path):
    """A python-only repo should not fail if scip-go is absent."""
    with patch("shutil.which", side_effect=_which_missing("scip-go")):
        check_preflight(["python"])  # must not raise


def test_preflight_go_does_not_require_scip_python(tmp_path):
    """A go-only repo should not fail if scip-python is absent."""
    with patch("shutil.which", side_effect=_which_missing("scip-python")):
        check_preflight(["go"])  # must not raise


def test_preflight_error_message_includes_install_command():
    """Error message must give a copy-pasteable install command."""
    with patch("shutil.which", side_effect=_which_missing("scip-typescript")):
        with pytest.raises(PreflightError) as exc_info:
            check_preflight(["typescript"])
    msg = str(exc_info.value)
    assert "npm install" in msg or "npx" in msg


# ---------------------------------------------------------------------------
# build_ingest_payload
# ---------------------------------------------------------------------------

_MINIMAL_INDEX = {
    "metadata": {"tool_info": {"name": "scip-python", "version": "0.5.0"}},
    "documents": [],
    "external_symbols": [],
}


def test_build_ingest_payload_shape():
    payload = build_ingest_payload(
        index=_MINIMAL_INDEX,
        repo="iansmith/slopstop",
        head_sha="abc123",
        source_root="/home/dev/slopstop",
    )
    assert payload["repo"] == "iansmith/slopstop"
    assert payload["index"] is _MINIMAL_INDEX
    assert payload["head_sha"] == "abc123"
    assert payload["source_root"] == "/home/dev/slopstop"


def test_build_ingest_payload_none_head_sha():
    payload = build_ingest_payload(
        index=_MINIMAL_INDEX,
        repo="iansmith/slopstop",
        head_sha=None,
        source_root="/home/dev/slopstop",
    )
    # head_sha=None must not be omitted silently — either key absent or value is None
    assert payload.get("head_sha") is None or "head_sha" not in payload


def test_build_ingest_payload_passes_index_unchanged():
    """The payload must not copy or transform the index dict."""
    index = dict(_MINIMAL_INDEX)
    payload = build_ingest_payload(index=index, repo="r", head_sha="sha", source_root="/s")
    assert payload["index"] is index
