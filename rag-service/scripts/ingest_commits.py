r"""Host-side script: mine ticket-referenced commits and POST commit provenance
to the rag-service /code-graph/ingest-commits endpoint.

Usage:
    python3 -m scripts.ingest_commits --repo owner/repo [options]

Options:
    --repo REPO         Repository identifier, e.g. "iansmith/slopstop" (required).
    --prefix PREFIX     Ticket prefix to search for in commit messages, e.g.
                        "BILL" (default: auto-detect from .project-conf.toml).
    --since-sha SHA     Only process commits reachable after this SHA
                        (exclusive; passed to git log as SHA..HEAD).
    --rag-url URL       rag-service base URL (default: http://localhost:7777).
    --dry-run           Print payloads without POSTing them.
    --git-dir DIR       Path to the git repository (default: current directory).

Design (BILL-56):
    - Finds ticket-referenced commits via:  git log --all --grep='\[PREFIX-[0-9]'
    - Extracts per-file diff stats with:    git diff-tree --name-status + diff --unified=0
    - Sends one CommitIngestRequest per commit.
    - changed_lines are 0-indexed (SCIP convention); git diff hunk headers are
      1-indexed, so the script subtracts 1 from each start line.

Run this on the host (not inside the Docker container) because it needs access
to the git history.  The rag container must be running for the POST to succeed.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

_DEFAULT_RAG_URL = "http://localhost:7777"
_TICKET_RE = re.compile(r"\[([A-Z]+-\d+)\]")
_REFS_RE = re.compile(r"^(?:Refs|Closes):\s*([A-Z]+-\d+)", re.MULTILINE)
_HUNK_RE = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")


def _run(cmd: list[str], cwd: Path) -> str:
    result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, check=True)
    return result.stdout


def _git_log_shas(prefix: str, since_sha: str | None, cwd: Path) -> list[str]:
    """Return SHAs of ticket-referenced commits, most-recent-first."""
    grep = rf"\[{prefix}-[0-9]"
    cmd = ["git", "log", "--all", "--format=%H", f"--grep={grep}"]
    if since_sha:
        cmd += [f"{since_sha}..HEAD"]
    out = _run(cmd, cwd)
    return [s.strip() for s in out.splitlines() if s.strip()]


def _git_show_meta(sha: str, cwd: Path) -> dict:
    """Return commit metadata dict for a given SHA."""
    fmt = "%H%n%s%n%an%n%aI%n%B"
    out = _run(["git", "show", "-s", f"--format={fmt}", sha], cwd)
    lines = out.split("\n", 4)
    full_sha = lines[0].strip()
    subject = lines[1].strip()
    author = lines[2].strip()
    authored_at = lines[3].strip()
    body = lines[4] if len(lines) > 4 else ""

    ticket_ids = sorted(set(_TICKET_RE.findall(subject) + _REFS_RE.findall(body)))
    return {
        "sha": full_sha,
        "subject": subject,
        "author": author,
        "authored_at": authored_at,
        "ticket_ids": ticket_ids,
    }


def _parse_hunk_lines(diff_output: str) -> list[list[int]]:
    """Extract 0-indexed [start_line, end_line] pairs from unified diff hunks."""
    ranges: list[list[int]] = []
    for line in diff_output.splitlines():
        m = _HUNK_RE.match(line)
        if m:
            start_1indexed = int(m.group(1))
            count = int(m.group(2)) if m.group(2) is not None else 1
            if count == 0:
                continue  # Pure deletion — no added lines
            start_0 = start_1indexed - 1
            end_0 = start_0 + count - 1
            ranges.append([start_0, end_0])
    return ranges


def _git_diff_files(sha: str, cwd: Path) -> list[dict]:
    """Return per-file change info for a commit.

    Uses git diff-tree to list changed files, then git diff for line ranges.
    change_type: 'added' (A), 'modified' (M/R), 'deleted' (D).
    changed_lines: 0-indexed, or None for deletions (no added lines).
    """
    # diff-tree: one line per file — status letter + tab + path(s)
    dt_out = _run(
        ["git", "diff-tree", "--no-commit-id", "-r", "--name-status", sha], cwd
    )
    files: list[dict] = []
    for line in dt_out.splitlines():
        if not line.strip():
            continue
        parts = line.split("\t", 1)
        if len(parts) < 2:
            continue
        status_raw, path_raw = parts[0].strip(), parts[1].strip()
        status = status_raw[0]  # A / M / D / R / C — take first char

        if status == "D":
            # Deletion: no added lines to track
            files.append(
                {"path": path_raw, "change_type": "deleted", "hunks": 1, "changed_lines": None}
            )
            continue

        change_type = "added" if status == "A" else "modified"

        # For renames, path_raw may be "old_path\tnew_path"; take the new path.
        if "\t" in path_raw:
            path_raw = path_raw.split("\t")[-1]

        # Get unified diff for hunk header parsing.
        try:
            diff_out = _run(
                ["git", "diff", "--unified=0", f"{sha}^", sha, "--", path_raw],
                cwd,
            )
        except subprocess.CalledProcessError:
            # Root commit or other edge case — no parent.
            diff_out = _run(
                ["git", "show", "--unified=0", sha, "--", path_raw], cwd
            )

        changed_lines = _parse_hunk_lines(diff_out)
        hunks = len(changed_lines)
        files.append(
            {
                "path": path_raw,
                "change_type": change_type,
                "hunks": max(hunks, 1),
                "changed_lines": changed_lines if changed_lines else None,
            }
        )
    return files


def _post(url: str, payload: dict) -> dict:
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode())


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--repo", required=True, help="Repository identifier (owner/repo)")
    p.add_argument("--prefix", default="BILL", help="Ticket prefix (default: BILL)")
    p.add_argument("--since-sha", default=None, help="Only process commits after this SHA")
    p.add_argument("--rag-url", default=_DEFAULT_RAG_URL)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--git-dir", default=".", type=Path)
    args = p.parse_args(argv)

    cwd = args.git_dir.resolve()
    endpoint = f"{args.rag_url.rstrip('/')}/code-graph/ingest-commits"

    shas = _git_log_shas(args.prefix, args.since_sha, cwd)
    if not shas:
        print(f"No {args.prefix}-referenced commits found.", file=sys.stderr)
        return 0

    print(f"Found {len(shas)} ticket-referenced commits. Ingesting...", file=sys.stderr)
    total_commits = 0
    total_touches = 0

    for sha in shas:
        meta = _git_show_meta(sha, cwd)
        files = _git_diff_files(sha, cwd)
        if not files:
            continue

        payload = {**meta, "repo": args.repo, "files": files}

        if args.dry_run:
            print(json.dumps(payload, indent=2))
            continue

        try:
            resp = _post(endpoint, payload)
            total_commits += resp.get("commits_merged", 0)
            total_touches += resp.get("touches_merged", 0)
            print(
                f"  {sha[:12]}  {meta['subject'][:60]}  "
                f"+{resp.get('touches_merged', 0)} touches"
            )
        except urllib.error.URLError as e:
            print(f"  ERROR {sha[:12]}: {e}", file=sys.stderr)

    if not args.dry_run:
        print(f"\nDone: {total_commits} commits, {total_touches} TOUCHES edges merged.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
