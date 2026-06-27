"""Unit tests for the local-markdown harvester (BILL-118).

All Layer-1 — no postgres, no embedder, no filesystem writes outside tmp_path.
Exercises _split_sections and build_chunks directly.
"""

import textwrap
from pathlib import Path

import pytest

from rag_service.harvesters.localmd import _split_sections, build_chunks, _MAX_CHUNK_CHARS, _MIN_CHUNK_CHARS


# ---------------------------------------------------------------------------
# _split_sections
# ---------------------------------------------------------------------------


def test_split_sections_single_h2():
    md = textwrap.dedent("""\
        # Title

        Preamble text that is long enough to survive the minimum threshold and
        should appear as the first chunk in the output list.

        ## Section One

        Content for section one goes here and must be at least a few sentences
        to exceed the minimum threshold and be kept as a standalone chunk.
    """)
    sections = _split_sections(md)
    assert len(sections) == 2
    assert "Preamble" in sections[0]
    assert "Section One" in sections[1]


def test_split_sections_no_headings():
    md = "Just some prose without any headings.\n\nMore prose here."
    sections = _split_sections(md)
    assert len(sections) == 1
    assert "prose" in sections[0]


def test_split_sections_empty_file():
    sections = _split_sections("")
    assert sections == []


def test_split_sections_short_section_merged_forward():
    """A section under _MIN_CHUNK_CHARS is merged into the next section."""
    short = "## See also\n\nShort."
    long_next = (
        "## Next Section\n\n"
        + "This section has enough content to stand on its own. " * 5
    )
    md = short + "\n\n" + long_next
    sections = _split_sections(md)
    # The short "See also" should be merged into "Next Section"
    assert len(sections) == 1
    assert "See also" in sections[0]
    assert "Next Section" in sections[0]


def test_split_sections_oversized_section_split_on_blank_lines():
    """A section exceeding _MAX_CHUNK_CHARS is split at blank lines."""
    para = "Word " * 60  # ~300 chars per paragraph
    big_section = "## Big Section\n\n" + ("\n\n".join([para] * 6))
    assert len(big_section) > _MAX_CHUNK_CHARS
    sections = _split_sections(big_section)
    assert len(sections) > 1
    for s in sections:
        assert len(s) <= _MAX_CHUNK_CHARS + len(para)  # one para overshoot allowed


def test_split_sections_multiple_h2():
    md = textwrap.dedent("""\
        # Doc Title

        Intro paragraph that is long enough to survive as a standalone preamble
        chunk and should not be merged with the first H2 section below it.

        ## Alpha

        Alpha content is here and has enough text to not be merged forward into
        the next section because it exceeds the minimum chunk character count.

        ## Beta

        Beta content is here and similarly has sufficient length to be retained
        as a standalone chunk in the output from _split_sections.

        ## Gamma

        Gamma content rounds out the test with enough text to survive as its
        own section in the final output list returned by the function.
    """)
    sections = _split_sections(md)
    headings = [s for s in sections if s.startswith("## ")]
    assert len(headings) == 3
    assert any("Alpha" in s for s in sections)
    assert any("Beta" in s for s in sections)
    assert any("Gamma" in s for s in sections)


# ---------------------------------------------------------------------------
# build_chunks
# ---------------------------------------------------------------------------


def test_build_chunks_basic(tmp_path):
    design_dir = tmp_path / "design"
    design_dir.mkdir()
    md = design_dir / "auth-flow.md"
    md.write_text(textwrap.dedent("""\
        # Auth Flow

        Overview of the authentication flow used by the mobile app.

        ## Silent Login

        The silent login coordinator attempts token refresh on foreground resume
        and returns a result object with tokensRefreshed and shouldClearAuth.

        ## Hard Logout

        Hard logout clears all tokens and navigates to the sign-in screen,
        which is distinct from soft logout that only clears the access token.
    """))

    rows = build_chunks(md, tmp_path, "mobile-v2")

    assert len(rows) >= 2
    for row in rows:
        assert row.source == "design"
        assert row.ticket_id == "design/auth-flow.md"
        assert row.provenance == "local"
        assert row.kind == "section"
        assert row.repo == "mobile-v2"
        assert row.embedding is None  # not embedded yet
    seqs = [r.seq for r in rows]
    assert seqs == list(range(len(rows)))


def test_build_chunks_relative_path_uses_repo_root(tmp_path):
    """ticket_id is relative to repo_root, not design_dir."""
    repo_root = tmp_path
    design_dir = tmp_path / "design" / "subsystem"
    design_dir.mkdir(parents=True)
    md = design_dir / "deep.md"
    md.write_text(
        "# Deep Doc\n\n"
        + "Content " * 30
        + "\n\n## Section\n\n"
        + "More content " * 20
    )

    rows = build_chunks(md, repo_root, "server-v2")
    assert all(r.ticket_id == "design/subsystem/deep.md" for r in rows)


def test_build_chunks_empty_file(tmp_path):
    design_dir = tmp_path / "design"
    design_dir.mkdir()
    md = design_dir / "empty.md"
    md.write_text("")
    rows = build_chunks(md, tmp_path, "mobile-v2")
    assert rows == []


def test_build_chunks_project_label_set(tmp_path):
    design_dir = tmp_path / "design"
    design_dir.mkdir()
    md = design_dir / "doc.md"
    md.write_text("# Doc\n\n" + "Content " * 40 + "\n\n## Section\n\n" + "Text " * 30)
    rows = build_chunks(md, tmp_path, "server-v2")
    assert all(r.repo == "server-v2" for r in rows)
