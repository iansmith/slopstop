"""Behavior tests for BILL-433 — five dead config keys become a load failure.

Each key governed machinery that no longer exists, and three of them never worked
even when it did:

  [pr_review] fix            gated a --fix loop on `git status --porcelain` being
                             non-empty after a review that only ever posted a
                             comment. It could not fire at either value, in any
                             project — yet three of the nine fleet repos set it to
                             true and believed fixes were being applied.
  [pr_review] coderabbit_fix existed to make a presentation-only run possible, which
  [pr_review] greptile_fix   is precisely how a confirmed 🔴 finding stays unfixed.
  [autonomous] on_red_findings  specified entirely as "only consulted when
                             [pr_review] fix = false" — a condition that cannot
                             exist once `fix` is gone.
  [autonomous] on_simplify_changes  named Step 1, deleted in BILL-436.

Accepting a key that has never had an effect is worse than rejecting it: silence
reads as "this is working". So presence is a hard load failure, not a warning.

Where the failure lives: `tools/metrics/conventions.load()`, which its own module
docstring calls "the single home for convention reads (charter R4)". It is the only
code path that reads .project-conf.toml. The skills read it as prose, so a skill
cannot enforce anything — recorded here because it is the honest limit of this
ticket: a project that never runs the metrics tooling gets no error, only the audit.

Per this repo's rule, no test here asserts what markdown says. These are TOML facts,
a real exception from a real loader, and the audit's actual output.

Test command:
    python3 -m pytest tests/test_bill433_behaviors.py -v
"""

import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

from conftest import REPO_ROOT

sys.path.insert(0, str(REPO_ROOT / "tools" / "metrics"))
import conventions  # noqa: E402

AUDIT = REPO_ROOT / "tools" / "fleet-sync" / "audit-project-conf.py"
OWN_CONF = REPO_ROOT / ".project-conf.toml"
EXAMPLE = REPO_ROOT / ".project-conf.toml.example"

# table -> key
DEAD_KEYS = [
    ("pr_review", "fix"),
    ("pr_review", "coderabbit_fix"),
    ("pr_review", "greptile_fix"),
    ("autonomous", "on_red_findings"),
    ("autonomous", "on_simplify_changes"),
]

MINIMAL = 'system = "github"\nkey = "o/r"\nprefix = "X"\n'


def _conf(tmp_path, extra=""):
    p = tmp_path / ".project-conf.toml"
    p.write_text(MINIMAL + extra)
    return p


@pytest.mark.parametrize("table,key", DEAD_KEYS)
def test_dead_key_makes_the_config_fail_to_load(tmp_path, table, key):
    """A config carrying a removed key raises, and the error names the key.

    RED at Phase 0: conventions.load() ignores unknown keys entirely.

    Naming the key is the whole value. "Invalid config" sends a maintainer to
    read the file; "[pr_review] fix was removed in BILL-433" sends them to the
    one line they must delete.
    """
    value = "false" if key.endswith("fix") else '"ask"'
    conf = _conf(tmp_path, f"\n[{table}]\n{key} = {value}\n")

    with pytest.raises(Exception) as exc:
        conventions.load(conf)
    msg = str(exc.value)
    assert key in msg, f"the error must name the offending key {key!r}; got: {msg}"
    assert table in msg, f"the error must name the table [{table}]; got: {msg}"


@pytest.mark.parametrize("table,key", DEAD_KEYS)
def test_this_repo_carries_none_of_them(table, key):
    """slopstop's own config and its example must load under the new rules.

    RED at Phase 0: .project-conf.toml sets fix, on_red_findings and
    on_simplify_changes; the example documents all five.

    Shipping a repo that cannot load its own config would be a self-inflicted
    outage, and the example is what every new project copies from.
    """
    for path in (OWN_CONF, EXAMPLE):
        data = tomllib.loads(path.read_text())
        assert key not in data.get(table, {}), (
            f"{path.name} still sets [{table}] {key} — removed in BILL-433"
        )


@pytest.mark.parametrize("table,key", DEAD_KEYS)
def test_the_fleet_audit_reports_each_dead_key(tmp_path, table, key):
    """The audit is how the other eight repos find out.

    RED at Phase 0: audit-project-conf.py checks [pr_review] fix as a
    consistency item, and knows nothing of the other four.

    slopstop must never edit another project's .project-conf.toml (universal §5),
    so the audit reporting is the entire delivery mechanism for this change.
    """
    value = "false" if key.endswith("fix") else '"ask"'
    conf = _conf(tmp_path, f"\n[{table}]\n{key} = {value}\n")

    out = subprocess.run(
        [sys.executable, str(AUDIT), "--conf", str(conf)],
        capture_output=True, text=True, cwd=tmp_path,
    )
    combined = out.stdout + out.stderr
    assert key in combined, (
        f"the audit must report the removed key {key!r}. Output was:\n{combined}"
    )


def test_a_clean_config_still_loads(tmp_path):
    """The rejection must not become "reject everything".

    Without this, a loader that raised unconditionally would pass every case
    above — the same false-positive shape that makes a detector useless.
    """
    c = conventions.load(_conf(tmp_path))
    assert (c.system, c.repo, c.prefix) == ("github", "o/r", "X")
