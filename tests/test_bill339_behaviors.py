"""
Behavior tests for BILL-339 — PRD/charter archiving to the umbrella ticket.

Design: the PRD and charter are claimed to be "archived to the umbrella ticket" in
three places (design/SKILL.md, design/slopstop-process.md §4, run-final-report.md's
Archive confirmation), but nothing performs the post. These tests pin that a named
archiving procedure exists, is reachable from both the fleet (:run) and non-fleet
(:merge) completion paths, is idempotent, reports its real outcome instead of
asserting success, documents the no-umbrella case, and that no tracked file still
makes the bare unbacked claim.

Test command:
    python3 -m pytest tests/test_bill339_behaviors.py -v
"""

import re
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
SKILLS = REPO_ROOT / "skills"

RUN_FINAL_REPORT = SKILLS / "run" / "references" / "run-final-report.md"
MERGE_ARCHIVE_CHAIN = SKILLS / "merge" / "references" / "merge-archive-chain.md"
MERGE_SKILL = SKILLS / "merge" / "SKILL.md"
DESIGN_SKILL = SKILLS / "design" / "SKILL.md"
SLOPSTOP_PROCESS = REPO_ROOT / "design" / "slopstop-process.md"


def _tracked_md_files():
    out = subprocess.run(
        ["git", "ls-files", "*.md"], cwd=REPO_ROOT, capture_output=True, text=True, check=True
    ).stdout
    return [REPO_ROOT / line for line in out.splitlines() if line]


TRACKED_MD_FILES = _tracked_md_files()

# The unbacked claim this ticket exists to kill: "archive(s) to the umbrella
# ticket" with no nearby pointer to the procedure that performs it.
UNBACKED_CLAIM_RE = re.compile(r"archiv\w* to the umbrella ticket", re.IGNORECASE)


def _find_archiving_procedure_file():
    """Locate the skills/ file that names and describes the posting procedure.

    "post" and "prd"/"charter" must appear within 200 chars of each other — an
    unbounded DOTALL match would treat any file that happens to mention "posts"
    somewhere and "PRD" somewhere else, arbitrarily far apart, as the procedure.
    """
    candidates = list((SKILLS).rglob("*.md"))
    for path in candidates:
        text = path.read_text()
        if "umbrella ticket" in text.lower() and re.search(
            r"\bpost(s|ing)?\b.{0,200}?\b(prd|charter)\b|\b(prd|charter)\b.{0,200}?\bpost(s|ing)?\b",
            text,
            re.IGNORECASE | re.DOTALL,
        ):
            yield path


def test_archiving_procedure_exists():
    found = list(_find_archiving_procedure_file())
    assert found, (
        "No file under skills/ describes a procedure that posts prd.md and "
        "charter.md to the umbrella ticket (with the posting action named, not "
        "merely asserted as done elsewhere)."
    )


def test_reachable_from_both_paths():
    run_text = RUN_FINAL_REPORT.read_text()
    merge_text = MERGE_ARCHIVE_CHAIN.read_text()

    procedure_files = list(_find_archiving_procedure_file())
    assert procedure_files, "No archiving procedure file found (see prior test)."

    procedure_names = {p.stem for p in procedure_files}

    # Both target files already contain the bare word "archive" for unrelated
    # reasons (run-final-report.md's own "Archive confirmation" line,
    # merge-archive-chain.md's prose about the :archive skill) — accepting that
    # as proof of a reference would let this test pass even if the new
    # procedure were never actually linked from either path. Require the
    # procedure file's own name/stem instead.
    def references_procedure(text):
        return any(name in text for name in procedure_names)

    assert references_procedure(run_text), (
        "run-final-report.md does not name the archiving procedure directly."
    )
    assert references_procedure(merge_text), (
        "merge-archive-chain.md does not name the archiving procedure directly."
    )


def test_archiving_is_idempotent():
    found = list(_find_archiving_procedure_file())
    assert found, "No archiving procedure file found (see prior test)."
    combined = "\n".join(p.read_text() for p in found)
    assert re.search(r"idempoten|update.{0,40}in place|not.{0,20}duplicat", combined, re.IGNORECASE), (
        "Archiving procedure does not state that re-running it updates an "
        "existing comment rather than duplicating it."
    )


def test_final_report_states_outcome():
    text = RUN_FINAL_REPORT.read_text()
    archive_section = re.search(
        r"Archive confirmation.*?(?=\n##|\n\d+\.|\Z)", text, re.IGNORECASE | re.DOTALL
    )
    assert archive_section, "run-final-report.md has no 'Archive confirmation' section."
    section_text = archive_section.group(0)
    for outcome in ("posted", "already present", "failed"):
        assert outcome in section_text.lower(), (
            f"Archive confirmation section does not name the '{outcome}' outcome; "
            "it must report the real result, not assert success."
        )


def test_no_unbacked_archiving_claim():
    offenders = []
    for path in TRACKED_MD_FILES:
        text = path.read_text()
        for match in UNBACKED_CLAIM_RE.finditer(text):
            window = text[max(0, match.start() - 300) : match.end() + 300]
            if not re.search(
                r"merge-archive-chain|run-final-report|archiving procedure|`archive[- ]?prd[- ]?charter`|posts? (it|prd|charter)",
                window,
                re.IGNORECASE,
            ):
                offenders.append(f"{path.relative_to(REPO_ROOT)}: {match.group(0)!r}")
    assert not offenders, (
        "Found unbacked 'archive(s) to the umbrella ticket' claims with no nearby "
        "pointer to the procedure that performs it:\n" + "\n".join(offenders)
    )


# Second-round review (BILL-339) found design/slopstop-process.md §8 restating the
# same unbacked claim with "attached to" instead of "archiv(e/ed)" — invisible to
# UNBACKED_CLAIM_RE's word-root match. Companion test, same intent, wider net.
UNBACKED_CLAIM_VARIANT_RE = re.compile(r"attached to the umbrella ticket", re.IGNORECASE)


def test_no_unbacked_archiving_claim_attached_wording():
    offenders = []
    for path in TRACKED_MD_FILES:
        text = path.read_text()
        for match in UNBACKED_CLAIM_VARIANT_RE.finditer(text):
            window = text[max(0, match.start() - 300) : match.end() + 300]
            if not re.search(
                r"merge-archive-chain|run-final-report|archiving procedure|`archive[- ]?prd[- ]?charter`|posts? (it|prd|charter)|document-archive-artifacts",
                window,
                re.IGNORECASE,
            ):
                offenders.append(f"{path.relative_to(REPO_ROOT)}: {match.group(0)!r}")
    assert not offenders, (
        "Found unbacked 'attached to the umbrella ticket' claims with no nearby "
        "pointer to the procedure that performs it:\n" + "\n".join(offenders)
    )


def test_no_umbrella_case_documented():
    found = list(_find_archiving_procedure_file())
    assert found, "No archiving procedure file found (see prior test)."
    combined = "\n".join(p.read_text() for p in found)
    assert re.search(
        r"no umbrella.{0,120}(skip|no-op|does not post|report(s|ed)? where|refus)"
        r"|freestanding.{0,120}(skip|no-op|does not post|report(s|ed)? where|refus)",
        combined,
        re.IGNORECASE | re.DOTALL,
    ), (
        "Archiving procedure mentions the no-umbrella case but does not specify a "
        "concrete action for it (bare keyword co-occurrence, e.g. an unrelated "
        "'single-ticket' mention elsewhere, must not satisfy this)."
    )


def test_procedure_documents_separate_comments():
    """The ticket requires the PRD and charter posted as two separate comments —
    a combined single comment would satisfy every other test in this file."""
    found = list(_find_archiving_procedure_file())
    assert found, "No archiving procedure file found (see prior test)."
    combined = "\n".join(p.read_text() for p in found)
    assert re.search(
        r"separate comments?|two comments?|each (as|in) (its|their) own comment",
        combined,
        re.IGNORECASE,
    ), (
        "Archiving procedure does not state that the PRD and charter are posted "
        "as two separate comments, not one combined comment."
    )


def test_idempotency_is_scoped_to_run_id():
    """Idempotency must be keyed on run-id, not 'does an archive comment exist at
    all' — otherwise a second run against the same umbrella ticket would match
    (and overwrite) the first run's PRD/charter comment."""
    found = list(_find_archiving_procedure_file())
    assert found, "No archiving procedure file found (see prior test)."
    combined = "\n".join(p.read_text() for p in found)
    assert re.search(r"run.?id", combined, re.IGNORECASE), (
        "Archiving procedure does not mention run-id as the key used to find/"
        "update the existing comment for this run."
    )


def test_merge_archive_chain_states_outcome():
    """The outcome-reporting requirement applies to the :merge path too, not just
    run-final-report.md — otherwise :merge could unconditionally claim success."""
    text = MERGE_ARCHIVE_CHAIN.read_text()
    for outcome in ("posted", "already present", "failed"):
        assert outcome in text.lower(), (
            f"merge-archive-chain.md does not name the '{outcome}' outcome for the "
            "PRD/charter archiving step."
        )
