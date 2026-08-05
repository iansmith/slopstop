"""`.project-conf.toml` decoding -- the single home for convention reads (charter R4).

No other module in this package reads `.project-conf.toml` directly; everything
that needs `system`, `repo`, `prefix`, or a status label goes through `load()`.
"""

import pathlib
import tomllib

# Keys removed by BILL-433. Each governed machinery that no longer exists, and three
# never worked even when it did: `fix` gated a loop on a working-tree change that a
# comment-only reviewer could never produce, and the two `*_fix` keys existed to make
# a presentation-only run possible -- which is how a confirmed 🔴 finding stays
# unfixed. `on_red_findings` was specified as "only consulted when fix = false", a
# condition that cannot exist once `fix` is gone; `on_simplify_changes` named a step
# deleted in BILL-436.
#
# Rejected rather than ignored, deliberately. Three of the nine fleet repos set
# `fix = true` and believed fixes were being applied for months. Silently accepting a
# key that has never had an effect reads as "this is working" -- the failure mode is
# not a broken run, it is a confident wrong belief.
REMOVED_KEYS = {
    "pr_review": ("fix", "coderabbit_fix", "greptile_fix"),
    "autonomous": ("on_red_findings", "on_simplify_changes"),
}


class RemovedConfigKey(ValueError):
    """A `.project-conf.toml` carries a key BILL-433 removed."""


def _reject_removed_keys(data, conf_path):
    found = [
        (table, key)
        for table, keys in REMOVED_KEYS.items()
        for key in keys
        if key in data.get(table, {})
    ]
    if found:
        listed = ", ".join(f"[{t}] {k}" for t, k in found)
        raise RemovedConfigKey(
            f"{conf_path}: {listed} — removed in BILL-433 and read by no step. "
            "Delete the line(s). Naming them here rather than failing generically "
            "is the point: the fix is a deletion, and you should not have to go "
            "hunting for which one."
        )


class Conventions:
    def __init__(self, system, repo, prefix, status_labels):
        self.system = system
        self.repo = repo
        self.prefix = prefix
        self.status_labels = status_labels


def load(conf_path):
    with pathlib.Path(conf_path).open("rb") as f:
        data = tomllib.load(f)
    _reject_removed_keys(data, conf_path)
    return Conventions(
        system=data["system"],
        repo=data["key"],
        prefix=data["prefix"],
        status_labels=data.get("status_labels", {}),
    )
