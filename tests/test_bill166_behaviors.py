"""
Phase 0 red tests for BILL-166 — scratch/ layout: seeded gitignored
interchange directory.

The v3 process (design/slopstop-process.md §4) puts all inter-tier interchange
in a gitignored scratch/ directory. This ticket makes :gh-init seed it, adds
the dogfood entry to this repo's .gitignore, and documents the
tracking_dir = "scratch/tickets" recommended default (config-only — :start
already resolves relative tracking_dir from the main worktree root).

Expected behaviors:
1. This repo's .gitignore ignores scratch/.
2. skills/gh-init/SKILL.md seeds scratch/ and appends the gitignore entry
   idempotently (no duplicate lines on re-run).
3. .project-conf.toml.example ships tracking_dir = "scratch/tickets" as the
   recommended default.
4. CONFIG.md documents tracking_dir and the scratch/ layout.

Test command:
    python3 -m pytest tests/test_bill166_behaviors.py -v
"""

import tomllib
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent
GITIGNORE = REPO_ROOT / ".gitignore"
GH_INIT = REPO_ROOT / "skills" / "gh-init" / "SKILL.md"
EXAMPLE = REPO_ROOT / ".project-conf.toml.example"
CONFIG_MD = REPO_ROOT / "CONFIG.md"


def test_repo_gitignores_scratch():
    """This repo dogfoods the layout: .gitignore must ignore scratch/."""
    lines = [ln.strip() for ln in GITIGNORE.read_text().splitlines()]
    assert "scratch/" in lines


def test_gh_init_seeds_scratch():
    """:gh-init must create scratch/ and add the gitignore entry."""
    text = GH_INIT.read_text()
    assert "scratch/" in text, ":gh-init must seed the scratch/ directory"
    assert ".gitignore" in text, ":gh-init must add scratch/ to .gitignore"


def test_gh_init_seeding_is_idempotent():
    """The gitignore append must guard against duplicate lines on re-run."""
    text = GH_INIT.read_text()
    assert "grep -qxF" in text, (
        ":gh-init's gitignore append must be duplicate-guarded with an exact "
        "whole-line check (grep -qxF) before the echo — 'idempotent' prose "
        "elsewhere in the skill doesn't count"
    )


def test_example_ships_tracking_dir_in_scratch():
    """.project-conf.toml.example must recommend tracking_dir = scratch/tickets."""
    conf = tomllib.loads(EXAMPLE.read_text())
    assert conf.get("tracking_dir") == "scratch/tickets"


def test_config_md_documents_tracking_dir_and_scratch():
    """CONFIG.md must document the tracking_dir key and the scratch/ layout."""
    text = CONFIG_MD.read_text()
    assert "tracking_dir" in text, "CONFIG.md must document tracking_dir"
    assert "scratch/runs/" in text, (
        "CONFIG.md must describe the scratch/ layout (runs/ + tickets/)"
    )
