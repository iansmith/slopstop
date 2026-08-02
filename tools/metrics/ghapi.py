"""Thin `gh api` subprocess wrapper, with the fleet's `gh` binary resolution ladder."""

import json
import pathlib
import shutil
import subprocess

_GH_CANDIDATES = [
    "/usr/local/bin/gh",
    str(pathlib.Path.home() / ".local/bin/gh"),
    "/opt/homebrew/bin/gh",
]


class GhNotFoundError(RuntimeError):
    """No `gh` binary found at any known path or on $PATH."""


def resolve_gh():
    for candidate in _GH_CANDIDATES:
        if pathlib.Path(candidate).is_file():
            return candidate
    found = shutil.which("gh")
    if found:
        return found
    raise GhNotFoundError("gh binary not found on any known path")


def gh_api(path):
    gh = resolve_gh()
    result = subprocess.run(
        [gh, "api", path], capture_output=True, text=True, check=True
    )
    return json.loads(result.stdout)
