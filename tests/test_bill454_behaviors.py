"""
Phase 0 red tests for BILL-454 — Collector skeleton, wave 2: stub modules and
record keys for spans, spawns, active, version.

Transcribed from the ticket's Test expectations
(https://github.com/iansmith/slopstop/issues/454). Transcription, not authorship:
every assertion and every expected value below is pinned by the ticket. If one is
wrong, the sanctioned exit is the TICKET UNDERSPECIFIED halt (TD-4a), not an edit
to this file.

Mirrors tests/test_bill382_behaviors.py, which is the same ticket shape one wave
earlier — same `run_collect` helper, same live-subprocess posture. Those calls do
reach the GitHub API; that is the established pattern here, not a new cost.

Note on redness: the file-existence assertion precedes every import below. Without
it these tests would fail with ImportError — failing *before* reaching an
assertion, which TD-3 step 2 does not accept as red. Asserting the path first
means each test reaches its assertion and fails on real state.

Test command:
    python3 -m pytest tests/test_bill454_behaviors.py -v
"""

import importlib.util
import inspect
import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent
METRICS = REPO_ROOT / "tools" / "metrics"
COLLECT = METRICS / "collect.py"

# The four blocks this ticket wires. Each is filled in by its own downstream
# ticket: spans #406, spawns #445, active #452, version #453.
NEW_MODULES = ("spans", "spawns", "active", "version")

EXISTING_KEYS = {
    "schema",
    "ticket",
    "system",
    "repo",
    "generated_at",
    "timing",
    "tokens",
    "phases",
    "signals",
}
SCHEMA_KEYS = EXISTING_KEYS | set(NEW_MODULES)

EXPECTED_SCHEMA = "slopstop.derived-metrics/2"
TICKET = "BILL-433"


def run_collect(args, cwd=None):
    return subprocess.run(
        [sys.executable, str(COLLECT)] + args,
        cwd=cwd or REPO_ROOT,
        capture_output=True,
        text=True,
    )


def _load(name):
    """Import a metrics module by path, asserting the file exists first."""
    path = METRICS / f"{name}.py"
    assert path.is_file(), f"missing {path.relative_to(REPO_ROOT)}"
    spec = importlib.util.spec_from_file_location(f"_bill454_{name}", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def collected():
    result = run_collect([TICKET])
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_four_new_keys_present_and_null(collected):
    """Ticket expectation 1: present and null — not absent, not {}.

    Absence is the failure that matters: it would let a downstream ticket add
    the key itself, which is exactly the collect.py collision this skeleton
    exists to prevent.
    """
    for name in NEW_MODULES:
        assert name in collected, f"record is missing the {name!r} key"
        assert collected[name] is None, (
            f"{name!r} must be null in the skeleton — filling it in belongs to "
            f"its own ticket; got {collected[name]!r}"
        )


def test_record_carries_exactly_the_expected_keys(collected):
    """The existing blocks keep their names and positions alongside the new ones."""
    assert set(collected.keys()) == SCHEMA_KEYS


def test_schema_is_version_two(collected):
    """Ticket expectation 2: the literal contract value."""
    assert collected["schema"] == EXPECTED_SCHEMA


@pytest.mark.parametrize("name", NEW_MODULES)
def test_each_module_exposes_collect_record_ctx(name):
    """Ticket expectation 3: `collect(record, ctx)` and no other public entry point."""
    module = _load(name)
    assert hasattr(module, "collect"), f"{name}.py defines no collect()"
    params = list(inspect.signature(module.collect).parameters)
    assert params == ["record", "ctx"], (
        f"{name}.collect must take exactly (record, ctx); got {params}"
    )
    public = [
        n
        for n in vars(module)
        if not n.startswith("_") and callable(getattr(module, n)) and n != "collect"
    ]
    assert public == [], f"{name}.py exposes extra public callables: {public}"


@pytest.mark.parametrize("name", NEW_MODULES)
def test_each_stub_touches_only_its_own_key(name):
    """Ticket expectation 4: inert against a record populated with sentinels.

    Guards the mutation an adversary would reach for first: a stub that clears
    the whole record, or writes a neighbour's key, still satisfies "my key is
    None" while destroying everything else.
    """
    module = _load(name)
    record = {k: f"SENTINEL::{k}" for k in SCHEMA_KEYS}
    module.collect(record, {})

    assert record[name] is None, f"{name}.collect must set its own key to None"
    for other in SCHEMA_KEYS - {name}:
        assert record[other] == f"SENTINEL::{other}", (
            f"{name}.collect modified {other!r}, which it does not own"
        )


def test_ctx_carries_slopstop_root():
    """Ticket expectation 5: resolves to a dir containing .claude-plugin/plugin.json.

    Captured from the ctx the real wiring passes to a collector, rather than from
    a helper that could drift from it — #453 reads tag history for a *consumer*
    repo whose project_root is a different repository, so this entry is the only
    way it can find slopstop at all.
    """
    sys.path.insert(0, str(METRICS))
    import collect as collect_mod

    assert hasattr(collect_mod, "version"), (
        "collect.py does not import the version module — without this the capture "
        "below raises AttributeError and never reaches its assertion, which TD-3 "
        "does not accept as red"
    )

    captured = {}
    original = collect_mod.version.collect

    def capture(record, ctx):
        captured.update(ctx)
        return original(record, ctx)

    collect_mod.version.collect = capture
    try:
        assert collect_mod.main([TICKET]) == 0
    finally:
        collect_mod.version.collect = original

    assert "slopstop_root" in captured, "ctx has no slopstop_root entry"
    root = Path(captured["slopstop_root"])
    assert (root / ".claude-plugin" / "plugin.json").is_file(), (
        f"slopstop_root {root} does not contain .claude-plugin/plugin.json"
    )


def test_collect_py_actually_calls_all_four_collectors():
    """Added by the Step 0f adversary pass — the frozen suite had a hole here.

    Mutation that survived every other test: set the four keys directly in
    collect.py's record literal and never call spans/spawns/active at all. The
    modules would exist with correct signatures (their own tests pass in
    isolation), the record would carry four nulls, and the schema would be /2 —
    all green, with three of the four collectors dead code.

    `test_ctx_carries_slopstop_root` catches this for `version` only, and only
    incidentally: it monkeypatches through `version.collect`, so an uncalled
    `version` leaves `captured` empty. Nothing covered the other three. Wiring
    them in is the entire point of this ticket, so it is worth an explicit test.
    """
    sys.path.insert(0, str(METRICS))
    import collect as collect_mod

    called = []
    originals = {}
    for name in NEW_MODULES:
        assert hasattr(collect_mod, name), f"collect.py does not import {name}"
        module = getattr(collect_mod, name)
        originals[name] = module.collect

        def make(n, original):
            def wrapper(record, ctx):
                called.append(n)
                return original(record, ctx)

            return wrapper

        module.collect = make(name, originals[name])

    try:
        assert collect_mod.main([TICKET]) == 0
    finally:
        for name, original in originals.items():
            getattr(collect_mod, name).collect = original

    assert sorted(called) == sorted(NEW_MODULES), (
        f"collect.py did not call every new collector; called {sorted(called)}, "
        f"expected {sorted(NEW_MODULES)}"
    )


def test_entrypoint_exercised_out_of_root():
    """Mandated by the ticket standard: subprocess, non-root cwd, relative path.

    collect.py already carries a comment explaining that cwd cannot stand in for
    the project root. Nothing ran that shape against the new keys; this does.
    """
    result = subprocess.run(
        [
            sys.executable,
            str(COLLECT.resolve()),
            TICKET,
            "--conf",
            "../.project-conf.toml",
        ],
        cwd=str(REPO_ROOT / "tests"),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    record = json.loads(result.stdout)
    assert set(record.keys()) == SCHEMA_KEYS
    assert record["schema"] == EXPECTED_SCHEMA
    assert record["ticket"] == TICKET
