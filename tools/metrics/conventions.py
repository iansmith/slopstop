"""`.project-conf.toml` decoding -- the single home for convention reads (charter R4).

No other module in this package reads `.project-conf.toml` directly; everything
that needs `system`, `repo`, `prefix`, or a status label goes through `load()`.
"""

import pathlib
import tomllib


class Conventions:
    def __init__(self, system, repo, prefix, status_labels):
        self.system = system
        self.repo = repo
        self.prefix = prefix
        self.status_labels = status_labels


def load(conf_path):
    with pathlib.Path(conf_path).open("rb") as f:
        data = tomllib.load(f)
    return Conventions(
        system=data["system"],
        repo=data["key"],
        prefix=data["prefix"],
        status_labels=data.get("status_labels", {}),
    )
