"""
Phase 0 red tests for BILL-136 — remove RAG system, return to skills-only architecture.

The RAG service (rag-service/, docker/postgres-pgvector/, mcp-server/), all harvest
infrastructure, and the search/know skills are stripped. Skills that referenced RAG
are cleaned. The result is a repo that contains only skill markdown files, tests for
those skills, and supporting config — no Python service, no Docker, no pgvector.

Expected behaviors after implementation:
1.  rag-service/ directory does not exist
2.  docker/postgres-pgvector/ directory does not exist
3.  mcp-server/ directory does not exist
4.  skills/search/ directory does not exist
5.  skills/know/ directory does not exist
6.  .harvester.toml does not exist
7.  .harvester.toml.example does not exist
8.  search.sh does not exist
9.  bin/slopstop-rag-start does not exist
10. bin/slopstop-schedule-harvest does not exist
11. bin/slopstop-ingest does not exist
12. bin/slopstop-install-hooks does not exist
13. .project-conf.toml has no [code-graph] section
14. .project-conf.toml has no harvest_schedule key
15. install-for-claude-desktop.sh does not reference slopstop-search
16. install-for-claude-desktop.sh does not reference slopstop-know
17. skills/archive/SKILL.md has no re-harvest step (Step 3 gone)
18. skills/archive/SKILL.md has no RAG health check reference
19. skills/archive/SKILL.md Step 5 confirm output has no "Text harvest" line
20. skills/plan/references/plan-adversary-gaps.md has no search_tickets reference
21. skills/plan/references/plan-red-tests.md has no search_tickets or RAG reference
22. skills/plan/references/plan-explore-prompt.md has no search_tickets reference
23. skills/plan/references/plan-explore-prompt.md has no get_callers or get_implementors reference
24. skills/pr/references/pr-cc-gate.md has no RAG or rag-service reference
25. skills/gh-init/SKILL.md has no RAG setup steps
26. design/ticket-rag.md does not exist
27. design/rag-service-testing.md does not exist
28. design/scip-code-graph-spike.md does not exist
29. design/hooks-post-commit.md does not exist
30. .claude/settings.local.json does not reference slopstop-rag
31. .claude/rules/repo-conventions.md has no rag-service section
32. Makefile has no rag- targets
33. tests/test_bill90_behaviors.py does not exist
34. tests/test_bill98_behaviors.py does not exist
35. tests/test_bill100_behaviors.py does not exist
36. tests/test_bill130_behaviors.py does not exist
37. tests/test_bill132_behaviors.py does not exist

These tests FAIL on current code and turn GREEN once the implementation is complete.

Test command:
    python3 -m pytest tests/test_bill136_behaviors.py -v
"""

from pathlib import Path
import pytest

REPO_ROOT = Path(__file__).parent.parent
SKILLS_DIR = REPO_ROOT / "skills"
DESIGN_DIR = REPO_ROOT / "design"
TESTS_DIR = REPO_ROOT / "tests"


# ---------------------------------------------------------------------------
# Directories that must be gone
# ---------------------------------------------------------------------------

def test_rag_service_dir_removed():
    assert not (REPO_ROOT / "rag-service").exists(), \
        "rag-service/ directory must be removed"


def test_docker_pgvector_dir_removed():
    assert not (REPO_ROOT / "docker" / "postgres-pgvector").exists(), \
        "docker/postgres-pgvector/ directory must be removed"


def test_mcp_server_dir_removed():
    assert not (REPO_ROOT / "mcp-server").exists(), \
        "mcp-server/ directory must be removed"


def test_skills_search_dir_removed():
    assert not (SKILLS_DIR / "search").exists(), \
        "skills/search/ (semantic ticket search skill) must be removed"


def test_skills_know_dir_removed():
    assert not (SKILLS_DIR / "know").exists(), \
        "skills/know/ (symbol knowledge skill) must be removed"


# ---------------------------------------------------------------------------
# Config and script files that must be gone
# ---------------------------------------------------------------------------

def test_harvester_toml_removed():
    assert not (REPO_ROOT / ".harvester.toml").exists(), \
        ".harvester.toml must be removed"


def test_harvester_toml_example_removed():
    assert not (REPO_ROOT / ".harvester.toml.example").exists(), \
        ".harvester.toml.example must be removed"


def test_search_sh_removed():
    assert not (REPO_ROOT / "search.sh").exists(), \
        "search.sh must be removed"


def test_bin_rag_start_removed():
    assert not (REPO_ROOT / "bin" / "slopstop-rag-start").exists(), \
        "bin/slopstop-rag-start must be removed"


def test_bin_schedule_harvest_removed():
    assert not (REPO_ROOT / "bin" / "slopstop-schedule-harvest").exists(), \
        "bin/slopstop-schedule-harvest must be removed"


def test_bin_ingest_removed():
    assert not (REPO_ROOT / "bin" / "slopstop-ingest").exists(), \
        "bin/slopstop-ingest must be removed"


def test_bin_install_hooks_removed():
    assert not (REPO_ROOT / "bin" / "slopstop-install-hooks").exists(), \
        "bin/slopstop-install-hooks must be removed"


# ---------------------------------------------------------------------------
# .project-conf.toml — no code-graph or harvest_schedule
# ---------------------------------------------------------------------------

def _project_conf():
    return (REPO_ROOT / ".project-conf.toml").read_text()


def test_project_conf_no_code_graph_section():
    assert "[code-graph]" not in _project_conf(), \
        ".project-conf.toml must not contain [code-graph] section"


def test_project_conf_no_harvest_schedule():
    assert "harvest_schedule" not in _project_conf(), \
        ".project-conf.toml must not contain harvest_schedule key"


# ---------------------------------------------------------------------------
# install-for-claude-desktop.sh — no search or know skills
# ---------------------------------------------------------------------------

def _install_script():
    return (REPO_ROOT / "install-for-claude-desktop.sh").read_text()


def test_install_script_no_slopstop_search():
    assert "slopstop-search" not in _install_script(), \
        "install-for-claude-desktop.sh must not reference slopstop-search"


def test_install_script_no_slopstop_know():
    assert "slopstop-know" not in _install_script(), \
        "install-for-claude-desktop.sh must not reference slopstop-know"


# ---------------------------------------------------------------------------
# skills/archive/SKILL.md — RAG harvest step removed
# ---------------------------------------------------------------------------

def _archive_skill():
    return (SKILLS_DIR / "archive" / "SKILL.md").read_text()


def test_archive_skill_no_reharvest_step():
    text = _archive_skill()
    assert "Re-harvest" not in text and "re-harvest" not in text, \
        "skills/archive/SKILL.md must not contain re-harvest step (Step 3 removed)"


def test_archive_skill_no_rag_health_check():
    text = _archive_skill()
    assert "rag_health" not in text and "RAG service" not in text, \
        "skills/archive/SKILL.md must not reference RAG health check"


def test_archive_skill_no_text_harvest_confirm():
    assert "Text harvest:" not in _archive_skill(), \
        "skills/archive/SKILL.md Step 5 confirm must not have 'Text harvest:' line"


# ---------------------------------------------------------------------------
# Plan reference files — no search_tickets / RAG references
# ---------------------------------------------------------------------------

def test_plan_adversary_gaps_no_search_tickets():
    text = (SKILLS_DIR / "plan" / "references" / "plan-adversary-gaps.md").read_text()
    assert "search_tickets" not in text, \
        "plan-adversary-gaps.md must not reference search_tickets"


def test_plan_red_tests_no_rag_references():
    text = (SKILLS_DIR / "plan" / "references" / "plan-red-tests.md").read_text()
    for term in ["search_tickets", "RAG service", "rag_health", "rag-service"]:
        assert term not in text, \
            f"plan-red-tests.md must not reference RAG term '{term}'"


def test_plan_explore_prompt_no_search_tickets():
    text = (SKILLS_DIR / "plan" / "references" / "plan-explore-prompt.md").read_text()
    assert "search_tickets" not in text, \
        "plan-explore-prompt.md must not reference search_tickets"


def test_plan_explore_prompt_no_code_graph_tools():
    text = (SKILLS_DIR / "plan" / "references" / "plan-explore-prompt.md").read_text()
    assert "get_callers" not in text and "get_implementors" not in text, \
        "plan-explore-prompt.md must not reference get_callers or get_implementors"


# ---------------------------------------------------------------------------
# PR reference files — no RAG references
# ---------------------------------------------------------------------------

def test_pr_cc_gate_no_rag_references():
    path = SKILLS_DIR / "pr" / "references" / "pr-cc-gate.md"
    if path.exists():
        text = path.read_text()
        assert "rag-service" not in text and "RAG" not in text, \
            "pr-cc-gate.md must not reference RAG or rag-service"


# ---------------------------------------------------------------------------
# skills/gh-init/SKILL.md — no RAG setup steps
# ---------------------------------------------------------------------------

def test_gh_init_no_rag_setup():
    path = SKILLS_DIR / "gh-init" / "SKILL.md"
    if path.exists():
        text = path.read_text()
        assert "rag" not in text.lower() and "harvest" not in text.lower(), \
            "skills/gh-init/SKILL.md must not reference RAG setup"


# ---------------------------------------------------------------------------
# Design docs that must be deleted
# ---------------------------------------------------------------------------

def test_design_ticket_rag_removed():
    assert not (DESIGN_DIR / "ticket-rag.md").exists(), \
        "design/ticket-rag.md must be removed"


def test_design_rag_service_testing_removed():
    assert not (DESIGN_DIR / "rag-service-testing.md").exists(), \
        "design/rag-service-testing.md must be removed"


def test_design_scip_code_graph_removed():
    assert not (DESIGN_DIR / "scip-code-graph-spike.md").exists(), \
        "design/scip-code-graph-spike.md must be removed"


def test_design_hooks_post_commit_removed():
    assert not (DESIGN_DIR / "hooks-post-commit.md").exists(), \
        "design/hooks-post-commit.md must be removed"


# ---------------------------------------------------------------------------
# Configuration files — no slopstop-rag
# ---------------------------------------------------------------------------

def test_claude_settings_no_slopstop_rag():
    settings_path = REPO_ROOT / ".claude" / "settings.local.json"
    if settings_path.exists():
        assert "slopstop-rag" not in settings_path.read_text(), \
            ".claude/settings.local.json must not reference slopstop-rag"


def test_repo_conventions_no_rag_service_section():
    rules_path = REPO_ROOT / ".claude" / "rules" / "repo-conventions.md"
    if rules_path.exists():
        assert "rag-service/" not in rules_path.read_text(), \
            ".claude/rules/repo-conventions.md must not have rag-service section"


def test_makefile_no_rag_targets():
    makefile = (REPO_ROOT / "Makefile").read_text()
    for target in ["rag-build", "rag-run", "rag-clean", "rag-dev-start",
                   "rag-dev-stop", "rag-dev-status"]:
        assert target not in makefile, \
            f"Makefile must not contain RAG target '{target}'"


# ---------------------------------------------------------------------------
# Archive confirm prompt — no RAG classification reference
# ---------------------------------------------------------------------------

def test_archive_confirm_prompt_no_rag_reference():
    path = SKILLS_DIR / "archive" / "references" / "archive-confirm-prompt.md"
    if path.exists():
        text = path.read_text()
        for term in ["rag", "RAG", "harvest", "ticket_chunk"]:
            assert term not in text, \
                f"archive-confirm-prompt.md must not reference '{term}'"


# ---------------------------------------------------------------------------
# PR verification classification — no ticket search reference
# ---------------------------------------------------------------------------

def test_pr_verification_no_ticket_search():
    path = SKILLS_DIR / "pr" / "references" / "pr-verification-classification.md"
    if path.exists():
        text = path.read_text()
        assert "search_tickets" not in text and "rag_health" not in text, \
            "pr-verification-classification.md must not reference RAG search tools"


# ---------------------------------------------------------------------------
# RAG behavior test files that must be deleted
# ---------------------------------------------------------------------------

def test_bill90_behaviors_removed():
    assert not (TESTS_DIR / "test_bill90_behaviors.py").exists(), \
        "tests/test_bill90_behaviors.py (RAG schema tests) must be removed"


def test_bill98_behaviors_removed():
    assert not (TESTS_DIR / "test_bill98_behaviors.py").exists(), \
        "tests/test_bill98_behaviors.py (harvest integration tests) must be removed"


def test_bill100_behaviors_removed():
    assert not (TESTS_DIR / "test_bill100_behaviors.py").exists(), \
        "tests/test_bill100_behaviors.py (code graph tests) must be removed"


def test_bill130_behaviors_removed():
    assert not (TESTS_DIR / "test_bill130_behaviors.py").exists(), \
        "tests/test_bill130_behaviors.py (harvest scheduling tests) must be removed"


def test_bill132_behaviors_removed():
    assert not (TESTS_DIR / "test_bill132_behaviors.py").exists(), \
        "tests/test_bill132_behaviors.py (search filtering tests) must be removed"
