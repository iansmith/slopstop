"""
Phase 0 red tests for BILL-351 — a Stop hook that meters token usage, with
Desktop install support.

Transcribed from the ticket's Test expectations
(https://github.com/iansmith/slopstop/issues/351). Transcription, not
authorship: every assertion and every expected value below is pinned by the
ticket, and per the fleet brief's hard constraint 9 the implementer may not
renegotiate them. If one is wrong, the sanctioned exit is the TICKET
UNDERSPECIFIED halt (TD-4a), not an edit to this file.

Oracle for token values (per the ticket): the fixture transcript's single
assistant message carries usage = {input_tokens: 100, output_tokens: 20,
cache_creation_input_tokens: 5, cache_read_input_tokens: 7} — the expected
sums are exactly those four numbers.

Threshold contract for the all-zero window (per the ticket, do not change):
warn only when the window holds >= 10 rows and the non-zero rate over the
most recent 50 rows is exactly 0.

Test command:
    python3 -m pytest tests/test_bill351_behaviors.py -v
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent
HOOK = REPO_ROOT / "hooks" / "cost-tracker.py"
PLUGIN_MANIFEST = REPO_ROOT / ".claude-plugin" / "plugin.json"
INSTALLER = REPO_ROOT / "install-for-claude-desktop.sh"
BASELINE_DIR = REPO_ROOT / "baseline"
SPEC_SHA256 = "722373b0dc8a8ca3293dcb1d77f454c93fc02864d3d40be49eb214b51a46ffa4"

USAGE = {
    "input_tokens": 100,
    "output_tokens": 20,
    "cache_creation_input_tokens": 5,
    "cache_read_input_tokens": 7,
}
ZERO_USAGE = {
    "input_tokens": 0,
    "output_tokens": 0,
    "cache_creation_input_tokens": 0,
    "cache_read_input_tokens": 0,
}
ROW_KEYS = {
    "session_id",
    "ts",
    "cwd",
    "model",
    "input_tokens",
    "output_tokens",
    "cache_creation_input_tokens",
    "cache_read_input_tokens",
}


def _write_transcript(path, usage):
    entry = {
        "type": "assistant",
        "message": {
            "role": "assistant",
            "model": "claude-sonnet-5",
            "usage": usage,
        },
    }
    path.write_text(json.dumps(entry) + "\n")


def _run_hook(payload, cwd):
    return subprocess.run(
        [sys.executable, str(HOOK)],
        input=json.dumps(payload),
        cwd=str(cwd),
        capture_output=True,
        text=True,
    )


def _costs_path(cwd):
    return Path(cwd) / ".slopstop" / "metrics" / "costs.jsonl"


def _lines(path):
    if not path.exists():
        return []
    return [json.loads(l) for l in path.read_text().splitlines() if l.strip()]


@pytest.fixture
def workdir(tmp_path):
    d = tmp_path / "work"
    d.mkdir()
    return d


@pytest.fixture
def nonzero_transcript(workdir):
    t = workdir / "transcript.jsonl"
    _write_transcript(t, USAGE)
    return t


@pytest.fixture
def zero_transcript(workdir):
    t = workdir / "zero_transcript.jsonl"
    _write_transcript(t, ZERO_USAGE)
    return t


def _payload(cwd, transcript_path, session_id="sess-1"):
    return {
        "session_id": session_id,
        "transcript_path": str(transcript_path),
        "cwd": str(cwd),
        "hook_event_name": "Stop",
    }


class TestHookAppendsRows:
    def test_hook_appends_one_row_per_invocation(self, workdir, nonzero_transcript):
        payload = _payload(workdir, nonzero_transcript)
        r1 = _run_hook(payload, workdir)
        assert r1.returncode == 0
        r2 = _run_hook(payload, workdir)
        assert r2.returncode == 0

        lines = _lines(_costs_path(workdir))
        assert len(lines) == 2

    def test_row_schema_exact_keys(self, workdir, nonzero_transcript):
        payload = _payload(workdir, nonzero_transcript)
        r = _run_hook(payload, workdir)
        assert r.returncode == 0

        lines = _lines(_costs_path(workdir))
        assert len(lines) == 1
        assert set(lines[0].keys()) == ROW_KEYS
        assert lines[0]["input_tokens"] == 100
        assert lines[0]["output_tokens"] == 20
        assert lines[0]["cache_creation_input_tokens"] == 5
        assert lines[0]["cache_read_input_tokens"] == 7


class TestHookNeverBlocks:
    def test_hook_exits_zero_on_malformed_stdin(self, workdir):
        r = subprocess.run(
            [sys.executable, str(HOOK)],
            input="not json",
            cwd=str(workdir),
            capture_output=True,
            text=True,
        )
        assert r.returncode == 0
        assert not _costs_path(workdir).exists()

    def test_hook_exits_zero_on_missing_transcript(self, workdir):
        payload = _payload(workdir, workdir / "does-not-exist.jsonl")
        r = _run_hook(payload, workdir)
        assert r.returncode == 0


class TestAllZeroWindow:
    def _seed_zero_rows(self, costs_path, n):
        costs_path.parent.mkdir(parents=True, exist_ok=True)
        rows = [
            {
                "session_id": f"seed-{i}",
                "ts": "2026-07-30T00:00:00Z",
                "cwd": str(costs_path.parent.parent.parent),
                "model": "claude-sonnet-5",
                **ZERO_USAGE,
            }
            for i in range(n)
        ]
        with open(costs_path, "w") as f:
            for row in rows:
                f.write(json.dumps(row) + "\n")

    def test_all_zero_window_warns_and_suppresses_zero_row(
        self, workdir, zero_transcript
    ):
        costs_path = _costs_path(workdir)
        self._seed_zero_rows(costs_path, 50)

        payload = _payload(workdir, zero_transcript)
        r = _run_hook(payload, workdir)

        assert r.returncode == 0
        assert "all-zero token rate" in r.stderr
        assert len(_lines(costs_path)) == 50

    def test_nonzero_row_appends_after_all_zero_window(
        self, workdir, nonzero_transcript
    ):
        costs_path = _costs_path(workdir)
        self._seed_zero_rows(costs_path, 50)

        payload = _payload(workdir, nonzero_transcript)
        r = _run_hook(payload, workdir)

        assert r.returncode == 0
        lines = _lines(costs_path)
        assert len(lines) == 51
        appended = lines[-1]
        assert appended["input_tokens"] == 100
        assert appended["output_tokens"] == 20
        assert appended["cache_creation_input_tokens"] == 5
        assert appended["cache_read_input_tokens"] == 7

        # Anti-latch: the meter must not still think it's in an all-zero
        # window now that a non-zero row has landed.
        r2 = _run_hook(_payload(workdir, nonzero_transcript, session_id="sess-2"), workdir)
        assert r2.returncode == 0
        assert "all-zero token rate" not in r2.stderr

    def test_short_history_does_not_warn(self, workdir, zero_transcript):
        costs_path = _costs_path(workdir)
        self._seed_zero_rows(costs_path, 9)

        payload = _payload(workdir, zero_transcript)
        r = _run_hook(payload, workdir)

        assert r.returncode == 0
        assert "all-zero token rate" not in r.stderr


class TestTranscriptResolvesRelativeToPayloadCwd:
    def test_hook_resolves_transcript_relative_to_payload_cwd(self, tmp_path):
        payload_cwd = tmp_path / "payload-cwd"
        process_cwd = tmp_path / "process-cwd"
        payload_cwd.mkdir()
        process_cwd.mkdir()

        transcript = payload_cwd / "relative-transcript.jsonl"
        _write_transcript(transcript, USAGE)

        payload = {
            "session_id": "sess-relative",
            "transcript_path": "relative-transcript.jsonl",
            "cwd": str(payload_cwd),
            "hook_event_name": "Stop",
        }

        r = subprocess.run(
            [sys.executable, str(HOOK)],
            input=json.dumps(payload),
            cwd=str(process_cwd),
            capture_output=True,
            text=True,
        )
        assert r.returncode == 0

        assert not _costs_path(process_cwd).exists()
        lines = _lines(_costs_path(payload_cwd))
        assert len(lines) == 1
        assert lines[0]["input_tokens"] == 100
        assert lines[0]["output_tokens"] == 20
        assert lines[0]["cache_creation_input_tokens"] == 5
        assert lines[0]["cache_read_input_tokens"] == 7


class TestPluginManifest:
    def test_plugin_manifest_declares_hooks(self):
        manifest = json.loads(PLUGIN_MANIFEST.read_text())
        assert "hooks" in manifest


class TestInstaller:
    def _run_installer(self, home):
        env = {"HOME": str(home), "PATH": "/usr/bin:/bin:/usr/local/bin"}
        return subprocess.run(
            ["bash", str(INSTALLER), "--merge-hook-only"],
            env=env,
            capture_output=True,
            text=True,
        )

    def test_installer_merge_is_idempotent(self, tmp_path):
        home = tmp_path / "home"
        home.mkdir()
        settings_dir = home / ".claude"
        settings_dir.mkdir()
        settings_path = settings_dir / "settings.json"
        unrelated = {"hooks": {"PreToolUse": [{"hooks": [{"type": "command", "command": "echo unrelated"}]}]}}
        settings_path.write_text(json.dumps(unrelated, indent=2) + "\n")

        r1 = self._run_installer(home)
        assert r1.returncode == 0
        after_first = settings_path.read_text()

        r2 = self._run_installer(home)
        assert r2.returncode == 0
        after_second = settings_path.read_text()

        assert after_first == after_second

        merged = json.loads(after_second)
        assert merged["hooks"]["PreToolUse"][0]["hooks"][0]["command"] == "echo unrelated"
        stop_commands = [
            h.get("command")
            for group in merged["hooks"].get("Stop", [])
            for h in group.get("hooks", [])
        ]
        assert any("cost-tracker.py" in c for c in stop_commands if c)

    def test_installer_prints_what_it_wrote(self, tmp_path):
        home = tmp_path / "home"
        home.mkdir()

        r1 = self._run_installer(home)
        assert r1.returncode == 0
        assert str(home / ".claude" / "settings.json") in r1.stdout
        assert "cost-tracker.py" in r1.stdout
        assert "WROTE" in r1.stdout

        r2 = self._run_installer(home)
        assert r2.returncode == 0
        assert "NOOP" in r2.stdout


class TestBaseline:
    def test_baseline_dir_tracked_and_complete(self):
        assert BASELINE_DIR.is_dir(), "baseline/ must exist"
        for name in (
            "sessions.json",
            "analyze.py",
            "report.py",
            "deep.py",
            "cost-time-audit-2026-07-30.md",
            "README.md",
        ):
            assert (BASELINE_DIR / name).is_file(), f"baseline/{name} missing"

        result = subprocess.run(
            ["git", "check-ignore", "-q", "baseline/"],
            cwd=str(REPO_ROOT),
            capture_output=True,
        )
        assert result.returncode != 0, "baseline/ must not be gitignored"

    def test_baseline_spec_hash_intact(self):
        import hashlib

        spec = BASELINE_DIR / "cost-time-audit-2026-07-30.md"
        assert spec.is_file(), "baseline/cost-time-audit-2026-07-30.md missing"
        digest = hashlib.sha256(spec.read_bytes()).hexdigest()
        assert digest == SPEC_SHA256

    def test_baseline_rollup_parses(self):
        rollup = BASELINE_DIR / "sessions.json"
        assert rollup.is_file(), "baseline/sessions.json missing"
        data = json.loads(rollup.read_text())
        assert data
