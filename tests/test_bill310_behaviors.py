"""
Phase 0 red tests for BILL-310 — tracking_dir/archive_dir are overrides, not requirements.

Transcribed from the ticket's Test expectations
(https://github.com/iansmith/slopstop/issues/310). Structural assertions over
skill and doc text, matching the test_skill_structure.py convention.

Twelve skills each re-derived the resolution and defaulted straight to
`~/.claude/`, with no check for a project-local `.slopstop/`. Because
`tracking_dir` is the *direct parent* of `$TRACKING_DIR/$TICKET`,
`tracking_dir = ".slopstop"` yields `.slopstop/SOP-123` while the global default's
own shape is `.../ticket-active/SOP-123`. Nothing reconciled the two layouts.

Verified harm (sophie): `git log -L14,15:.project-conf.toml` proves `tracking_dir`
was only ever `.pi` then `.slopstop` — never a `.../ticket-active` value — so the
`.slopstop/ticket-active/` and `.slopstop/ticket-archive/` trees were *invented by
sessions guessing*. 33 `SOP-*` dirs stranded in `~/.claude/ticket-archive` and 2 in
`~/.claude/ticket-active` while `.slopstop/ticket-archive` held 60 more. One ticket
(SOP-158) ended up with two contradictory records.

The guessing mechanism was in the guard text itself: it told the operator to "Set a
project-local path (e.g. \".slopstop/ticket-active\")", so a session holding an
already-configured `.slopstop` appended `ticket-active` to it. Fixing the ladder
without fixing that example would leave the trap in place — hence
test_guard_no_longer_teaches_the_appending_mistake.

These tests FAIL on current code and turn GREEN once the fix is applied.

Test command:
    python3 -m pytest tests/test_bill310_behaviors.py -v
"""

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent
SKILLS_DIR = REPO_ROOT / "skills"
CONFIG_DOC = REPO_ROOT / "CONFIG.md"

SHARED_REF = SKILLS_DIR / "start" / "references" / "tracking-dir-resolution.md"
# The pointer every consuming skill must carry, in the repo's installed-path form.
POINTER = "slopstop-start-refs/tracking-dir-resolution.md"

# The 12 skills the ticket enumerates as re-deriving the resolution independently.
CONSUMING_SKILLS = [
    "create-gh",
    "archive",
    "design",
    "run",
    "document",
    "gh-init",
    "plan",
    "update-ticket",
    "merge",
    "pr",
    "start",
    "update",
]

# The old per-skill boilerplate. Its survival anywhere means a skill still
# re-derives the rule instead of referencing it.
INLINE_BOILERPLATE = "If absent or equal to `~/.claude/ticket-active`, default to"


@pytest.fixture(scope="module")
def shared_ref():
    assert SHARED_REF.is_file(), (
        f"{SHARED_REF.relative_to(REPO_ROOT)} must exist — behavior 1 requires the "
        "resolution to live in one shared place all 12 skills reference"
    )
    return SHARED_REF.read_text()


def test_shared_reference_exists(shared_ref):
    """Behavior 1 — one shared definition, not twelve."""
    assert len(shared_ref) > 500, "the shared reference must actually carry the ladder"


def test_shared_reference_is_installed(shared_ref):
    """A reference absent from manifest.txt is never installed, so the pointers dangle.

    The Desktop installer fetches each skill's manifest and installs only what it
    lists; test_skill_structure.py enforces manifest/disk agreement. A shared doc that
    12 skills point at but which never lands on disk is worse than the duplication.
    """
    manifest = (SKILLS_DIR / "start" / "references" / "manifest.txt").read_text()
    assert "tracking-dir-resolution.md" in manifest, (
        "skills/start/references/manifest.txt must list tracking-dir-resolution.md or "
        "it is never installed to ~/.claude/commands/slopstop-start-refs/"
    )


def test_all_three_tiers_are_defined(shared_ref):
    """Behavior 2 — the precedence ladder, resolved for both paths together."""
    low = shared_ref.lower()
    for token, why in (
        ("tier 1", "explicit key wins verbatim"),
        ("tier 2", "a project-local .slopstop/ implies both subdirs"),
        ("tier 3", "the historical ~/.claude default"),
    ):
        assert token in low, f"the shared reference must define {token} — {why}"
    assert ".slopstop/ticket-active" in shared_ref, "tier 2's tracking path"
    assert ".slopstop/ticket-archive" in shared_ref, "tier 2's archive path"
    assert "~/.claude/ticket-active" in shared_ref, "tier 3's tracking path"
    assert "~/.claude/ticket-archive" in shared_ref, "tier 3's archive path"


def test_bare_slopstop_directory_is_sufficient(shared_ref):
    """Behavior 3 — presence of `.slopstop/` alone implies both subdirectories.

    Neither key needs setting. This is the whole point of tier 2: it makes the
    ~/.claude default mostly unreachable without anyone configuring anything.
    """
    low = shared_ref.lower()
    assert "sufficient" in low or "alone" in low, (
        "the shared reference must state that the presence of .slopstop/ alone is "
        "enough — that neither key needs setting for tier 2 to apply"
    )
    assert "both" in low, "tier 2 must be stated as implying BOTH subdirectories"


def test_explicit_tracking_dir_still_resolves_verbatim(shared_ref):
    """Behavior 4 — `tracking_dir = ".slopstop"` means `.slopstop`, so state is never stranded.

    Tier 1 beats tier 2. sophie and aatoolkit have real state at `.slopstop/<TICKET>`;
    a ladder that reinterpreted their explicit key would lose it.
    """
    assert "verbatim" in shared_ref.lower(), (
        "tier 1 must say an explicit key is taken verbatim"
    )
    assert '`.slopstop`' in shared_ref or '".slopstop"' in shared_ref, (
        "the shared reference must work the flat `.slopstop` case explicitly — it is "
        "the live config in two projects and the one a reader will doubt"
    )


def test_the_pair_resolves_together(shared_ref):
    """Behavior 2 — setting only one key must not leave the other on the global default.

    The exact pairing that split sophie's state: tracking_dir = ".slopstop" with
    archive_dir unset sent active state into the repo and archives to ~/.claude.
    """
    low = shared_ref.lower()
    assert "together" in low, (
        "the shared reference must say both paths resolve together, in one pass"
    )


def test_mismatch_is_reported_never_relocated(shared_ref):
    """Behavior 5 — detect and report, never silently relocate.

    The ticket's hard constraint. Losing a ticket's tracking dir is the failure mode
    this whole ladder exists to prevent, so adopting stray state is the operator's call.
    """
    low = shared_ref.lower()
    assert "mismatch" in low, "the shared reference must define the mismatch report"
    assert "never" in low and ("relocat" in low or "move" in low), (
        "it must say a mismatched layout is never moved automatically"
    )
    assert "nothing has been moved" in low, (
        "the report must tell the operator explicitly that nothing was moved — "
        "otherwise 'mismatch' reads as 'I fixed it'"
    )


def test_guard_no_longer_teaches_the_appending_mistake():
    """The guard text was the guessing mechanism — fixing the ladder is not enough.

    `start/SKILL.md` told the operator to `Set a project-local path (e.g.
    ".slopstop/ticket-active")`. A session holding an already-configured `.slopstop`
    read that as license to append `ticket-active`, which is how the divergent trees
    were invented in the first place. Under tier 2 the remedy is a directory, not a key.
    """
    offenders = []
    for skill in CONSUMING_SKILLS:
        text = (SKILLS_DIR / skill / "SKILL.md").read_text()
        if 'Set a project-local path (e.g. \\".slopstop/ticket-active\\")' in text:
            offenders.append(skill)
        elif 'Set a project-local path (e.g. ".slopstop/ticket-active")' in text:
            offenders.append(skill)
    assert offenders == [], (
        f"these skills still tell the operator to set tracking_dir to "
        f'".slopstop/ticket-active": {offenders}. That instruction is what a session '
        "holding a configured `.slopstop` follows to invent `.slopstop/ticket-active`."
    )


@pytest.mark.parametrize("skill", CONSUMING_SKILLS)
def test_skill_references_the_shared_resolution(skill):
    """Behavior 1 — each of the 12 points at the shared step."""
    text = (SKILLS_DIR / skill / "SKILL.md").read_text()
    assert POINTER in text, (
        f"skills/{skill}/SKILL.md must point at the shared resolution "
        f"({POINTER}) rather than carrying or implying its own copy"
    )


@pytest.mark.parametrize("skill", CONSUMING_SKILLS)
def test_skill_no_longer_inlines_the_resolution(skill):
    """Behavior 1 — the duplicated paragraph is gone, not merely supplemented.

    Eight skills carried this byte-identical. Leaving a copy behind next to a pointer
    is how they drift apart again — and the inline copy has no tier 2, so a session
    reading it still defaults to ~/.claude.
    """
    text = (SKILLS_DIR / skill / "SKILL.md").read_text()
    assert INLINE_BOILERPLATE not in text, (
        f"skills/{skill}/SKILL.md still inlines the old resolution rule "
        f"({INLINE_BOILERPLATE!r}), which has no tier-2 check"
    )


def test_config_doc_documents_the_three_tiers():
    """CONFIG.md must present the keys as overrides, not required settings."""
    text = CONFIG_DOC.read_text()
    low = text.lower()
    assert "tier 2" in low, (
        "CONFIG.md must document the three-tier precedence — today it documents "
        "~/.claude/ticket-active as the flat default with no mention of .slopstop/"
    )
    row = next((l for l in text.splitlines() if l.startswith("| `tracking_dir`")), None)
    assert row is not None, "CONFIG.md must keep documenting tracking_dir"
    assert "override" in row.lower(), (
        "CONFIG.md's tracking_dir row must describe the key as an override — the "
        "ticket's framing is that these became overrides, not required settings"
    )
