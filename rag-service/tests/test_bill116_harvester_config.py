"""BILL-116: Red tests for ~/.harvester.toml relocation and project-key auto-derive.

Tests for two behaviors introduced in BILL-116:
  a) HARVESTER_TOML env-var makes load_harvester_conf() use a custom path.
  b) _resolve_project_keys() auto-derives project key from .project-conf.toml
     when no --project flag or JIRA_PROJECT_KEYS env var is set.

These tests do NOT touch psycopg, postgres, models, or network.
"""

from __future__ import annotations

import pytest


# ---------------------------------------------------------------------------
# a) HARVESTER_TOML env-var override for load_harvester_conf
# ---------------------------------------------------------------------------


def test_load_harvester_conf_uses_harvester_toml_env_var(monkeypatch, tmp_path):
    """HARVESTER_TOML env var redirects load_harvester_conf to a custom path."""
    conf_file = tmp_path / "mycreds.toml"
    conf_file.write_bytes(b'[linear]\napi_key = "lin_api_test"\n')
    monkeypatch.setenv("HARVESTER_TOML", str(conf_file))

    from rag_service.harvesters._common import load_harvester_conf

    result = load_harvester_conf()
    assert result.get("linear", {}).get("api_key") == "lin_api_test"


def test_load_harvester_conf_ignores_env_var_when_explicit_path_given(monkeypatch, tmp_path):
    """Explicit config_path beats HARVESTER_TOML env var."""
    env_file = tmp_path / "from_env.toml"
    env_file.write_bytes(b'[linear]\napi_key = "from_env"\n')
    explicit_file = tmp_path / "explicit.toml"
    explicit_file.write_bytes(b'[linear]\napi_key = "from_explicit"\n')
    monkeypatch.setenv("HARVESTER_TOML", str(env_file))

    from rag_service.harvesters._common import load_harvester_conf

    result = load_harvester_conf(config_path=str(explicit_file))
    assert result.get("linear", {}).get("api_key") == "from_explicit"


def test_load_harvester_conf_returns_empty_dict_when_env_path_missing(monkeypatch, tmp_path):
    """HARVESTER_TOML pointing to a nonexistent file is treated as missing (returns {})."""
    monkeypatch.setenv("HARVESTER_TOML", str(tmp_path / "nonexistent.toml"))
    monkeypatch.delenv("JIRA_PROJECT_KEYS", raising=False)

    from rag_service.harvesters._common import load_harvester_conf

    result = load_harvester_conf()
    assert result == {}


# ---------------------------------------------------------------------------
# b) _resolve_project_keys auto-derives prefix from .project-conf.toml
# ---------------------------------------------------------------------------


def test_resolve_project_keys_reads_prefix_from_project_conf(monkeypatch, tmp_path):
    """When no env var or --project, prefix is read from .project-conf.toml in cwd."""
    project_conf = tmp_path / ".project-conf.toml"
    project_conf.write_bytes(b'system = "jira"\nkey = "lyos"\nprefix = "PLTF"\n')
    monkeypatch.delenv("JIRA_PROJECT_KEYS", raising=False)
    monkeypatch.setenv("HARVESTER_TOML", str(tmp_path / "nonexistent.toml"))

    from rag_service.harvesters.jira import _resolve_project_keys

    result = _resolve_project_keys(cwd=str(tmp_path))
    assert result == ["PLTF"]


def test_resolve_project_keys_env_var_beats_project_conf(monkeypatch, tmp_path):
    """JIRA_PROJECT_KEYS env var takes precedence over .project-conf.toml."""
    project_conf = tmp_path / ".project-conf.toml"
    project_conf.write_bytes(b'prefix = "PLTF"\n')
    monkeypatch.setenv("JIRA_PROJECT_KEYS", "FOO,BAR")

    from rag_service.harvesters.jira import _resolve_project_keys

    result = _resolve_project_keys(cwd=str(tmp_path))
    assert result == ["FOO", "BAR"]


def test_resolve_project_keys_falls_back_to_harvester_toml_when_no_project_conf(
    monkeypatch, tmp_path
):
    """When .project-conf.toml is absent, falls back to .harvester.toml project_keys."""
    harvester_conf = tmp_path / ".harvester.toml"
    harvester_conf.write_bytes(b'[jira]\nproject_keys = ["SERV"]\n')
    monkeypatch.delenv("JIRA_PROJECT_KEYS", raising=False)

    from rag_service.harvesters.jira import _resolve_project_keys

    result = _resolve_project_keys(config_path=str(harvester_conf), cwd=str(tmp_path))
    assert result == ["SERV"]


def test_resolve_project_keys_project_conf_beats_harvester_toml(monkeypatch, tmp_path):
    """When both .project-conf.toml and .harvester.toml exist, project-conf wins."""
    project_conf = tmp_path / ".project-conf.toml"
    project_conf.write_bytes(b'prefix = "PLTF"\n')
    harvester_conf = tmp_path / ".harvester.toml"
    harvester_conf.write_bytes(b'[jira]\nproject_keys = ["SERV"]\n')
    monkeypatch.delenv("JIRA_PROJECT_KEYS", raising=False)

    from rag_service.harvesters.jira import _resolve_project_keys

    result = _resolve_project_keys(config_path=str(harvester_conf), cwd=str(tmp_path))
    assert result == ["PLTF"]


def test_resolve_project_keys_returns_empty_when_nothing_configured(monkeypatch, tmp_path):
    """With no env var, no .project-conf.toml, and no .harvester.toml, returns []."""
    monkeypatch.delenv("JIRA_PROJECT_KEYS", raising=False)
    empty_harvester = tmp_path / ".harvester.toml"
    empty_harvester.write_bytes(b"")

    from rag_service.harvesters.jira import _resolve_project_keys

    result = _resolve_project_keys(cwd=str(tmp_path), config_path=str(empty_harvester))
    assert result == []


def test_resolve_project_keys_ignores_project_conf_without_prefix(monkeypatch, tmp_path):
    """A .project-conf.toml lacking 'prefix' does not produce a spurious key."""
    project_conf = tmp_path / ".project-conf.toml"
    project_conf.write_bytes(b'system = "github"\nkey = "owner/repo"\n')
    harvester_conf = tmp_path / ".harvester.toml"
    harvester_conf.write_bytes(b'[jira]\nproject_keys = ["SERV"]\n')
    monkeypatch.delenv("JIRA_PROJECT_KEYS", raising=False)

    from rag_service.harvesters.jira import _resolve_project_keys

    result = _resolve_project_keys(config_path=str(harvester_conf), cwd=str(tmp_path))
    assert result == ["SERV"]
