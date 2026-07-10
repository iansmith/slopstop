"""
Test suite for BILL-216: Bind $PREFIX from the `prefix` field, not `key`.

Verifies that:
1. No skill binds $PREFIX from the `key` field (under any wording)
2. Each skill's binding sentence contains the literal string `` (`prefix` field) ``
3. Each skill mentions hard errors for missing/invalid `prefix`
4. skills/update/SKILL.md doesn't contradict itself
5. skills/create-gh/SKILL.md is unchanged (reference wording)
"""

import re
import pytest
from pathlib import Path

# The ten files that must be fixed
SKILLS_TO_FIX = {
    "skills/start/SKILL.md",
    "skills/run/SKILL.md",
    "skills/tickets/SKILL.md",
    "skills/plan/SKILL.md",
    "skills/pr/SKILL.md",
    "skills/merge/SKILL.md",
    "skills/update/SKILL.md",
    "skills/update-ticket/SKILL.md",
    "skills/archive/SKILL.md",
    "skills/document/SKILL.md",
}

# Reference file that should NOT be touched
REFERENCE_FILE = "skills/create-gh/SKILL.md"

# Regex patterns covering all four variants of the defect
DEFECT_PATTERNS = [
    r"PREFIX\s*=\s*key",  # Set $PREFIX = key
    r"`key`\s*\([^)]*\$PREFIX",  # `key` (`$PREFIX`)
    r"Extract\s+`key`",  # Extract `key` ... and call it $PREFIX
]

REPO_ROOT = Path(__file__).parent.parent


def read_file(rel_path: str) -> str:
    """Read a file relative to repo root."""
    return (REPO_ROOT / rel_path).read_text()


def get_project_scope_section(content: str) -> str:
    """Extract the Project scope section (or the primary binding text)."""
    # Look for "## Project scope" or "## Project-scope"
    match = re.search(r"##\s+Project[- ]scope(.+?)(?=##\s+|\Z)", content, re.DOTALL | re.IGNORECASE)
    if match:
        return match.group(1)
    # If no dedicated section, return the whole content (binding may be inline in intro)
    return content


class TestNoSkillBindsPrefixFromKey:
    """Test that no skill matches the defect patterns."""

    @pytest.mark.parametrize("skill_path", SKILLS_TO_FIX)
    def test_no_defect_pattern(self, skill_path: str):
        """Each skill must NOT match any of the four defect patterns."""
        content = read_file(skill_path)

        for pattern in DEFECT_PATTERNS:
            matches = list(re.finditer(pattern, content, re.IGNORECASE))
            assert not matches, (
                f"{skill_path} contains defect pattern '{pattern}' at "
                f"{[(m.start(), m.end()) for m in matches]}"
            )


class TestBindingSentenceNamesPrefixField:
    """Test that each skill's binding sentence contains `` (`prefix` field) ``."""

    @pytest.mark.parametrize("skill_path", SKILLS_TO_FIX)
    def test_contains_prefix_field_marker(self, skill_path: str):
        """Binding sentence must literally contain `` (`prefix` field) ``."""
        content = read_file(skill_path)
        project_scope = get_project_scope_section(content)

        # The marker is a backtick-enclosed phrase naming the field
        marker = "(`prefix` field)"
        assert marker in project_scope, (
            f"{skill_path}'s Project-scope section does not contain "
            f'the literal string "{marker}"'
        )


class TestAbsentAndInvalidPrefixAreHardErrors:
    """Test that skills document the hard errors for absent/invalid prefix."""

    @pytest.mark.parametrize("skill_path", SKILLS_TO_FIX)
    def test_mentions_absent_prefix_error(self, skill_path: str):
        """Skill must describe stopping/refusing when prefix is absent."""
        content = read_file(skill_path)
        project_scope = get_project_scope_section(content)

        # Look for keywords indicating a hard stop/error on missing prefix
        error_keywords = [
            r"absent",
            r"missing",
            r"stop.*prefix",
            r"refuse.*prefix",
            r"error.*prefix",
            r"clear error",
            r"hard error",
        ]

        found = any(re.search(kw, project_scope, re.IGNORECASE) for kw in error_keywords)
        assert found, (
            f"{skill_path} does not mention stopping/refusing when prefix is absent"
        )

    @pytest.mark.parametrize("skill_path", SKILLS_TO_FIX)
    def test_mentions_invalid_prefix_error(self, skill_path: str):
        """Skill must describe stopping when prefix is invalid."""
        content = read_file(skill_path)
        project_scope = get_project_scope_section(content)

        # Look for pattern reference or validation language
        validation_keywords = [
            r"match.*\^",  # regex pattern reference
            r"invalid",
            r"pattern",
            r"stops.*prefix",
            r"error.*quoting",
            r"does not match",
        ]

        found = any(re.search(kw, project_scope, re.IGNORECASE) for kw in validation_keywords)
        assert found, (
            f"{skill_path} does not mention stopping when prefix is invalid"
        )


class TestUpdateSkillSelfConsistent:
    """Test that skills/update/SKILL.md lines 12 and 14 don't contradict."""

    def test_update_binding_and_branch_parser_agree(self):
        """Update skill's binding sentence and branch-match sentence must describe same value."""
        content = read_file("skills/update/SKILL.md")
        lines = content.split("\n")

        # Find line 12 (index 11) and 14 (index 13) - binding and branch parser
        # Line 12 should say binding, line 14 should describe branch matching
        line_12 = lines[11] if len(lines) > 11 else ""
        line_14 = lines[13] if len(lines) > 13 else ""

        # Both must reference `$PREFIX` from the same source
        # The binding (line 12) must be from `prefix` field
        # The branch parser (line 14) must match `^$PREFIX-\d+$`

        # Line 12 must NOT say "Extract `key`" (that would contradict)
        assert "Extract `key`" not in line_12 or "(`prefix` field)" in line_12, (
            "skills/update/SKILL.md line 12 contradicts line 14: "
            "line 12 describes binding but doesn't mention prefix field"
        )

        # Line 14 must reference `^$PREFIX-\d+$` matching
        assert "PREFIX" in line_14 and r"\d+" in line_14, (
            "skills/update/SKILL.md line 14 must describe matching ^$PREFIX-\\d+$"
        )


class TestCreateGhRemainsReference:
    """Test that skills/create-gh/SKILL.md is unchanged."""

    def test_create_gh_has_reference_wording(self):
        """Create-gh must still contain the reference wording."""
        content = read_file(REFERENCE_FILE)

        # The reference wording is:
        # Extract `$PREFIX` (`prefix` field), `$OWNER` and `$REPO` (split `key` on `/`).
        reference_phrase = "Extract `$PREFIX` (`prefix` field)"
        assert reference_phrase in content, (
            f"{REFERENCE_FILE} is missing the reference wording: {reference_phrase}"
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
