"""
Phase 0 red tests for BILL-175 — /slopstop:run skeleton: launch order, agent
contract, briefs, fleet state.

Stage 3's orchestrator (design/slopstop-process.md §7a-§7b): reads the
G2-approved tree, computes the dependency-first launch order, launches one
hermetically-sealed worktree agent per leaf with the §7a brief, externalizes
fleet state to disk. Monitoring (#176), verification (#177), failure handling
(#178), and integration/report (#179) dock into this spine later.

Expected behaviors:
1. skills/run/SKILL.md exists (frontmatter, ≤350 lines), tier gate vs
   [tiers].medium, reads the run dir by run-id.
2. Launch ordering: file-affinity + explicit relations, detailed in
   references/run-launch-order.md.
3. Agent brief in references/run-agent-brief.md: :plan --ticket-driven
   --inline, :pr --inline, decline the PR, never :merge, $TRACKING_DIR
   carve-out, reporting protocol, same-size adversary at adversary_effort,
   stuck exit, TICKET UNDERSPECIFIED marker awareness.
4. Router: healthy -> ANTHROPIC_BASE_URL injection + run-id per request;
   disabled/down -> direct with the degradation note. Health check happens at
   EACH agent launch.
5. Fleet state at scratch/runs/<run-id>/fleet-state.md — the source of truth,
   updated on every event.
6. Installer + manifests include run (parity).

Test command:
    python3 -m pytest tests/test_bill175_behaviors.py -v
"""

import json
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent
SKILL = REPO_ROOT / "skills" / "run" / "SKILL.md"
REFS = REPO_ROOT / "skills" / "run" / "references"
INSTALL = REPO_ROOT / "install-for-claude-desktop.sh"
PLUGIN_JSON = REPO_ROOT / ".claude-plugin" / "plugin.json"


@pytest.fixture(scope="module")
def spine():
    assert SKILL.exists(), "skills/run/SKILL.md must exist (BILL-175)"
    return SKILL.read_text()


@pytest.fixture(scope="module")
def brief():
    path = REFS / "run-agent-brief.md"
    assert path.exists(), "references/run-agent-brief.md must exist"
    return path.read_text()


@pytest.fixture(scope="module")
def launch_order():
    path = REFS / "run-launch-order.md"
    assert path.exists(), "references/run-launch-order.md must exist"
    return path.read_text()


def test_frontmatter_line_limit_tier_gate(spine):
    frontmatter = spine.split("---", 2)[1]
    assert "description:" in frontmatter
    assert "disable-model-invocation: true" in frontmatter
    assert len(spine.splitlines()) <= 350
    assert "[tiers]" in spine and "medium" in spine
    assert "hard stop" in spine.lower() or "hard-stop" in spine.lower()


def test_reads_run_dir(spine):
    assert "scratch/runs/" in spine
    assert "run-id" in spine.lower() or "$RUN_ID" in spine


def test_launch_order_reference(spine, launch_order):
    assert "run-launch-order.md" in spine
    assert "file" in launch_order.lower() and "affinity" in launch_order.lower()
    assert "disjoint" in launch_order.lower()
    assert "blocked" in launch_order.lower() or "explicit" in launch_order.lower()


def test_brief_contract(brief):
    """The brief carries every §7a hard constraint.

    :plan and :pr each carry --inline independently. Asserting a bare
    "--inline" would be subsumed by the :plan arg string and could never
    fail on its own.
    """
    assert 'args="--ticket-driven --inline"' in brief  # :plan
    assert 'args="--inline"' in brief  # :pr, separately
    assert "DECLINE" in brief or "decline" in brief
    assert "slopstop:merge" in brief  # the do-NOT-run instruction names it
    assert "$TRACKING_DIR" in brief
    assert "adversary_effort" in brief
    assert "TICKET UNDERSPECIFIED" in brief
    assert "stuck" in brief.lower()
    assert "rebase" in brief.lower()  # git-behavior constraint


def test_brief_names_steps_as_skill_tool_calls(brief):
    """Steps must be Skill tool calls, never bare slash text.

    A headless `claude -p` session has no SlashCommand tool, so a line like
    `/slopstop:start BILL-202` in the prompt is inert prose. Observed at the
    haiku fleet tier: one agent replied "Waiting for /slopstop-start to
    complete…" and exited having done nothing; another skipped :start and
    :plan entirely and improvised implementation code.

    The source names the plugin namespace (slopstop:); the installer rewrites
    it to slopstop- for a commands install. See test_installer_rewrites_refs.
    """
    for step in ("slopstop:start", "slopstop:plan", "slopstop:update", "slopstop:pr"):
        assert f'Skill(skill="{step}"' in brief, f"{step} must be named as a Skill tool call"


def test_brief_tells_agent_to_trust_its_own_skill_list(brief):
    """Belt and braces for a mixed or unexpected install namespace.

    The instruction must not spell out the alternative separator literally:
    the installer's sed would rewrite that example too, leaving the installed
    brief telling the agent to prefer a dash over a dash.
    """
    assert "available-skills list" in brief
    assert "trust the list" in brief


def test_installer_rewrites_refs_not_just_the_spine():
    """References are shipped to ~/.claude/commands too, and must be rewritten.

    run-agent-brief.md tells the agent to call Skill(skill="slopstop:start").
    In a commands install only `slopstop-start` exists. Copying the reference
    verbatim hands a headless agent a skill name that does not resolve.
    """
    MARKER = "Installing slopstop skill references"
    for script in (INSTALL, REPO_ROOT / "install-for-claude-desktop-local.sh"):
        text = script.read_text()
        # Without this the split below returns the WHOLE file and the guards go vacuous.
        assert MARKER in text, f"{script.name} lost the references-section marker"
        refs_half = text.split(MARKER)[-1]
        assert 'sed "${SED_ARGS[@]}"' in refs_half, (
            f"{script.name} must apply the namespace rewrite to references"
        )
        assert "cp " not in refs_half, (
            f"{script.name} copies references verbatim — they must go through SED_ARGS"
        )


def test_installers_never_leave_a_truncated_reference():
    """`sed src > dst` truncates dst before reading src, and under `set -e` an
    unguarded sed aborts the whole install. Both installers must write through a
    temp file inside the `if` condition so a failed re-run leaves the previously
    installed reference intact.
    """
    for script in (INSTALL, REPO_ROOT / "install-for-claude-desktop-local.sh"):
        refs_half = script.read_text().split("Installing slopstop skill references")[-1]
        assert 'if [ -f "$ref_src" ] && sed' in refs_half or "&& sed" in refs_half, (
            f"{script.name} runs sed unguarded — set -e aborts the install on failure"
        )
        assert ".tmp" in refs_half and "mv " in refs_half, (
            f"{script.name} must sed into a temp file and mv it into place"
        )


def test_brief_forbids_bare_slash_steps(brief):
    """No step may be given as slash text the agent is expected to 'run'."""
    body = brief.split("```")[1]  # the templated prompt itself, not the prose around it
    offenders = [
        line.strip()
        for line in body.splitlines()
        if re.match(r"^\s*/slopstop[:-](start|plan|update|pr)\b", line)
    ]
    assert not offenders, f"brief tells the agent to run inert slash text: {offenders}"


def test_brief_declares_printing_a_step_name_a_failure(brief):
    """The weakest fleet tier needs the failure mode spelled out, not implied."""
    low = brief.lower()
    assert "printing" in low and "failed" in low


def test_brief_forbids_inventing_the_spec(brief):
    """An agent denied the ticket read must halt, not fabricate one.

    Observed: an agent wrote a task_plan whose "Original description" was
    invented from the PRD, placing the module at cmd/router/ on port 8888,
    when the ticket said router/ and 8484.
    """
    low = brief.lower()
    assert "do not infer" in low or "do not guess" in low
    assert "invent" in low  # constraint 8's ban on routing around a denied tool


def test_router_injection_per_launch(spine):
    assert "[fleet.router]" in spine
    assert "ANTHROPIC_BASE_URL" in spine
    assert "each agent launch" in spine.lower() or "every agent launch" in spine.lower()
    assert "cost tracking" in spine.lower()


def test_fleet_state_externalized(spine):
    assert "fleet-state.md" in spine
    assert "source of truth" in spine.lower()


def test_agents_config_consumed(spine):
    """Model/effort come from [fleet.agents]."""
    assert "[fleet.agents]" in spine


def test_launch_recipe_grants_the_tools_the_base_process_needs(spine):
    """acceptEdits auto-approves file edits only — not Bash.

    Under it a fleet agent cannot read its ticket, transition it, comment, or
    push: the entire base process is denied. `auto` alone still gates `gh`.
    The recipe must pair a permission mode with a scoped --allowedTools grant,
    and must not reach for a blanket bypass.
    """
    assert "--permission-mode acceptEdits" not in spine, (
        "acceptEdits cannot run the base process — it denies Bash"
    )
    assert "--allowedTools" in spine, "the scoped grant is what makes the mode workable"
    assert "Bash(gh:*)" in spine, "gh is what the ticket-system steps need"
    assert "[fleet.agents].allowed_tools" in spine, (
        "the process-wide base grant belongs in config, not hardcoded in the recipe"
    )
    assert "bypassPermissions" in spine, "the recipe must say why NOT to reach for it"


def test_launch_recipe_grants_the_tracking_dir(spine):
    """A relative tracking_dir resolves from the MAIN worktree root.

    So it always lies outside the agent's own worktree, and the launch must
    --add-dir it. An agent denied its tracking dir was observed inventing a
    local .local-tracking/ rather than halting.
    """
    assert "--add-dir" in spine
    assert "git-common-dir" in spine, "the recipe must explain why the dir is outside"


def test_launch_recipe_warns_off_the_protected_claude_path(spine):
    """~/.claude refuses writes even with a matching --add-dir."""
    assert "~/.claude/" in spine and "protected" in spine.lower()


def test_launch_recipe_enforces_effort(spine):
    """The CLI takes --model and --effort; effort is enforced, not advisory.

    Asserted against the launch command itself, not the prose around it —
    the prose is allowed to mention the superseded ANTHROPIC_MODEL= form.
    """
    blocks = [b for b in re.findall(r"```bash\n(.*?)```", spine, re.S) if "claude -p" in b]
    assert blocks, "no fenced bash block contains the `claude -p` launch command"
    cmd = blocks[0]
    assert "--model" in cmd and "--effort" in cmd
    assert "ANTHROPIC_MODEL=" not in cmd, "superseded by --model in the launch command"


def test_installer_and_manifests():
    script = INSTALL.read_text()
    skills_line = next(ln for ln in script.splitlines() if ln.startswith("SKILLS=("))
    assert " run" in skills_line or "(run" in skills_line
    plugin = json.loads(PLUGIN_JSON.read_text())
    assert ":run" in plugin["description"]
