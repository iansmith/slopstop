"""
Behavior tests for BILL-429 — simplify and code review as clean-context agents.

Scope note, and why this file is short.

slopstop's skills are markdown prose read by Claude, not code that executes. Most of
BILL-429's substance — four serial appliers, read-only find agents, the 5-round cap,
the severity matrix — is untestable here: the only available assertion would be that a
markdown file *contains a sentence saying* those things.

This repo has already paid for that mistake. Six threshold tests in
tests/test_cc_gate_invocation.py were green for months against a CC gate that had never
executed once, because it invoked lizard with a JSON flag lizard has never had. (Not
spelled out here: that file bans the literal string in any tracked file, and this
docstring tripped it on first run — the guard works.) Its own docstring records the
verdict: "asserting on prose cannot tell you the command works."
BILL-429 exists because Step 6 recorded `step_6: pass` with no independent context
having produced it. A prose assertion here would build a third instance of that gate.

Per Ian's ruling of 2026-08-04 (this repo only): no test may assert what markdown text
says. Surface the omission instead. The unverifiable behaviors are listed on the ticket
as explicitly not-DoD-gated and are observed by hand via
.slopstop/ticket-active/BILL-429/observation-checklist.md, which reads the harness
transcript — the one artifact the session under test does not author.

So this file pins file facts and exact-token presence/absence only.

Every test was mutation-checked by an adversary pass, then reviewed by four cleanup
agents (2026-08-04). The first draft had two tests that both went GREEN against an
implementation with zero of the ticket done. Each test now carries the mutation that
broke its predecessor. Two later near-misses are also recorded inline: counting fenced
blocks instead of `Agent(` occurrences would have failed a *correct* implementation
that used this repo's own house style, and the plugin denylist would have failed a
brief that merely cited its provenance.

Deliberately NOT here, to avoid duplicating existing coverage (universal §5):
  - `skills/pr/SKILL.md` line limit -> test_skill_structure.py::test_skill_within_line_limit[pr]
  - manifest <-> disk agreement    -> test_skill_structure.py::test_skill_manifest_matches_files[pr]

Known follow-up (raised by two reviewers, deliberately not done at Phase 0): the three
token-scan tests are standing repo-wide invariants and arguably belong in
test_structural_invariants.py, not in a ticket-named file. Moving them mid-Phase-0 would
churn the frozen set, so it belongs on its own branch per universal §3.

Test command:
    python3 -m pytest tests/test_bill429_behaviors.py -v
"""

import re

from conftest import REPO_ROOT, SKILLS_DIR

PR_DIR = SKILLS_DIR / "pr"
PR_REFS = PR_DIR / "references"
PR_SPINE = PR_DIR / "SKILL.md"
SIMPLIFY_DISPATCH = PR_REFS / "pr-simplify.md"
CLAUDE_REVIEW_DISPATCH = PR_REFS / "pr-claude-review.md"

# Agent types slopstop is permitted to name. All are built into Claude Code, so they
# work with no plugins installed at all -- the central claim of BILL-429's dependency
# withdrawal. Anything else is plugin-provided and makes the skill silently depend on
# an install slopstop does not control.
ALLOWED_SUBAGENT_TYPES = {"general-purpose", "Explore", "Plan"}

# Plugin agents slopstop must not *dispatch to*. Each lookahead exempts the citation
# form while still banning the invocation form -- #420 was specifically about the bare
# name colliding across two plugins:
#   allowed: `code-simplifier@claude-plugins-official` (provenance in a brief)
#   allowed: `scratch/pr-review-toolkit-briefs-20260802/` (the preserved source path)
#   banned:  a bare `code-simplifier` / `pr-review-toolkit`
# Without the exemptions this test fails a brief that merely records where its rules
# came from -- which the ticket's own plan says three of the four rules do.
PLUGIN_TOKEN_RES = (
    re.compile(r"code-simplifier(?!@)"),
    re.compile(r"pr-review-toolkit(?!-briefs)"),
)

# Loose on purpose. The strict `subagent_type:\s*"..."` form was mutation-broken by
# single-quoting the value; `=` and bare values evade it too.
SUBAGENT_TYPE_RE = re.compile(r'subagent_type\s*[:=]\s*["\']?([A-Za-z0-9_-]+)')
CODE_REVIEW_SKILL_RE = re.compile(r'skill\s*[:=]\s*["\']?code-review')
FENCED_RE = re.compile(r"```[^\n]*\n(.*?)```", re.DOTALL)
MD_NAME_RE = re.compile(r"([A-Za-z0-9._-]+\.md)")

DIMENSIONS = ("reuse", "simplification", "efficiency", "altitude")

# A stub tripwire, not a quality bar. Real briefs in
# scratch/pr-review-toolkit-briefs-20260802/ run 3.6-7.8 KB, so this leaves ~10x
# headroom. An empty file satisfies Path.exists(); it does not brief an agent.
# (Not a general floor for reference files -- archive-confirm-prompt.md is 379 bytes.)
MIN_BRIEF_BYTES = 400


def _read(path):
    # No encoding= and no error handling aborts the whole scan on one stray byte,
    # which reads as a green run if it happens during collection.
    return path.read_text(encoding="utf-8", errors="replace")


def _skill_markdown_files():
    """Every skill markdown file, with the non-vacuity floor built in.

    The floor lives here rather than in one caller so that every scan in this file
    gets it. `assert not offenders` cannot distinguish "nothing violated" from
    "nothing was scanned": an empty or moved skills/ tree greens every token test
    silently, which is the exact false-green this file's preamble is about.
    """
    paths = sorted(SKILLS_DIR.rglob("*.md"))
    assert paths, (
        f"no skill markdown under {SKILLS_DIR} — no scan in this file checked anything"
    )
    return paths


def _reference_files_repo_wide():
    """Every file under any skill's references/ dir, by bare filename.

    Brief lookups resolve against this rather than against skills/pr/references/
    alone: a Step 6 agent prompt legitimately cites cross-skill references such as
    gates-json.md (which lives under skills/start/references/), and scoping the
    existence check to one directory would fail a correct implementation.
    """
    return {p.name: p for p in SKILLS_DIR.rglob("references/*.md")}


def _scan(paths, matcher):
    """Collect `path:lineno -> token` for every line matching `matcher`.

    Per-line rather than whole-file because the line number is load-bearing: a red
    test whose message points at pr-simplify.md:55 is worth far more than one that
    says "somewhere in skills/".
    """
    offenders = []
    for path in paths:
        for lineno, line in enumerate(_read(path).splitlines(), start=1):
            for token in matcher(line):
                offenders.append(f"{path.relative_to(REPO_ROOT)}:{lineno} -> {token}")
    return offenders


def test_no_plugin_provided_subagent_types():
    """Every subagent_type named in skills/** is one slopstop owns.

    RED at Phase 0: pr-simplify.md:55 names "code-simplifier", a plugin-provided
    agent (#420's collision). With pr-review-toolkit withdrawn, that name resolves to
    whatever plugin happens to be installed, or to nothing.

    Kept alongside the token test below: this one is a forward-looking allowlist and
    catches a plugin name nobody has thought of yet; that one catches `code-simplifier`
    on prose lines where no subagent_type appears. Neither subsumes the other.
    """
    offenders = _scan(
        _skill_markdown_files(),
        lambda line: [
            name
            for name in SUBAGENT_TYPE_RE.findall(line)
            if name not in ALLOWED_SUBAGENT_TYPES
        ],
    )
    assert not offenders, (
        "skills/** names agent type(s) slopstop does not own:\n  "
        + "\n  ".join(offenders)
        + f"\nAllowed (built-in, no plugin required): {sorted(ALLOWED_SUBAGENT_TYPES)}"
    )


def test_no_plugin_agent_name_survives_anywhere_in_skills():
    """The dependency withdrawal must hold at every site, not just the declaration.

    RED at Phase 0: `code-simplifier` reaches Claude through three sites — the
    declaration (pr-simplify.md:55), the spine's Step 1 summary (pr/SKILL.md:53), and
    the unavailable-fallback line (pr-simplify.md:61) that tells the *user* to install
    a plugin. A subagent_type-only scan sees one of the three, so deleting that line
    alone still ships the plugin dependency.
    """
    offenders = _scan(
        _skill_markdown_files(),
        lambda line: [m.group(0) for r in PLUGIN_TOKEN_RES for m in r.finditer(line)],
    )
    assert not offenders, (
        "skills/** still dispatches to a plugin-provided agent:\n  "
        + "\n  ".join(offenders)
        + "\n(Citation forms `code-simplifier@...` and `pr-review-toolkit-briefs...` "
        "are exempt — only the bare invocation name is banned.)"
    )


def test_removed_review_machinery_is_gone_as_a_token():
    """The built-in /code-review cannot be launched by a skill.

    RED at Phase 0: six invocations survive — pr-claude-review.md:50,53,56,57,98 and
    pr/SKILL.md:115.

    /code-review is disable-model-invocation, so a skill cannot launch it; a human must
    type it. The pattern mirrors SUBAGENT_TYPE_RE's tolerance deliberately: the first
    draft hardcoded two literal strings requiring exactly one space after the colon,
    repeating in this test the very mutation the file fixed in the one above.
    Scanning skills/** rather than skills/pr/ because the invariant is repo-wide.
    """
    offenders = _scan(
        _skill_markdown_files(),
        lambda line: [m.group(0) for m in CODE_REVIEW_SKILL_RE.finditer(line)],
    )
    assert not offenders, (
        "skills/** still invokes the built-in /code-review, which is "
        "disable-model-invocation and cannot be launched by a skill:\n  "
        + "\n  ".join(offenders)
    )


def test_the_four_dimension_briefs_are_four_distinct_non_empty_files():
    """One brief per dimension means four distinct files, not one named for four.

    RED at Phase 0: pr-simplify.md references no brief files at all.

    Mutation that broke the predecessor: a single zero-byte file named
    pr-simplify-brief-reuse-simplification-efficiency-altitude.md satisfied all four
    dimension lookups and went green. Cardinality, distinctness, and byte size are file
    facts; none of them reads what a brief says.

    Filenames are not pinned beyond containing the dimension — layout is the
    implementer's call.
    """
    assert SIMPLIFY_DISPATCH.exists(), f"missing dispatch file: {SIMPLIFY_DISPATCH}"
    referenced = {
        n
        for n in MD_NAME_RE.findall(_read(SIMPLIFY_DISPATCH))
        if n != SIMPLIFY_DISPATCH.name
    }

    resolved, ambiguous, missing = {}, {}, []
    for dimension in DIMENSIONS:
        names = sorted(n for n in referenced if dimension in n.lower())
        if not names:
            missing.append(dimension)
        elif len(names) > 1:
            ambiguous[dimension] = names
        else:
            resolved[dimension] = names[0]

    assert not missing, f"no brief referenced for dimension(s): {', '.join(missing)}"
    assert not ambiguous, (
        "dimension(s) resolve to more than one brief, so which is dispatched depends "
        f"on sort order: {ambiguous}"
    )
    assert len(set(resolved.values())) == len(DIMENSIONS), (
        f"the four dimensions must map to four distinct files, got {resolved}"
    )

    on_disk = _reference_files_repo_wide()
    absent = sorted(n for n in resolved.values() if n not in on_disk)
    assert not absent, f"referenced but absent from any skill references/ dir: {absent}"

    sizes = {n: on_disk[n].stat().st_size for n in sorted(resolved.values())}
    undersized = {n: s for n, s in sizes.items() if s < MIN_BRIEF_BYTES}
    assert not undersized, (
        f"brief file(s) under {MIN_BRIEF_BYTES} bytes — an empty file passes exists() "
        f"but briefs nobody: {undersized}"
    )


def _agent_spawn_count(path):
    """Count `Agent(` occurrences inside fenced blocks, not the blocks themselves.

    Counting blocks would fail a *correct* implementation: this repo's house style
    already puts four invocations in a single fence (pr-claude-review.md:48-58 does
    exactly that with Skill()). An implementer who mirrors it would see "expected 4,
    found 1" and reformat markdown instead of changing behavior — the precise failure
    mode this file exists to prevent.
    """
    return sum(b.count("Agent(") for b in FENCED_RE.findall(_read(path)) if "Agent(" in b)


def test_simplify_dispatch_spawns_one_agent_per_dimension():
    """Step 1 dispatches four agents, each naming its brief inside the invocation.

    RED at Phase 0: pr-simplify.md has one Agent( invocation, naming a plugin agent
    and no briefs.

    Mutation that broke the predecessor: appending "We considered
    pr-simplify-brief-reuse-...md but decided against briefs entirely." turned a
    whole-file name scan green. Scoping to fenced blocks containing `Agent(` is a
    location check on a token, not a reading of prose.

    Counting four spawns catches the one-agent-four-briefs collapse. It does NOT and
    cannot establish that they run *serially* — seriality is observable only via the
    harness transcript (see the observation checklist).
    """
    blocks = [b for b in FENCED_RE.findall(_read(SIMPLIFY_DISPATCH)) if "Agent(" in b]
    assert blocks, f"{SIMPLIFY_DISPATCH.name} has no fenced Agent( block"

    dispatched = {n.lower() for b in blocks for n in MD_NAME_RE.findall(b)}
    orphaned = [d for d in DIMENSIONS if not any(d in n for n in dispatched)]
    assert not orphaned, (
        "dimension(s) whose brief is named only outside an Agent( invocation: "
        + ", ".join(orphaned)
    )

    spawns = _agent_spawn_count(SIMPLIFY_DISPATCH)
    assert spawns == len(DIMENSIONS), (
        f"expected {len(DIMENSIONS)} Agent( invocations in {SIMPLIFY_DISPATCH.name}, "
        f"found {spawns}"
    )


def test_claude_review_dispatch_spawns_agents():
    """Step 6 must spawn agents at all.

    RED at Phase 0: pr-claude-review.md contains ZERO Agent( invocations. That is the
    defect in its purest form — Step 6 has no spawn, so it can only ever have run in
    the caller's session, which is what happened on PR #411.

    Deliberately a floor (>= 1) rather than an exact count: the ticket fixes no number
    of review dimensions, unlike Step 1's four.
    """
    assert CLAUDE_REVIEW_DISPATCH.exists(), f"missing: {CLAUDE_REVIEW_DISPATCH}"
    spawns = _agent_spawn_count(CLAUDE_REVIEW_DISPATCH)
    assert spawns, (
        "pr-claude-review.md declares no Agent( invocation — Step 6 has no spawn, so "
        "it runs in the caller's session (the PR #411 failure)"
    )

    blocks = [
        b for b in FENCED_RE.findall(_read(CLAUDE_REVIEW_DISPATCH)) if "Agent(" in b
    ]
    named = {
        n
        for b in blocks
        for n in MD_NAME_RE.findall(b)
        if n != CLAUDE_REVIEW_DISPATCH.name
    }
    on_disk = _reference_files_repo_wide()
    absent = sorted(n for n in named if n not in on_disk)
    assert not absent, f"referenced but absent from any skill references/ dir: {absent}"
