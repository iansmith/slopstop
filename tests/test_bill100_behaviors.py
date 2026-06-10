"""
Phase 0 red tests for BILL-100 — harvest schedule docs follow-on.

Three deferred items from BILL-97 (PR #99):
1. .project-conf.toml.example — new file, all keys documented including harvest_schedule
2. skills/gh-init/SKILL.md — add Step 10 (harvest schedule setup)
3. design/cold-start.md §7 — add a nightly harvest setup step

These tests FAIL on current code and turn GREEN once all three items are done.

Test command:
    python3 -m pytest tests/test_bill100_behaviors.py -v
"""

from pathlib import Path
import re
import pytest

try:
    import tomllib
except ImportError:
    import tomli as tomllib  # type: ignore[no-redef]

REPO_ROOT = Path(__file__).parent.parent
SKILLS_DIR = REPO_ROOT / "skills"
DESIGN_DIR = REPO_ROOT / "design"
EXAMPLE_CONF = REPO_ROOT / ".project-conf.toml.example"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _skill_text(skill: str) -> str:
    """Return concatenated text of SKILL.md + references/*.md for *skill*."""
    base = SKILLS_DIR / skill
    texts = []
    skill_md = base / "SKILL.md"
    if skill_md.exists():
        texts.append(skill_md.read_text())
    refs = base / "references"
    if refs.is_dir():
        for f in sorted(refs.glob("*.md")):
            texts.append(f.read_text())
    return "\n".join(texts)


# ---------------------------------------------------------------------------
# Item 1 — .project-conf.toml.example
# ---------------------------------------------------------------------------

def test_example_conf_exists():
    """.project-conf.toml.example must exist at the repo root."""
    assert EXAMPLE_CONF.is_file(), (
        ".project-conf.toml.example is missing from the repo root. "
        "Create it as a fully-commented example config for new users."
    )


def test_example_conf_is_valid_toml():
    """.project-conf.toml.example must parse as valid TOML."""
    if not EXAMPLE_CONF.is_file():
        pytest.skip(".project-conf.toml.example absent — failing in test_example_conf_exists")
    content = EXAMPLE_CONF.read_text()
    try:
        tomllib.loads(content)
    except tomllib.TOMLDecodeError as exc:
        pytest.fail(f".project-conf.toml.example is not valid TOML: {exc}")


def test_example_conf_has_harvest_schedule():
    """.project-conf.toml.example must contain a harvest_schedule key under [hooks]."""
    if not EXAMPLE_CONF.is_file():
        pytest.skip(".project-conf.toml.example absent — failing in test_example_conf_exists")
    content = EXAMPLE_CONF.read_text()
    assert "harvest_schedule" in content, (
        ".project-conf.toml.example is missing 'harvest_schedule' — "
        "add it under [hooks] with both HH:MM and 5-field cron examples."
    )


def test_example_conf_has_required_sections():
    """.project-conf.toml.example must document all major config sections."""
    if not EXAMPLE_CONF.is_file():
        pytest.skip(".project-conf.toml.example absent — failing in test_example_conf_exists")
    content = EXAMPLE_CONF.read_text()
    required = [
        "[status_labels]",
        "[code-graph]",
        "[pr_review]",
        "[workflow]",
        "[hooks]",
        "[autonomous]",
    ]
    missing = [s for s in required if s not in content]
    assert not missing, (
        f".project-conf.toml.example is missing sections: {missing}. "
        "The example file must document every config section."
    )


def test_example_conf_harvest_schedule_in_hooks_section():
    """.project-conf.toml.example must place harvest_schedule inside [hooks], not elsewhere."""
    if not EXAMPLE_CONF.is_file():
        pytest.skip(".project-conf.toml.example absent — failing in test_example_conf_exists")
    content = EXAMPLE_CONF.read_text()
    assert re.search(r'\[hooks\].*harvest_schedule', content, re.DOTALL), (
        ".project-conf.toml.example has 'harvest_schedule' but not inside a [hooks] section. "
        "The key must appear after a [hooks] header."
    )


def test_example_conf_documents_hhmm_format():
    """.project-conf.toml.example must show HH:MM format for harvest_schedule."""
    if not EXAMPLE_CONF.is_file():
        pytest.skip(".project-conf.toml.example absent — failing in test_example_conf_exists")
    content = EXAMPLE_CONF.read_text()
    # Must show at least one HH:MM-style example (e.g. "02:00" or "04:00")
    assert re.search(r'"[0-2]\d:[0-5]\d"', content), (
        ".project-conf.toml.example must include an HH:MM example value for "
        "harvest_schedule (e.g. \"02:00\")."
    )


def test_example_conf_documents_5field_cron_format():
    """.project-conf.toml.example must show the 5-field cron form for harvest_schedule."""
    if not EXAMPLE_CONF.is_file():
        pytest.skip(".project-conf.toml.example absent — failing in test_example_conf_exists")
    content = EXAMPLE_CONF.read_text()
    # Match a 5-field cron expression in a string (e.g. "0 2 * * *")
    assert re.search(r'"[0-9*,/-]+ [0-9*,/-]+ [0-9*,/-]+ [0-9*,/-]+ [0-9*,/-]+"', content), (
        ".project-conf.toml.example must include a 5-field cron example for harvest_schedule "
        "(e.g. \"0 2 * * *\") in addition to the HH:MM form."
    )


def test_example_conf_documents_disabled_form():
    """.project-conf.toml.example must document the empty-string disabled form."""
    if not EXAMPLE_CONF.is_file():
        pytest.skip(".project-conf.toml.example absent — failing in test_example_conf_exists")
    content = EXAMPLE_CONF.read_text()
    # Either shows harvest_schedule = "" or has a comment about empty = disabled
    has_empty_value = re.search(r'harvest_schedule\s*=\s*""', content)
    has_disable_comment = "disabled" in content.lower() and "harvest_schedule" in content
    assert has_empty_value or has_disable_comment, (
        ".project-conf.toml.example must document how to disable the harvest schedule "
        "(either harvest_schedule = \"\" or a comment explaining empty = disabled)."
    )


# ---------------------------------------------------------------------------
# Item 2 — skills/gh-init/SKILL.md: harvest schedule step
# ---------------------------------------------------------------------------

def test_ghinit_has_harvest_step():
    """skills/gh-init/SKILL.md (or its references/) must document a harvest schedule step."""
    text = _skill_text("gh-init")
    assert "harvest" in text.lower(), (
        "skills/gh-init/ contains no harvest-schedule step. "
        "Add a Step 10 asking whether to set up nightly harvest, then running "
        "slopstop-schedule-harvest on 'y'."
    )


def test_ghinit_references_schedule_harvest_script():
    """gh-init skill must reference the slopstop-schedule-harvest script."""
    text = _skill_text("gh-init")
    assert "slopstop-schedule-harvest" in text, (
        "skills/gh-init/ does not reference 'slopstop-schedule-harvest'. "
        "Step 10 must call or mention the script so users know how to re-run it."
    )


def test_ghinit_harvest_step_numbered_step10():
    """gh-init skill must add the harvest step as Step 10 (after Step 9)."""
    text = _skill_text("gh-init")
    assert "Step 10" in text or "step 10" in text.lower(), (
        "skills/gh-init/ does not contain 'Step 10'. "
        "The harvest schedule step must be numbered Step 10 (after the existing Step 9 output)."
    )


def test_ghinit_harvest_step_prompts_hhmm():
    """gh-init harvest step must prompt the user for an HH:MM time."""
    text = _skill_text("gh-init")
    if "harvest" not in text.lower():
        pytest.skip("no harvest step present — failing in test_ghinit_has_harvest_step")
    assert "HH:MM" in text or "hh:mm" in text.lower(), (
        "skills/gh-init/ harvest step does not mention HH:MM format. "
        "The prompt must ask for a time in HH:MM (24-hour) format."
    )


def test_ghinit_harvest_step_writes_project_conf():
    """gh-init harvest step must say to write harvest_schedule to .project-conf.toml."""
    text = _skill_text("gh-init")
    if "harvest" not in text.lower():
        pytest.skip("no harvest step present — failing in test_ghinit_has_harvest_step")
    assert "harvest_schedule" in text and ".project-conf.toml" in text, (
        "skills/gh-init/ harvest step does not mention writing 'harvest_schedule' to "
        "'.project-conf.toml'. The step must describe writing the key before running the script."
    )


def test_ghinit_harvest_step_is_optional():
    """gh-init harvest step must be described as optional (y/N prompt near harvest content)."""
    text = _skill_text("gh-init")
    if "harvest" not in text.lower():
        pytest.skip("no harvest step present — failing in test_ghinit_has_harvest_step")
    # Find the paragraph/section containing harvest content and check it's optional
    lines = text.splitlines()
    harvest_lines = [i for i, l in enumerate(lines) if "harvest" in l.lower()]
    context_start = max(0, harvest_lines[0] - 5)
    context_end = min(len(lines), harvest_lines[-1] + 15)
    harvest_context = "\n".join(lines[context_start:context_end])
    assert "[y/N]" in harvest_context or "optional" in harvest_context.lower(), (
        "skills/gh-init/ harvest step must be framed as optional — "
        "include a [y/N] prompt or mark the step as optional so users can skip it."
    )


# ---------------------------------------------------------------------------
# Item 3 — design/cold-start.md §7: nightly harvest setup step
# ---------------------------------------------------------------------------

def _coldstart_section7() -> str:
    """Return the text of design/cold-start.md §7 only (between ## 7. and ## 8.)."""
    cold_start = DESIGN_DIR / "cold-start.md"
    if not cold_start.is_file():
        pytest.skip("design/cold-start.md not found")
    content = cold_start.read_text()
    # Extract §7 only — between the ## 7. heading and the next ## 8. heading
    m = re.search(r'(## 7\..+?)(?=## 8\.)', content, re.DOTALL)
    if not m:
        pytest.skip("Could not locate §7 in design/cold-start.md")
    return m.group(1)


def test_coldstart_has_harvest_schedule_section():
    """design/cold-start.md §7 must include a harvest_schedule step (not just §5 config table)."""
    section7 = _coldstart_section7()
    assert "harvest_schedule" in section7, (
        "design/cold-start.md §7 has no mention of 'harvest_schedule'. "
        "Add a Step 7 (Set up nightly harvest) that explains setting "
        "harvest_schedule in .project-conf.toml and running slopstop-schedule-harvest."
    )


def test_coldstart_references_schedule_harvest_script():
    """design/cold-start.md §7 must reference slopstop-schedule-harvest."""
    section7 = _coldstart_section7()
    assert "slopstop-schedule-harvest" in section7, (
        "design/cold-start.md §7 does not reference 'slopstop-schedule-harvest'. "
        "The harvest setup step must name the script."
    )


def test_coldstart_harvest_step_is_optional():
    """design/cold-start.md §7 harvest step must be marked optional."""
    section7 = _coldstart_section7()
    if "slopstop-schedule-harvest" not in section7:
        pytest.skip("harvest step absent — failing in test_coldstart_references_schedule_harvest_script")
    assert "optional" in section7.lower(), (
        "design/cold-start.md §7 harvest step must be marked as optional. "
        "Add '(optional)' to the step heading or include a note that it can be skipped."
    )
