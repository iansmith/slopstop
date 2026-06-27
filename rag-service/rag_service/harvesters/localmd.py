"""Local Markdown harvester — indexes design/ docs into ticket_chunks.

Walks a directory tree, finds *.md files, splits them into per-section chunks
at ## heading boundaries (H2), and ingests them via the standard embed/write
pipeline.  Designed for long-lived design documents; not recommended for
high-churn scratchpad directories.

Source taxonomy
---------------
source     = "design"
provenance = "local"
kind       = "section"
ticket_id  = relative path from the repo root, e.g. "design/auth-flow.md"
project    = repo name passed by the caller, e.g. "mobile-v2"

Usage
-----
    # Sync one repo's design/ dir
    python3 -m rag_service.harvesters.localmd sync ~/lyos/mobile-v2/design mobile-v2

    # Sync multiple
    python3 -m rag_service.harvesters.localmd sync ~/lyos/mobile-v2/design mobile-v2
    python3 -m rag_service.harvesters.localmd sync ~/lyos/server-v2/design server-v2

Credentials: reads pgdata / embedder config from ~/.harvester.toml (same as
other harvesters).  No network calls; all content is local.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from rag_service.harvesters._common import (
    ChunkRow,
    embed_rows,
    open_conn,
    strip_code_blocks,
    write_ticket,
)

# ---------------------------------------------------------------------------
# Chunking constants
# ---------------------------------------------------------------------------

# Markdown H2 heading — split here.  H1 is treated as a preamble, not a split.
_H2_RE = re.compile(r"^## .+", re.MULTILINE)

# A chunk this short is merged forward into the next section rather than
# written as a standalone row (avoids one-liner "## See also" noise).
_MIN_CHUNK_CHARS = 80

# Hard cap per chunk.  Sections exceeding this are split on blank lines.
_MAX_CHUNK_CHARS = 900


# ---------------------------------------------------------------------------
# Pure chunking logic
# ---------------------------------------------------------------------------


def _merge_short_sections(sections: list[str]) -> list[str]:
    """Merge sections shorter than _MIN_CHUNK_CHARS into a neighbour.

    Prefers merging forward (into the next section); falls back to merging
    backward (into the previous) when there is no next section.
    """
    merged: list[str] = []
    skip_next = False
    for i, section in enumerate(sections):
        if skip_next:
            skip_next = False
            continue
        if len(section) < _MIN_CHUNK_CHARS:
            if i + 1 < len(sections):
                merged.append(section + "\n\n" + sections[i + 1])
                skip_next = True
            elif merged:
                merged[-1] = merged[-1] + "\n\n" + section
            else:
                merged.append(section)
        else:
            merged.append(section)
    return merged


def _split_oversized(sections: list[str]) -> list[str]:
    """Split any section exceeding _MAX_CHUNK_CHARS on blank-line boundaries."""
    result: list[str] = []
    for section in sections:
        if len(section) <= _MAX_CHUNK_CHARS:
            result.append(section)
            continue
        paragraphs = re.split(r"\n{2,}", section)
        chunk = ""
        for para in paragraphs:
            candidate = (chunk + "\n\n" + para).strip() if chunk else para
            if len(candidate) > _MAX_CHUNK_CHARS and chunk:
                result.append(chunk)
                chunk = para
            else:
                chunk = candidate
        if chunk:
            result.append(chunk)
    return result


def _split_sections(text: str) -> list[str]:
    """Split markdown prose into H2-bounded sections.

    The preamble before the first H2 (including the H1 title) is included as
    the first section when it meets the minimum length.  Pass prose with code
    blocks already stripped.
    """
    boundaries = [m.start() for m in _H2_RE.finditer(text)]
    if not boundaries:
        return [text.strip()] if text.strip() else []
    starts = [0] + boundaries
    ends = boundaries + [len(text)]
    raw = [text[s:e].strip() for s, e in zip(starts, ends)]
    merged = _merge_short_sections([s for s in raw if s])
    return [s for s in _split_oversized(merged) if s]


def build_chunks(
    md_path: Path,
    repo_root: Path,
    project: str,
    source: str = "design",
) -> list[ChunkRow]:
    """Convert one markdown file into a list of ChunkRows (no embedding yet)."""
    text = md_path.read_text(encoding="utf-8", errors="replace")
    prose, _code_blocks = strip_code_blocks(text)
    rel = str(md_path.relative_to(repo_root))
    sections = _split_sections(prose)

    return [
        ChunkRow(
            source=source,
            ticket_id=rel,
            provenance="local",
            kind="section",
            seq=i,
            text=section,
            code_refs=[],
            ticket_refs=[],
            repo=project,
        )
        for i, section in enumerate(sections)
    ]


# ---------------------------------------------------------------------------
# Ingestion
# ---------------------------------------------------------------------------


def sync_directory(
    design_dir: Path,
    project: str,
    repo_root: Path | None = None,
    source: str = "design",
) -> None:
    """Walk *design_dir*, embed all .md files in one batch, and upsert into ticket_chunks."""
    from rag_service.embed import get_embedder

    if repo_root is None:
        repo_root = design_dir.parent

    md_files = sorted(design_dir.rglob("*.md"))
    if not md_files:
        print(f"No .md files found under {design_dir}", file=sys.stderr)
        return

    print(f"Syncing {len(md_files)} files from {design_dir} (project={project})")

    # Build rows for all files; collect (ticket_id, rows) pairs for writing.
    all_rows: list[ChunkRow] = []
    file_rows: list[tuple[str, list[ChunkRow]]] = []
    for md_path in md_files:
        rows = build_chunks(md_path, repo_root, project, source=source)
        if not rows:
            rel = str(md_path.relative_to(repo_root))
            print(f"  skip {rel} (no content)")
            continue
        all_rows.extend(rows)
        file_rows.append((rows[0].ticket_id, rows))

    if not all_rows:
        return

    # Single embedding pass over all rows.
    embedder = next(get_embedder())
    embed_rows(all_rows, embedder)

    conn = open_conn()
    try:
        for ticket_id, rows in file_rows:
            n = write_ticket(
                conn,
                rows,
                source=source,
                ticket_id=ticket_id,
                provenance="local",
            )
            print(f"  {ticket_id}: {n} chunk(s)")
    finally:
        conn.close()

    print("Done.")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Index local markdown design docs into ticket_chunks."
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    sync = sub.add_parser("sync", help="Sync a design directory into the RAG DB.")
    sync.add_argument("directory", help="Path to the design/ directory to index.")
    sync.add_argument("project", help="Project label, e.g. 'mobile-v2'.")
    return p


def main(argv: list[str] | None = None) -> None:
    args = _build_parser().parse_args(argv)
    if args.cmd == "sync":
        design_dir = Path(args.directory).expanduser().resolve()
        if not design_dir.is_dir():
            sys.exit(f"Not a directory: {design_dir}")
        sync_directory(design_dir, args.project)


if __name__ == "__main__":
    main()
