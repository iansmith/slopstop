"""Behavior tests for BILL-436 — /slopstop:review as a forked skill.

slopstop hand-built agent orchestration for simplify and code review. The harness already
exposes that isolation as frontmatter: `context: fork` gives a skill its own subagent with
no conversation history. Probed 2026-08-04 — a forked skill reported NO_HISTORY, reached
the real working tree, received CLAUDE.md, and ran to completion headless inside a git
worktree invoked by slash. So the orchestration goes, and a forked skill replaces it.

Per this repo's standing rule (Ian, 2026-08-04), no test here asserts what markdown prose
*says*. These assert frontmatter fields (structured YAML), file presence/absence, body
size, exact-token absence, and installer/manifest completeness.

EXPLICITLY NOT TESTED, and not DoD-gated — surfaced rather than faked:

  - that :pr's loop is bounded at 5, exits early on clean, or records which exit it took
  - that a round actually finds anything, or that the loop converges
  - that the review is any good

All four are statements about what markdown instructs a model to do. Asserting them is the
tests/test_cc_gate_invocation.py failure mode: six tests green for months against a gate
that never ran. They are observed on real runs.

Every test below carries the mutation or wrong contract an adversary pass found in its
predecessor on 2026-08-05.

Test command:
    python3 -m pytest tests/test_bill436_behaviors.py -v
"""

import re

import pytest

from conftest import REPO_ROOT, SKILLS_DIR, reachable_references

REVIEW_SKILL = SKILLS_DIR / "review" / "SKILL.md"
PR_REFS = SKILLS_DIR / "pr" / "references"
INSTALLERS = [
    REPO_ROOT / "install-for-claude-desktop.sh",
    REPO_ROOT / "install-for-claude-desktop-local.sh",
]

ALLOWED_SUBAGENT_TYPES = {"general-purpose", "Explore", "Plan"}
SUBAGENT_TYPE_RE = re.compile(r'subagent_type\s*[:=]\s*["\']?([A-Za-z0-9_-]+)')

# Plugin-provided agent names. Exact tokens, not a reading of prose. The subagent_type
# scan alone misses these: pr/SKILL.md names "code-simplifier" in running text with no
# key at all, and pr-slop-detection.md spawns an agent with no subagent_type whatsoever.
PLUGIN_AGENT_TOKENS = ("code-simplifier", "code-reviewer")

# Flags that die with Step 1. Leaving them referenced is the dead-prose problem this
# whole line of work exists to remove.
DEAD_FLAG_TOKENS = ("--no-simplify",)

# Named defects from the /code-review pass on a362176 that are token-checkable.
# NOTE: several others from that list were never on master (they lived on the closed
# BILL-429 branch or in untracked scratch/), so their absence here is pre-existing and
# is NOT evidence this ticket removed them. Only these were actually present.
FORBIDDEN_DEFECT_TOKENS = {
    "D4 wrong merge-base": "merge-base origin/HEAD",
    "D10 broken shell": "gh pr diff #",
}

MIN_BODY_LINES = 30
MAX_BODY_LINES = 350


def _read(path):
    return path.read_text(encoding="utf-8", errors="replace")


def _skill_markdown_files():
    paths = sorted(SKILLS_DIR.rglob("*.md"))
    assert paths, f"no skill markdown under {SKILLS_DIR} — no scan here checked anything"
    return paths


def _frontmatter(path):
    """Parse the YAML frontmatter into scalars.

    Tolerant of the shapes an implementer will legitimately write: trailing `# comments`
    (the ticket's own snippet has one), quoted values, CRLF, and mixed-case booleans.
    The strict version rejected `context: fork  # the isolation` and would have produced
    a false red against a correct implementation.
    """
    text = _read(path).replace("\r\n", "\n")
    assert text.startswith("---\n"), f"{path.name} has no frontmatter block"
    end = text.find("\n---", 4)
    assert end != -1, f"{path.name} has an unterminated frontmatter block"
    out = {}
    for line in text[4:end].splitlines():
        if ":" in line and not line.startswith((" ", "\t", "#")):
            k, _, v = line.partition(":")
            v = v.split("#")[0].strip().strip("'\"").lower()
            out[k.strip()] = v
    return out


def _body(path):
    text = _read(path).replace("\r\n", "\n")
    end = text.find("\n---", 4)
    return text[end + 4:] if end != -1 else text


def test_review_skill_declares_the_fork_in_frontmatter():
    """The isolation is a frontmatter field, and the tier controls live beside it.

    RED at Phase 0: skills/review/ does not exist.

    `context: fork` is the whole design — without it the skill runs in the caller's
    session, which is the PR #411 failure verbatim. `background: false` is required
    because a gate must have its verdict in the invoking turn. `model`/`effort` replace
    what [stage_tiers] would have carried, and are the only way to reach a forked skill —
    the bare Agent tool has no effort parameter at all.
    """
    assert REVIEW_SKILL.is_file(), f"missing {REVIEW_SKILL.relative_to(REPO_ROOT)}"
    fm = _frontmatter(REVIEW_SKILL)

    assert fm.get("context") == "fork", f"context must be fork, got {fm.get('context')!r}"
    assert fm.get("background") == "false", (
        f"background must be false so :pr has the verdict in-turn, got "
        f"{fm.get('background')!r}"
    )
    assert fm.get("model"), "model must be set — it replaces [stage_tiers].review"
    assert fm.get("effort"), "effort must be set — a forked skill is the only place it reaches"
    assert "disable-model-invocation" not in fm, (
        "the review skill must stay model-invocable — :pr calls it, and marking it "
        "human-only recreates the exact blocker that forced this redesign"
    )
    assert fm.get("description"), "description is required for skill discovery"


def test_review_skill_has_a_substantive_body():
    """Frontmatter alone is not a skill.

    RED at Phase 0: the file does not exist.

    Guards the mutation that broke the predecessor: a four-line stub with correct
    frontmatter satisfied every other assertion. `review` is also outside
    test_skill_structure.py's REFACTOR_TARGETS, so no line limit or references/ check
    applies to it — this is the only size constraint it has.
    """
    assert REVIEW_SKILL.is_file(), f"missing {REVIEW_SKILL.relative_to(REPO_ROOT)}"
    n = len([ln for ln in _body(REVIEW_SKILL).splitlines() if ln.strip()])
    assert MIN_BODY_LINES <= n <= MAX_BODY_LINES, (
        f"review skill body is {n} non-blank lines; expected "
        f"{MIN_BODY_LINES}-{MAX_BODY_LINES}"
    )


def test_hand_built_simplify_orchestration_is_gone():
    """Step 1's dispatch and every brief file are deleted.

    RED at Phase 0: skills/pr/references/pr-simplify.md exists and spawns an agent.

    The glob is `pr-*brief*` rather than `pr-simplify*`: the predecessor's narrower glob
    covered the five pr-simplify-brief-* files by luck of prefix and none of the four
    pr-review-brief-* ones. Note the nine brief files never landed on master — they lived
    on the closed BILL-429 branch — so that half is green by default and is a regression
    guard, not evidence of a deletion.
    """
    stale = sorted(PR_REFS.glob("pr-simplify*.md")) + sorted(PR_REFS.glob("pr-*brief*.md"))
    assert not stale, (
        "Step 1's orchestration and brief files must be gone, found: "
        + ", ".join(p.name for p in stale)
    )


def test_no_plugin_provided_agent_is_named_anywhere():
    """No skill names an agent slopstop does not own — by type OR in prose.

    RED at Phase 0: pr-simplify.md declares `subagent_type: "code-simplifier"` and
    pr/SKILL.md names the same agent in running text with no key at all.

    A subagent_type-only scan misses both the prose mention and pr-slop-detection.md's
    spawn, which carries no subagent_type whatsoever. Exact-token absence catches what a
    key-scoped regex cannot.
    """
    offenders = []
    for path in _skill_markdown_files():
        for lineno, line in enumerate(_read(path).splitlines(), start=1):
            rel = path.relative_to(REPO_ROOT)
            for name in SUBAGENT_TYPE_RE.findall(line):
                if name not in ALLOWED_SUBAGENT_TYPES:
                    offenders.append(f"{rel}:{lineno} -> subagent_type {name!r}")
            for token in PLUGIN_AGENT_TOKENS:
                if token in line:
                    offenders.append(f"{rel}:{lineno} -> names {token!r}")
    assert not offenders, (
        "skills/** names a plugin-provided agent:\n  " + "\n  ".join(offenders)
    )


def test_no_skill_invokes_the_builtin_code_review():
    """No skill tries to launch /code-review.

    RED at Phase 0: pr-claude-review.md carries several Skill({skill: "code-review"})
    invocations.

    That skill is disable-model-invocation — a skill cannot launch it, only a human
    typing it can — so every one of those call sites was inert. Proven the hard way on
    2026-08-04: this session could not run it; the human had to.
    """
    pat = re.compile(r'skill\s*[:=]\s*["\']?code-review')
    offenders = [
        f"{p.relative_to(REPO_ROOT)}:{n}"
        for p in _skill_markdown_files()
        for n, line in enumerate(_read(p).splitlines(), start=1)
        if pat.search(line)
    ]
    assert not offenders, (
        "skills/** still invokes the built-in /code-review, which cannot be launched by "
        "a skill:\n  " + "\n  ".join(offenders)
    )


@pytest.mark.parametrize("defect,token", sorted(FORBIDDEN_DEFECT_TOKENS.items()))
def test_named_defect_token_is_absent(defect, token):
    """Defects the /code-review pass on a362176 named, that are token-checkable.

    RED at Phase 0: both are present on master — `merge-base origin/HEAD` at
    pr-simplify.md:57 (the remote's *default* branch, not $BASE, so agents reviewed a
    diff the step never measured) and `gh pr diff #` at pr-claude-review.md:18 (`#` opens
    a shell comment, so $PR is silently discarded).
    """
    offenders = [
        f"{p.relative_to(REPO_ROOT)}:{n}"
        for p in _skill_markdown_files()
        for n, line in enumerate(_read(p).splitlines(), start=1)
        if token in line
    ]
    assert not offenders, f"{defect}: token {token!r} still present:\n  " + "\n  ".join(offenders)


@pytest.mark.parametrize("token", DEAD_FLAG_TOKENS)
def test_dead_flag_is_not_referenced(token):
    """Flags that die with Step 1 must not survive in skills/**.

    RED at Phase 0: --no-simplify is referenced by pr/SKILL.md, pr-simplify.md,
    pr-slop-detection.md (which branches on it) and pr-confirm-summary.md (which prints
    an outcome string for it).
    """
    offenders = [
        f"{p.relative_to(REPO_ROOT)}:{n}"
        for p in _skill_markdown_files()
        for n, line in enumerate(_read(p).splitlines(), start=1)
        if token in line
    ]
    assert not offenders, (
        f"{token} no longer exists but is still referenced:\n  " + "\n  ".join(offenders)
    )

# ---------------------------------------------------------------------------
# Three further tests are deliberately NOT in the Phase 0 commit:
#
#   test_review_is_deliberately_not_installed_to_desktop
#   test_both_installers_declare_the_same_skill_set
#   test_every_read_pointer_resolves  (parametrized over every skill)
#
# All PASS today, and plan-phase0-mechanics.md § 0e admits only tests observed FAILING at
# 0d. They are absence/consistency guards rather than behavior claims, and each goes red
# at the moment implementation starts: deleting pr-simplify.md breaks pr/SKILL.md:54's
# `→ Read` pointer, and adding skills/review/ without an installer exclusion trips the
# Desktop check. They are added with the implementation, which § 0e sanctions ("Add tests
# freely").
#
# Parked at scratchpad/bill436-deferred-guards.py so they are not re-derived from memory.
# ---------------------------------------------------------------------------
