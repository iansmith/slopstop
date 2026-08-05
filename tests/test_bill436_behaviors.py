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

MIN_BODY_LINES = 30
MAX_BODY_LINES = 350


def _read(path):
    return path.read_text(encoding="utf-8", errors="replace")


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


def test_review_is_deliberately_not_installed_to_desktop():
    """Desktop must NOT get /slopstop-review, and the reason is mechanical.

    RED at Phase 0: the guard below is inverted relative to the first draft of this
    suite, which asserted the opposite.

    The installers strip frontmatter unconditionally:

        NR==1 && /^---$/ { in_fm=1; next }
        in_fm && /^---$/ { in_fm=0; next }
        in_fm { next }

    So `context: fork` — the entire mechanism — is deleted on the way to
    ~/.claude/commands/slopstop-review.md. Shipping it would install a review that runs
    in the caller's session while looking like the isolated one: strictly worse than not
    shipping it, because it fails silently.

    That is the right outcome anyway. Desktop is interactive, so a human is present and
    the bundled /code-review — measured faster and better on 2026-08-04 — is available.
    The forked skill exists for autonomous and fleet runs, where nobody can type it.
    """
    on_disk = {p.name for p in SKILLS_DIR.iterdir() if (p / "SKILL.md").is_file()}
    for installer in INSTALLERS:
        assert installer.is_file(), f"missing {installer.name}"
        m = re.search(r"^SKILLS=\(([^)]*)\)", _read(installer), re.M)
        assert m, f"no SKILLS=( ... ) array in {installer.name}"
        listed = set(m.group(1).split())

        assert "review" not in listed, (
            f"{installer.name} ships 'review' to Desktop, where frontmatter is stripped "
            "and `context: fork` is lost — the command would silently self-review"
        )
        missing = sorted(on_disk - listed - {"review"})
        assert not missing, (
            f"{installer.name}: skill(s) on disk but not installed: {missing}"
        )


def test_both_installers_declare_the_same_skill_set():
    """One definition, two files (universal §5). Nothing checked they agree.

    RED at Phase 0: only vacuously green today — they are byte-identical. It becomes
    load-bearing the moment this ticket edits one, which it must.
    """
    arrays = {}
    for installer in INSTALLERS:
        m = re.search(r"^SKILLS=\(([^)]*)\)", _read(installer), re.M)
        assert m, f"no SKILLS=( ... ) array in {installer.name}"
        arrays[installer.name] = set(m.group(1).split())
    names = list(arrays)
    assert arrays[names[0]] == arrays[names[1]], (
        f"installer skill sets differ: only in {names[0]}: "
        f"{sorted(arrays[names[0]] - arrays[names[1]])}; only in {names[1]}: "
        f"{sorted(arrays[names[1]] - arrays[names[0]])}"
    )


@pytest.mark.parametrize(
    "skill",
    sorted(d.name for d in SKILLS_DIR.iterdir() if (d / "references").is_dir()),
)
def test_every_read_pointer_resolves(skill):
    """No skill points at a reference file that does not exist.

    RED at Phase 0 for `pr` once pr-simplify.md is deleted — pr/SKILL.md:54 still carries
    its `→ Read` pointer. Currently green; it is the guard that makes the deletion safe.

    Uses conftest.reachable_references, which has existed since BILL-325 with ZERO
    consumers after the 2026-08-01 prune. The repo already had the machinery to catch a
    dangling pointer and was not running it.
    """
    _, broken = reachable_references(skill)
    assert not broken, f"skills/{skill} points at missing reference(s): {broken}"
