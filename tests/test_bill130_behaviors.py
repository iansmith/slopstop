"""
Phase 0 red tests for BILL-130 — add pr-repo config field to decouple
GitHub owner/repo from JIRA key.

Expected behaviors after implementation:
1. All five affected skills read pr-repo when parsing $OWNER/$REPO
2. pr and merge skills no longer parse $OWNER/$REPO unconditionally from key
3. archive skill no longer says $OWNER/$REPO are always parsed from key
4. pr skill step 5b no longer says "canonical repo from key" (uses pr-repo when present)
5. Fallback to key is documented (backward-compatible when pr-repo absent)
6. merge skill: BOTH owner/repo-parse locations are updated (step 1a and github state section)

These tests FAIL on current code and turn GREEN once the implementation is complete.

Test command:
    python3 -m pytest tests/test_bill130_behaviors.py -v
"""

from pathlib import Path
import pytest

REPO_ROOT = Path(__file__).parent.parent
SKILLS_DIR = REPO_ROOT / "skills"


def _skill_text(name):
    """Return concatenated text of SKILL.md + all references/*.md for a skill."""
    base = SKILLS_DIR / name
    texts = []
    skill_md = base / "SKILL.md"
    if skill_md.exists():
        texts.append(skill_md.read_text())
    refs = base / "references"
    if refs.is_dir():
        for f in sorted(refs.glob("*.md")):
            texts.append(f.read_text())
    return "\n".join(texts)


def _spine(name):
    return (SKILLS_DIR / name / "SKILL.md").read_text()


# ---------------------------------------------------------------------------
# 1. pr-repo must be present in all five affected skill's full text
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("skill", ["pr", "merge", "document", "start", "archive"])
def test_skill_reads_pr_repo(skill):
    """All five affected skills must reference the pr-repo config key.

    BILL-130: pr-repo is the new optional field that decouples GitHub owner/repo
    from the JIRA/Linear key field. Every skill that uses $OWNER/$REPO must be
    aware of it.
    """
    text = _skill_text(skill)
    assert "pr-repo" in text, (
        f"skills/{skill}/ has no mention of 'pr-repo' — "
        f"BILL-130 requires this skill to read pr-repo from .project-conf.toml "
        f"and use it as $OWNER/$REPO when present."
    )


# ---------------------------------------------------------------------------
# 2. pr skill: pre-flight must no longer parse owner/repo exclusively from key
# ---------------------------------------------------------------------------

def test_pr_skill_preflight_owner_repo_uses_pr_repo():
    """skills/pr/SKILL.md pre-flight must read pr-repo, not only key, for $OWNER/$REPO.

    BILL-130: the pre-flight currently says
    'parse `$OWNER` and `$REPO` from `.project-conf.toml`'s `key` field'
    unconditionally. After the fix this must be conditional: use pr-repo when
    present, fall back to key otherwise.
    """
    spine = _spine("pr")
    # Old unconditional text must be gone — it asserts key as the sole source
    assert "parse `$OWNER` and `$REPO` from `.project-conf.toml`'s `key` field" not in spine, (
        "skills/pr/SKILL.md pre-flight still says to parse $OWNER/$REPO exclusively "
        "from 'key' — update it to use pr-repo when present and fall back to key otherwise."
    )


def test_pr_skill_create_pr_not_only_from_key():
    """skills/pr/SKILL.md step 5b must not say PR targets 'the canonical repo from key'.

    BILL-130: step 5b currently says 'owner=$OWNER, repo=$REPO (the canonical repo from
    `key`)' — once pr-repo is supported, the canonical repo comes from pr-repo
    (when set) not key. The parenthetical must be updated.
    """
    spine = _spine("pr")
    assert "the canonical repo from `key`" not in spine, (
        "skills/pr/SKILL.md step 5b still says '(the canonical repo from `key`)' — "
        "update it to reflect that pr-repo overrides key when present."
    )


# ---------------------------------------------------------------------------
# 3. merge skill: BOTH owner/repo-parse locations must be updated
# ---------------------------------------------------------------------------

def test_merge_skill_step1a_owner_repo_uses_pr_repo():
    """skills/merge/SKILL.md step 1a must read pr-repo, not only key, for $OWNER/$REPO.

    BILL-130: step 1a currently says
    'Parse `$OWNER` and `$REPO` from `.project-conf.toml`'s `key` field'
    unconditionally. This must become conditional on pr-repo.
    """
    spine = _spine("merge")
    assert "Parse `$OWNER` and `$REPO` from `.project-conf.toml`'s `key` field" not in spine, (
        "skills/merge/SKILL.md step 1a still parses $OWNER/$REPO exclusively from 'key' — "
        "update it to check pr-repo first and fall back to key."
    )


def test_merge_skill_github_state_section_owner_repo_uses_pr_repo():
    """skills/merge/SKILL.md GitHub state section must not parse $OWNER/$REPO from key only.

    BILL-130 gap: merge/SKILL.md has a SECOND owner/repo parse in the GitHub
    state-machine section (Step 2): 'Parse `$OWNER`/`$REPO` from `key`'.
    Both occurrences must be updated — fixing only one leaves the other broken.
    """
    spine = _spine("merge")
    assert "Parse `$OWNER`/`$REPO` from `key`" not in spine, (
        "skills/merge/SKILL.md GitHub state section still says "
        "'Parse `$OWNER`/`$REPO` from `key`' — this is the SECOND owner/repo-parse "
        "location that must be updated to check pr-repo first."
    )


# ---------------------------------------------------------------------------
# 4. archive skill: re-harvest call must not hardcode key as sole owner/repo source
# ---------------------------------------------------------------------------

def test_archive_skill_reharvest_not_only_from_key():
    """skills/archive/SKILL.md re-harvest call must not say $OWNER/$REPO come only from key.

    BILL-130: archive currently says 'where `$OWNER` and `$REPO` are parsed from
    `.project-conf.toml`'s `key` field' in the re-harvest POST documentation.
    This must be updated to use pr-repo when present.
    """
    spine = _spine("archive")
    assert "where `$OWNER` and `$REPO` are parsed from `.project-conf.toml`'s `key` field" not in spine, (
        "skills/archive/SKILL.md re-harvest step still says $OWNER/$REPO come only from "
        "'key' — update to use pr-repo when present, key otherwise."
    )


# ---------------------------------------------------------------------------
# 5. Fallback documented: when pr-repo absent, key is used (backward-compat)
# ---------------------------------------------------------------------------

def test_pr_repo_fallback_to_key_documented():
    """At least one skill must document that key is used as fallback when pr-repo is absent.

    BILL-130: the change must be backward-compatible. Projects without pr-repo must
    continue to work as today (key is used). This must be stated explicitly somewhere
    in a skill that also mentions pr-repo (so it's fallback language specific to pr-repo,
    not pre-existing fallback prose for other features).
    """
    for skill in ["pr", "merge", "start", "document", "archive"]:
        text = _skill_text(skill)
        if "pr-repo" not in text:
            continue
        # pr-repo is in this skill — check that fallback language is also present
        has_fallback = any(phrase in text for phrase in [
            "else `key`",
            "else key",
            "fall back to `key`",
            "fall back to key",
            "falls back to key",
            "falls back to `key`",
            "absent, use `key`",
            "absent, parse from `key`",
            "if not present, use `key`",
            "if not present, parse",
            "when not set",
            "pr-repo` is absent",
            "pr-repo is absent",
        ])
        if has_fallback:
            return  # at least one skill has both pr-repo and fallback language
    pytest.fail(
        "No skill documents the pr-repo → key fallback in a context that also mentions pr-repo — "
        "BILL-130 requires backward-compatibility: when pr-repo is absent, "
        "skills must fall back to parsing $OWNER/$REPO from key as today. "
        "At least one skill must say so explicitly (e.g. 'else key', 'fall back to key') "
        "in the same text that describes reading pr-repo."
    )


# ---------------------------------------------------------------------------
# 6. pr-repo is in the pre-flight / remote-config section of pr skill
# ---------------------------------------------------------------------------

def test_pr_skill_pr_repo_in_preflight_section():
    """skills/pr/SKILL.md pre-flight section must mention pr-repo alongside pr-remote/origin-remote.

    BILL-130: pr-repo is a remote/repo config key. The pre-flight already reads
    pr-remote and origin-remote. pr-repo must appear in the same pre-flight config
    block so Claude knows to read all three at startup.
    """
    spine = _spine("pr")
    # Find the remote config block — both pr-remote and origin-remote are there
    pr_remote_pos = spine.find("pr-remote")
    pr_repo_pos = spine.find("pr-repo")
    assert pr_repo_pos != -1, (
        "skills/pr/SKILL.md has no 'pr-repo' — add it to the pre-flight remote/repo "
        "config block alongside pr-remote and origin-remote."
    )
    # pr-repo must appear near pr-remote (within 500 chars) to be in the same config block
    assert abs(pr_repo_pos - pr_remote_pos) < 500, (
        "skills/pr/SKILL.md mentions pr-repo but it is far from pr-remote — "
        "pr-repo should be read in the same pre-flight config block as pr-remote and "
        "origin-remote so all three repo/remote settings are collected together."
    )


# ---------------------------------------------------------------------------
# Adversary gaps — added from adversary review
# ---------------------------------------------------------------------------

def test_start_skill_github_owner_repo_not_only_from_key():
    """skills/start/SKILL.md Step 2 GitHub path must not parse $OWNER/$REPO exclusively from key.

    Adversary gap 2: start/SKILL.md line 96 currently says
    'Parse `$OWNER`, `$REPO` from `.project-conf.toml` `key`' unconditionally.
    test_skill_reads_pr_repo[start] only checks positive presence — it passes if
    pr-repo is added anywhere in prose while the actual parse site is untouched.
    This negative test catches that case.
    """
    spine = _spine("start")
    assert "Parse `$OWNER`, `$REPO` from `.project-conf.toml` `key`" not in spine, (
        "skills/start/SKILL.md Step 2 GitHub path still parses $OWNER/$REPO exclusively "
        "from 'key' — update it to check pr-repo first and fall back to key otherwise."
    )


def test_archive_skill_reharvest_section_mentions_pr_repo():
    """The archive re-harvest POST block must reference pr-repo near the actual POST call.

    Adversary gap 3: the existing negative phrase test verifies the old text is gone,
    but pr-repo could be added to a preamble far from the POST body JSON, leaving
    the actual harvest call still sourcing $OWNER/$REPO from key only. This proximity
    check ensures pr-repo appears near the POST block itself.
    """
    spine = _spine("archive")
    harvest_start = spine.find("POST to the RAG service")
    if harvest_start == -1:
        pytest.skip("POST section not found in archive/SKILL.md — check section text")
    harvest_block = spine[harvest_start:harvest_start + 600]
    assert "pr-repo" in harvest_block, (
        "The archive re-harvest POST block does not mention pr-repo — "
        "pr-repo must be referenced near the POST body where $OWNER/$REPO are assembled, "
        "not just in an unrelated preamble section."
    )


def test_merge_skill_github_state_section_pr_repo_near_step2():
    """skills/merge/SKILL.md GitHub state section must mention pr-repo near the $OWNER/$REPO parse.

    Adversary gap 4: test_merge_skill_github_state_section_owner_repo_uses_pr_repo checks
    that the old unconditional parse text is absent, but doesn't confirm pr-repo is
    actually present in that section. A lazy implementation could remove the old text
    without adding pr-repo there, leaving the second parse site simply undefined.
    """
    spine = _spine("merge")
    gh_section = spine.find("**GitHub:**\n")
    if gh_section == -1:
        pytest.skip("GitHub state section not found in merge/SKILL.md")
    gh_block = spine[gh_section:gh_section + 350]
    assert "pr-repo" in gh_block, (
        "merge/SKILL.md GitHub state section (Step 2) does not mention pr-repo — "
        "the $OWNER/$REPO parse in this section must be updated to check pr-repo first, "
        "not just have the old text removed."
    )


# ---------------------------------------------------------------------------
# Adversary gaps — pre-emptive edge cases
# ---------------------------------------------------------------------------

def test_pr_repo_precedence_is_explicit():
    """At least one skill must explicitly state that pr-repo takes precedence over key.

    Adversary gap: a skill might mention 'pr-repo' in passing without saying which
    wins when both pr-repo and key are set. The precedence rule must be stated.
    """
    combined = "\n".join(_skill_text(s) for s in ["pr", "merge"])
    has_precedence = any(phrase in combined for phrase in [
        "pr-repo` if present",
        "pr-repo if present",
        "pr-repo` takes precedence",
        "pr-repo takes precedence",
        "when `pr-repo` is set",
        "when pr-repo is set",
        "if `pr-repo`",
        "$OWNER/$REPO` from `pr-repo`",
        "from pr-repo",
        "from `pr-repo`",
    ])
    assert has_precedence, (
        "No skill states that pr-repo takes precedence over key — "
        "at least pr or merge must explicitly say $OWNER/$REPO comes from pr-repo "
        "when it is set (e.g. 'if pr-repo is present, use it; else parse from key')."
    )


def test_merge_skill_pr_repo_near_step1a():
    """skills/merge/SKILL.md must mention pr-repo near the step 1a owner/repo parse.

    Adversary gap: pr-repo might be added to the top-level pre-flight of merge
    but not to step 1a where $OWNER/$REPO is actually computed — leaving the
    step 1a parse still reading from key.
    """
    spine = _spine("merge")
    step1a_start = spine.find("### 1a.")
    step1a_end = spine.find("### 1b.", step1a_start) if step1a_start != -1 else -1
    if step1a_start == -1 or step1a_end == -1:
        pytest.skip("Step 1a section not found in merge/SKILL.md — check section headings")
    step1a_text = spine[step1a_start:step1a_end]
    assert "pr-repo" in step1a_text, (
        "skills/merge/SKILL.md step 1a does not mention pr-repo — "
        "pr-repo must be read in step 1a (where $OWNER/$REPO is computed) "
        "not just in a preamble or unrelated section."
    )
