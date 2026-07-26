"""The `[code-graph]` / SCIP feature is not shipping — no surface may advertise it.

slopstop briefly documented per-project SCIP indexer configuration: a
`[code-graph]` section in `.project-conf.toml`, a `[tools]` section in
`~/.slopstop/config.toml`, and two shell helpers mapping languages to indexer
binaries. The feature was dropped. Documentation for a feature that does not
exist is worse than no documentation — a reader who configures `[code-graph]`
gets silence, not an error, and spends real time working out why.

The README section was removed in 3.7.0; this guard covers every remaining
surface so it cannot creep back in. CHANGELOG.md is exempt (it records the
removal, and past entries describe releases in which the feature was real) and
so is walkthrough/ (it quotes a transcript verbatim).
"""

import re
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent

# Everything a user or a developer reads that is not a historical record.
SHIPPED_DOCS = [
    REPO_ROOT / "README.md",
    REPO_ROOT / "CONFIG.md",
    REPO_ROOT / "QUICKSTART.md",
    REPO_ROOT / "SETUP-GUIDE.md",
    REPO_ROOT / ".project-conf.toml.example",
    REPO_ROOT / ".gitignore",
    REPO_ROOT / ".claude-plugin" / "plugin.json",
    REPO_ROOT / ".claude-plugin" / "marketplace.json",
]
SHIPPED_TREES = [REPO_ROOT / "skills", REPO_ROOT / "bin"]

# `code-graph`/`code_graph` in any casing, and `scip` only as a whole word —
# an unanchored `scip` matches "discipline", which is why the first draft of
# this sweep reported false hits in prose that had nothing to do with indexing.
FEATURE = re.compile(r"code[-_]graph|\bscip\w*\b", re.IGNORECASE)


def _shipped_files():
    files = [p for p in SHIPPED_DOCS if p.is_file()]
    for tree in SHIPPED_TREES:
        if tree.is_dir():
            files.extend(p for p in tree.rglob("*") if p.is_file())
    return files


def _hits():
    out = []
    for f in _shipped_files():
        try:
            text = f.read_text()
        except UnicodeDecodeError:
            continue  # binary artifact; not a doc surface
        for n, line in enumerate(text.splitlines(), 1):
            if FEATURE.search(line):
                out.append(f"{f.relative_to(REPO_ROOT)}:{n}: {line.strip()[:100]}")
    return out


def test_no_code_graph_references_in_shipped_surfaces():
    hits = _hits()
    assert not hits, (
        f"The code-graph/SCIP feature is not shipping, but {len(hits)} reference(s) "
        "survive in user- or developer-facing files:\n  " + "\n  ".join(hits)
    )


def test_no_stray_scip_index_artifacts():
    """`index.scip` was a build artifact of the dropped feature."""
    strays = [p.name for p in REPO_ROOT.glob("*.scip")]
    assert not strays, f"Leftover SCIP index artifacts in the repo root: {strays}"
