"""
Phase 0 red tests for BILL-166 — scratch/ layout: seeded gitignored
interchange directory. Extended by BILL-181 for the .slopstop/ tracking layout.

The v3 process (design/slopstop-process.md §4) puts all inter-tier interchange
in a gitignored scratch/ directory, and per-ticket tracking in a gitignored
.slopstop/ directory. :gh-init seeds and gitignores both.

Tracking must NOT live under ~/.claude: it is a protected path, and a headless
fleet agent's Write tool refuses it even when the launch passes a matching
--add-dir. An agent denied its tracking dir invents a local one rather than
halting (BILL-181), so the recommendation is project-local .slopstop/.

Expected behaviors:
1. This repo's .gitignore ignores scratch/.
2. skills/gh-init/SKILL.md seeds scratch/ and .slopstop/ and appends both
   gitignore entries idempotently (no duplicate lines on re-run).
3. .project-conf.toml.example ships tracking_dir and archive_dir as the
   recommended defaults, COMMENTED OUT (activation belongs to the seeding
   paths, which gitignore .slopstop/ in the same run).
4. CONFIG.md documents tracking_dir, archive_dir, and the ~/.claude trap.
5. Neither the example nor :gh-init ever recommends a path under ~/.claude.

Test command:
    python3 -m pytest tests/test_bill166_behaviors.py -v
"""

import tomllib
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent
GITIGNORE = REPO_ROOT / ".gitignore"
GH_INIT = REPO_ROOT / "skills" / "gh-init" / "SKILL.md"
DESIGN = REPO_ROOT / "skills" / "design" / "SKILL.md"
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


def test_gh_init_activates_both_project_local_dirs():
    """:gh-init must activate both project-local dirs — by creating them, not by config.

    Superseded by BILL-310. This test used to require the config template to write
    `tracking_dir = ".slopstop/ticket-active"` and its archive twin. Under BILL-310's
    tier-2 resolution the *presence* of `.slopstop/` resolves both paths on its own, so
    those keys became redundant noise and gh-init stopped emitting them — the keys are
    overrides now, not settings a bootstrap has to supply.

    The invariant is unchanged and still worth guarding: gh-init is the safe activation
    path because Step 8b creates AND gitignores `.slopstop/` in the same run, so tracking
    files can never be swept up by :pr's `git add -A`. What moved is only *how*
    activation happens. Creating the directory is now itself the activation, which is
    why the mkdir is the thing to assert.
    """
    text = GH_INIT.read_text()
    assert ".slopstop/ticket-active" in text and ".slopstop/ticket-archive" in text, (
        ":gh-init must still create both project-local dirs (Step 8b's mkdir -p)"
    )
    assert 'tracking_dir = ".slopstop/ticket-active"' not in text, (
        ":gh-init must NOT write tracking_dir into the config template — a project-local "
        ".slopstop/ resolves it via tier 2, so the key is redundant (BILL-310)"
    )


def test_gh_init_gitignores_what_it_activates():
    """Step 8b must ignore .slopstop/, not just scratch/.

    Activating a repo-relative tracking_dir without ignoring it is the exact
    footgun the commented-out example exists to prevent.
    """
    text = GH_INIT.read_text()
    assert ".slopstop/" in text and "check-ignore" in text
    assert "'.slopstop/'" in text, "the ignore entry must be appended, not just mkdir'd"


@pytest.mark.parametrize("skill", [GH_INIT, DESIGN], ids=["gh-init", "design"])
def test_every_seeding_path_gitignores_slopstop(skill):
    """BOTH seeding paths must ignore .slopstop/, not just scratch/.

    CONFIG.md, gh-init's own prose, and this file's docstrings all name
    :gh-init AND :design as the seeding paths that make activating a
    repo-relative tracking_dir safe. :design seeded only scratch/, so a project
    bootstrapped through it with an active tracking_dir = ".slopstop/..." would
    have every tracking dir swept into its first PR by :pr's `git add -A`.
    """
    text = skill.read_text()
    assert "check-ignore -q .slopstop/" in text, (
        f"{skill.parent.name} seeds tracking but never gitignores .slopstop/"
    )
    assert "'.slopstop/'" in text, (
        f"{skill.parent.name} must append the ignore entry, not just mkdir the dir"
    )


def test_example_documents_dirs_as_overrides_without_activating_them():
    """The example documents both keys but ships them COMMENTED — and no longer as advice.

    Reframed by BILL-310. This used to require the commented example values to be
    exactly `".slopstop/ticket-active"` / `".slopstop/ticket-archive"`, presented as
    "the recommendation". Those are now precisely the values tier-2 resolution produces
    from a bare `.slopstop/` directory, so as advice they are redundant — and worse,
    that literal string presented as guidance is what a session holding an
    already-configured `.slopstop` followed by appending `ticket-active` to it, inventing
    the divergent second tree BILL-310 exists to prevent. The example override now points
    somewhere that is obviously an override.

    The invariant that still matters, and is still asserted below: copying the example
    must not *activate* a repo-relative tracking dir in a repo where `.slopstop/` isn't
    gitignored, because an un-ignored `.slopstop/` gets committed by `:pr`'s `git add -A`.
    Activation belongs to the seeding paths (`:gh-init` / `:design`), which create and
    gitignore `.slopstop/` in the same run.
    """
    raw = EXAMPLE.read_text()
    assert "# tracking_dir = " in raw, (
        "both keys must still be documented, as commented-out overrides"
    )
    assert "# archive_dir  = " in raw, (
        "archive_dir must be documented alongside tracking_dir — they resolve as a pair"
    )
    assert '# tracking_dir = ".slopstop/ticket-active"' not in raw, (
        "the commented override must NOT be `.slopstop/ticket-active` — that is what a "
        "bare `.slopstop/` already resolves to (tier 2), and presenting it as advice is "
        "the appending trap BILL-310 removed"
    )
    conf = tomllib.loads(raw)
    assert "tracking_dir" not in conf, (
        "the example must NOT activate tracking_dir — copiers without the "
        "gitignore seeding would commit their tracking files"
    )
    assert "archive_dir" not in conf, "the example must NOT activate archive_dir either"


def test_tracking_dirs_never_recommended_under_protected_claude_path():
    """~/.claude is protected: an agent's Write tool refuses it even with --add-dir.

    A recommended (uncommented or commented) project setting pointing there
    would silently break every headless fleet agent, which then invents its own
    tracking dir rather than halting. Guard the recommendation, not the default.
    """
    for path in (EXAMPLE, GH_INIT):
        text = path.read_text()
        assert 'tracking_dir = "~/.claude' not in text, f"{path.name} recommends a protected path"
        assert 'archive_dir  = "~/.claude' not in text, f"{path.name} recommends a protected path"


def test_config_md_documents_tracking_dir_and_scratch():
    """CONFIG.md must document both dir keys and the scratch/ layout."""
    text = CONFIG_MD.read_text()
    assert "tracking_dir" in text, "CONFIG.md must document tracking_dir"
    assert "archive_dir" in text, "CONFIG.md must document archive_dir"
    assert "scratch/runs/" in text, (
        "CONFIG.md must describe the scratch/ layout (runs/ + tickets/)"
    )


def test_config_md_warns_about_the_protected_claude_path():
    """The ~/.claude trap must be written down, not rediscovered per project."""
    text = CONFIG_MD.read_text()
    assert "protected path" in text
    assert "--add-dir" in text, (
        "the warning must say the trap survives a matching --add-dir, "
        "otherwise the reader assumes granting the dir is enough"
    )
