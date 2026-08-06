"""
Phase 0 red tests for BILL-456 — the Desktop installers strip all frontmatter.

Transcribed from the ticket's Test expectations
(https://github.com/iansmith/slopstop/issues/456). Transcription, not authorship.
If an expected value here is wrong, the sanctioned exit is the TICKET
UNDERSPECIFIED halt (TD-4a), not an edit to this file.

Two costs of the stripping, both pinned below:

  1. Ten skills declare `disable-model-invocation: true` and every installed copy
     loses it, so a model can launch :merge or :run on its own.
  2. It is the only reason `review` cannot ship — BILL-436 excluded it because
     `context: fork` would be deleted in transit.

The premise is our own awk block, not a harness rule. `code.claude.com/docs/en/skills`:
"Custom commands have been merged into skills" and "Files in `.claude/commands/`
still work and support the same frontmatter."

Which installer these tests exercise, and why:
`install-for-claude-desktop.sh` fetches from GitHub, so it can only ever install the
*released* version — running it end-to-end here would test master, not this branch.
`-local.sh` installs from the working copy, so it is the one driven end-to-end. The
GitHub variant is held to the same contract statically (same SKILLS array, same
transform), which is the strongest check available without network or a release.

`DEST` derives from `$HOME`, so every install below runs against a tmp HOME and
cannot touch the real ~/.claude/commands.

Test command:
    python3 -m pytest tests/test_bill456_behaviors.py -v
"""

import re
import subprocess
import sys

import pytest

from conftest import REPO_ROOT, SKILLS_DIR

LOCAL_INSTALLER = REPO_ROOT / "install-for-claude-desktop-local.sh"
GH_INSTALLER = REPO_ROOT / "install-for-claude-desktop.sh"

# Every skill whose SKILL.md declares disable-model-invocation. Derived from the
# repo rather than hardcoded: a hardcoded list would silently stop covering a
# skill that gained the field later.
HUMAN_ONLY = sorted(
    d.name
    for d in SKILLS_DIR.iterdir()
    if (d / "SKILL.md").is_file()
    and "disable-model-invocation" in (d / "SKILL.md").read_text(encoding="utf-8")
)


def _frontmatter(text):
    """The frontmatter block of an installed command file, or None if absent."""
    text = text.replace("\r\n", "\n")
    if not text.startswith("---\n"):
        return None
    end = text.find("\n---", 4)
    return None if end == -1 else text[4:end]


@pytest.fixture(scope="module")
def installed(tmp_path_factory):
    """Run the local installer against a throwaway HOME; return {name: text}."""
    home = tmp_path_factory.mktemp("home")
    result = subprocess.run(
        ["bash", str(LOCAL_INSTALLER)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        env={"HOME": str(home), "PATH": "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin"},
    )
    assert result.returncode == 0, f"installer failed:\n{result.stdout}\n{result.stderr}"
    dest = home / ".claude" / "commands"
    assert dest.is_dir(), f"installer produced no {dest}"
    return {p.name: p.read_text(encoding="utf-8") for p in dest.glob("slopstop-*.md")}


def _skills_array(path):
    m = re.search(r"^SKILLS=\(([^)]*)\)", path.read_text(encoding="utf-8"), re.M)
    assert m, f"no SKILLS=( ... ) array in {path.name}"
    return set(m.group(1).split())


@pytest.mark.parametrize("skill", HUMAN_ONLY)
def test_installed_copy_keeps_disable_model_invocation(installed, skill):
    """Ticket expectation 1 — the guardrail must survive the install.

    Ten skills declare it; every installed copy currently loses it, so a model can
    launch :merge or :run unprompted. Expected literal: `disable-model-invocation: true`.
    """
    name = f"slopstop-{skill}.md"
    assert name in installed, f"{name} was not installed"
    fm = _frontmatter(installed[name])
    assert fm is not None, f"{name} has no frontmatter block at all"
    assert "disable-model-invocation: true" in fm, (
        f"{name} lost `disable-model-invocation: true` — the repo declares it, so "
        f"the installed copy is model-invocable when it must not be"
    )


def test_review_is_installed_with_its_mechanism_intact(installed):
    """Ticket expectation 2 — the two fields that make review what it is.

    Without `context: fork` it silently reviews its own caller's session (the PR #411
    failure); without `background: false` :pr has no verdict in the invoking turn.
    """
    assert "slopstop-review.md" in installed, (
        "review is not installed — BILL-456 exists to ship it"
    )
    fm = _frontmatter(installed["slopstop-review.md"])
    assert fm is not None, "slopstop-review.md has no frontmatter block"
    assert "context: fork" in fm, (
        "installed review lost `context: fork` — it would run in the caller's session "
        "while looking isolated, which is worse than not shipping it"
    )
    assert "background: false" in fm, (
        "installed review lost `background: false` — :pr needs the verdict in-turn"
    )


def test_both_installers_ship_review(installed):
    """Ticket expectation 4 — one definition, two files (universal §5)."""
    local, gh = _skills_array(LOCAL_INSTALLER), _skills_array(GH_INSTALLER)
    assert "review" in local, "install-for-claude-desktop-local.sh omits review"
    assert "review" in gh, "install-for-claude-desktop.sh omits review"
    assert local == gh, (
        f"installer skill sets differ: only local={sorted(local - gh)}, "
        f"only gh={sorted(gh - local)}"
    )


def test_no_installed_command_claims_the_bare_skill_name(installed):
    """Added by the Step 0f adversary pass. Guards the obvious wrong implementation.

    Mutation that survived every frozen test: delete the awk block entirely and copy
    frontmatter verbatim. All 19 pass — `disable-model-invocation` survives, `review`
    keeps `context: fork` — while every command also carries its bare `name:`. Per the
    docs, `name` is the display name that decides the invoked command name, so
    `slopstop-pr.md` declaring `name: pr` can claim `/pr` and collide with a bundled or
    project skill.

    The ticket names this ("the part that is not simply 'stop stripping'") but no frozen
    test covered it, because with frontmatter stripped there is no `name:` to be wrong —
    it would have been green at Phase 0, and only failing tests may be frozen.
    """
    for filename, text in installed.items():
        skill = filename[len("slopstop-"):-len(".md")]
        fm = _frontmatter(text)
        if fm is None:
            continue
        for line in fm.split("\n"):
            if line.startswith("name:"):
                declared = line.split(":", 1)[1].strip().strip("'\"")
                assert declared != skill, (
                    f"{filename} declares `name: {skill}` — it would claim /{skill} "
                    f"rather than /slopstop-{skill}, colliding with any bundled or "
                    f"project skill of that name"
                )


def test_installed_review_stays_model_invocable(installed):
    """Added by the Step 0f adversary pass. The inverse mutation, equally silent.

    Mutation: preserve frontmatter by stamping `disable-model-invocation: true` onto
    every installed command. All 19 frozen tests pass — the sixteen guardrail tests go
    green *because* of the mutation — and `review` becomes human-only, so `:pr` Step 6
    can never invoke it. The ticket would report success having re-broken the exact
    thing it exists to fix.

    review is the one skill that must stay model-invocable: :pr calls it. The repo file
    correctly omits the field; the installed copy must too.
    """
    assert "slopstop-review.md" in installed, "review is not installed"
    fm = _frontmatter(installed["slopstop-review.md"])
    assert fm is not None, "slopstop-review.md has no frontmatter block"
    assert "disable-model-invocation" not in fm, (
        "installed review carries disable-model-invocation — :pr Step 6 could never "
        "invoke it, which is the blocker this whole ticket exists to remove"
    )


# Skills that other skills invoke as tools. These must stay model-invocable: a caller
# that sequences them cannot launch one that is marked human-only.
#
#   :design and :single-ticket -> grill
#   :merge                     -> update, document, archive
#   :pr                        -> review
#
# **This list is maintained by hand, and nothing detects a new entry.** Deriving it would
# mean grepping skill prose for invocation instructions, and this repo does not assert on
# markdown content (2026-08-05 rule) — a `Next: /slopstop:archive (fresh session)` line is
# advice to a human, while `Invoke /slopstop:archive as a Skill invocation` is a call, and
# only prose distinguishes them. Surfaced rather than faked: adding a skill-to-skill
# invocation without adding it here will not be caught by any test.
TOOL_SKILLS = ("grill", "archive", "document", "update", "review",
               # the reorg's workers: :run/:tickets/:design launch each one via an
               # Agent whose prompt is a Skill() call, so they are tools, not commands.
               "investigate", "red-tests", "mutation-check", "adversary", "implement",
               "slop-check", "vacuity-check", "complexity-check")


@pytest.mark.parametrize("skill", TOOL_SKILLS)
def test_tool_skills_stay_model_invocable(skill):
    """A skill another skill invokes must not be marked human-only.

    Found by reviewing this PR: preserving frontmatter correctly restored
    `disable-model-invocation` — and four of the sixteen are skills that other skills
    call. `:merge` would have merged the PR, then failed three times in a row invoking
    `:update`, `:document` and `:archive`, after the irreversible step.

    Ian's ruling, 2026-08-05: "Those three are not human-only. They are part of the
    process that are used as tools by skills like :merge." `grill` is the same case
    (`:design` and `:single-ticket` both call it) and is included on that reasoning.
    """
    fm = _frontmatter((SKILLS_DIR / skill / "SKILL.md").read_text(encoding="utf-8"))
    assert fm is not None, f"skills/{skill}/SKILL.md has no frontmatter"
    assert "disable-model-invocation" not in fm, (
        f"skills/{skill}/SKILL.md is marked human-only, but other skills invoke it as a "
        f"tool — the caller cannot launch it, and the failure lands mid-workflow"
    )


def test_installer_runs_from_a_non_root_cwd_with_a_relative_path(tmp_path_factory):
    """Mandated by the ticket standard: subprocess, non-root cwd, relative path.

    The installer resolves its own directory to find the skills to copy. Invoked by a
    relative path from elsewhere, a script that resolved against `cwd` instead of its
    own location would copy nothing and still exit 0 — the exact failure shape the
    standard cites, and nothing here ran it.
    """
    home = tmp_path_factory.mktemp("home_relpath")
    result = subprocess.run(
        ["bash", "../install-for-claude-desktop-local.sh"],
        cwd=str(REPO_ROOT / "tests"),
        capture_output=True,
        text=True,
        env={"HOME": str(home), "PATH": "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin"},
    )
    assert result.returncode == 0, f"{result.stdout}\n{result.stderr}"
    dest = home / ".claude" / "commands"
    assert (dest / "slopstop-pr.md").is_file(), "no slopstop-pr.md from a relative invocation"
    assert (dest / "slopstop-review.md").is_file(), (
        "no slopstop-review.md from a relative invocation"
    )
    fm = _frontmatter((dest / "slopstop-review.md").read_text(encoding="utf-8"))
    assert fm and "context: fork" in fm, "relative invocation lost review's context: fork"
