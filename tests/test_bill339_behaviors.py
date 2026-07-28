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
    """Locate the skills/ file that names and describes the posting procedure."""
    candidates = list((SKILLS).rglob("*.md"))
    for path in candidates:
        text = path.read_text()
        if "umbrella ticket" in text.lower() and re.search(
            r"\bpost(s|ing)?\b.*\b(prd|charter)\b|\b(prd|charter)\b.*\bpost(s|ing)?\b",
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

    def references_procedure(text):
        return any(name in text for name in procedure_names) or "archiv" in text.lower()

    assert references_procedure(run_text), (
        "run-final-report.md does not reference the archiving procedure."
    )
    assert references_procedure(merge_text), (
        "merge-archive-chain.md does not reference the archiving procedure."
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


def test_no_umbrella_case_documented():
    found = list(_find_archiving_procedure_file())
    assert found, "No archiving procedure file found (see prior test)."
    combined = "\n".join(p.read_text() for p in found)
    assert re.search(r"no umbrella|freestanding|single.ticket", combined, re.IGNORECASE), (
        "Archiving procedure does not document what happens when the run has no "
        "umbrella ticket."
    )
