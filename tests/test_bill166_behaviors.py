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
    """:gh-init must carry the actual seeding step, not just mention scratch/.

    Anchored to the implementation (step heading + mkdir command) so the test
    fails if the seeding commands are removed while disclosure prose remains.
    """
    text = GH_INIT.read_text()
    assert "## Step 8b" in text, ":gh-init must have the Step 8b seeding step"
    assert "mkdir -p" in text and "scratch" in text, (
        ":gh-init Step 8b must create the scratch/ directory"
    )


def test_gh_init_seeding_is_idempotent():
    """The gitignore append must be guarded against duplicate coverage on re-run."""
    text = GH_INIT.read_text()
    assert "check-ignore" in text or "grep -qxF" in text, (
        ":gh-init's gitignore append must be guarded (git check-ignore, or the "
        "grep -qxF exact-line fallback) — 'idempotent' prose elsewhere in the "
        "skill doesn't count"
    )


def test_gh_init_writes_tracking_dir():
    """:gh-init's config template must activate tracking_dir = scratch/tickets.

    gh-init is the safe activation path: Step 8b gitignores scratch/ in the
    same run, so tracking files can never be swept up by :pr's `git add -A`.
    """
    text = GH_INIT.read_text()
    assert 'tracking_dir = "scratch/tickets"' in text


def test_example_recommends_tracking_dir_without_activating_it():
    """The example documents the recommendation but ships the key COMMENTED.

    Copying the example must not activate a repo-relative tracking dir in a
    repo where scratch/ isn't gitignored — an un-ignored scratch/ would be
    committed by :pr's `git add -A`. Activation belongs to the seeding paths
    (:gh-init / :design), which gitignore scratch/ in the same run.
    """
    raw = EXAMPLE.read_text()
    assert '# tracking_dir = "scratch/tickets"' in raw, (
        "the recommendation must be present, as a commented-out key"
    )
    conf = tomllib.loads(raw)
    assert "tracking_dir" not in conf, (
        "the example must NOT activate tracking_dir — copiers without the "
        "gitignore seeding would commit their tracking files"
    )


def test_config_md_documents_tracking_dir_and_scratch():
    """CONFIG.md must document the tracking_dir key and the scratch/ layout."""
    text = CONFIG_MD.read_text()
    assert "tracking_dir" in text, "CONFIG.md must document tracking_dir"
    assert "scratch/runs/" in text, (
        "CONFIG.md must describe the scratch/ layout (runs/ + tickets/)"
    )
