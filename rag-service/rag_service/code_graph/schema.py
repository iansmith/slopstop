"""AGE code graph schema constants and pure classification helpers.

Defines the vertex labels, edge types, and property key constants for the
Apache AGE property graph (the ``code_graph`` graph bootstrapped by
``docker/postgres-pgvector/schema/004_age.sql``), plus two pure functions
that classify SCIP symbol descriptors into vertex labels and determine
callability.

Design decisions (BILL-54):
  - One global ``code_graph`` with a ``repo`` property on every vertex —
    simpler than per-repo sub-graphs; multi-repo queries filter by ``repo``.
  - MERGE key = full SCIP moniker string — stable, versioned for external
    deps, idempotent across re-indexes.
  - Vertex types come from the SCIP descriptor *suffix* as the primary
    signal because ``kind`` is only populated by ``scip-go``; ``scip-python``
    and ``scip-typescript`` both emit empty ``kind`` fields. ``kind`` is used
    as an override when present (most importantly to identify Go's
    ``MethodSpecification``, which shares the ``.`` suffix with ``Field``).
  - External stub vertices (``VERTEX_EXTERNAL``) are required: 33 % of calls
    in a real Go repo target external / stdlib symbols that have no
    ``SymbolInformation`` in the index.
  - Test-origin symbols are tagged ``test: true`` rather than using a
    separate vertex label, so queries can include or exclude them uniformly.

Grounded in ``design/scip-code-graph-spike.md`` (Parts 1–3).
"""

from __future__ import annotations

import re

# ---------------------------------------------------------------------------
# Vertex labels
# ---------------------------------------------------------------------------

VERTEX_PACKAGE: str = "Package"
"""Namespace or module.  Descriptor suffix: ``/``."""

VERTEX_FILE: str = "File"
"""Source file.  Created from ``document.relative_path`` entries in the index;
not from a symbol descriptor suffix."""

VERTEX_TYPE: str = "Type"
"""Struct, interface, or class.  Descriptor suffix: ``#``."""

VERTEX_FUNCTION: str = "Function"
"""Function, method, constructor, or interface-method specification.
Descriptor suffix: ``().`` (all indexers) or ``.`` + ``kind=MethodSpecification``
(Go only)."""

VERTEX_FIELD: str = "Field"
"""Struct field or class attribute.  Descriptor suffix: ``.`` (default when
no ``kind`` hint disambiguates from ``MethodSpecification``)."""

VERTEX_EXTERNAL: str = "External"
"""Stub vertex for a symbol that is *referenced* in the index but whose
``SymbolInformation`` is absent (e.g. stdlib, third-party, cross-module dep).
Created during ingest so CALLS edges always have a target."""

# ---------------------------------------------------------------------------
# Edge types
# ---------------------------------------------------------------------------

EDGE_CONTAINS: str = "CONTAINS"
"""Structural containment: ``Package → Type → Method/Field``, or
``File → Symbol`` (for symbols defined in that file)."""

EDGE_DEFINES: str = "DEFINES"
"""``File`` → symbol, from definition occurrences (``role & 1``)."""

EDGE_CALLS: str = "CALLS"
"""Caller → callee, reconstructed via ``enclosing_range`` containment of
call-site occurrences."""

EDGE_IMPLEMENTS: str = "IMPLEMENTS"
"""Type → Type (struct implements interface) and Function → Function
(concrete method implements interface-method spec), from
``is_implementation`` relationships."""

EDGE_REFERENCES: str = "REFERENCES"
"""General usage edge: symbol → symbol, from read-access occurrences
(``role & 8``) that are not CALLS."""

EDGE_TOUCHES: str = "TOUCHES"
"""Commit → File or Function.  Written by the commit-provenance pipeline
(BILL-56); ``change_type`` (added/modified/deleted) and ``hunks`` (int)
are properties on the edge."""

# ---------------------------------------------------------------------------
# Vertex labels (continued)
# ---------------------------------------------------------------------------

VERTEX_COMMIT: str = "Commit"
"""A git commit.  MERGE key is ``(sha, repo)``; properties: ``sha``,
``repo``, ``subject``, ``author``, ``authored_at`` (ISO-8601),
``ticket_ids`` (list of ticket-key strings)."""

VERTEX_REPO: str = "Repo"
"""One per repository.  MERGE key is ``repo`` (e.g. ``"iansmith/slopstop"``).
Updated by every successful full index; ``last_indexed_sha`` records the HEAD
at index time so slopstop-ingest can skip re-indexing when HEAD is unchanged
(reconcile-on-start, BILL-59)."""

PROP_LAST_INDEXED_SHA: str = "last_indexed_sha"
"""HEAD SHA stored on the :Repo vertex after each successful full index."""

# ---------------------------------------------------------------------------
# Property key constants
# (used by the ingester and query layer to avoid raw string literals)
# ---------------------------------------------------------------------------

PROP_MONIKER: str = "moniker"
"""Full SCIP moniker string — the MERGE key and the primary lookup field."""

PROP_FILE_PATH: str = "file_path"
"""Repository-relative path of the file where this symbol is defined."""

PROP_RANGE: str = "range"
"""Name-token range ``[startLine, startChar, endChar]`` (or 4-element for
multi-line) — the location to jump to when navigating to a definition."""

PROP_ENCLOSING_RANGE: str = "enclosing_range"
"""Full body span of a function/method.  Used for CALLS reconstruction:
a call-site occurrence whose position falls inside this range belongs to
this function as its caller."""

PROP_LANG: str = "lang"
"""Source language, derived from ``metadata.tool_info.name``
(``scip-go`` → ``go``, ``scip-python`` → ``python``,
``scip-typescript`` → ``typescript``)."""

PROP_EXTERNAL: str = "external"
"""Boolean.  ``True`` on ``VERTEX_EXTERNAL`` stub vertices."""

PROP_TEST: str = "test"
"""Boolean.  ``True`` when the symbol originates from a test file
(e.g. ``_test.go``, ``*_test.py``, ``*.test.ts``)."""

PROP_REPO: str = "repo"
"""Repository identifier (e.g. ``iansmith/slopstop``).  Present on every
vertex so the single global ``code_graph`` supports multi-repo queries via
``WHERE repo = 'X'``."""

PROP_SHA: str = "sha"
"""Git commit SHA (full 40-char hex).  Part of the MERGE key for Commit vertices."""

PROP_SUBJECT: str = "subject"
"""First line of a git commit message (the commit subject)."""

PROP_AUTHOR: str = "author"
"""Commit author display name."""

PROP_AUTHORED_AT: str = "authored_at"
"""Commit author timestamp, ISO-8601 (e.g. ``"2026-06-03T19:53:21Z"``)."""

PROP_TICKET_IDS: str = "ticket_ids"
"""List of ticket key strings parsed from ``[BILL-N]`` commit subjects and
``Refs:`` trailers.  Stored on Commit vertices."""

PROP_CHANGE_TYPE: str = "change_type"
"""One of ``"added"``, ``"modified"``, or ``"deleted"`` — stored on TOUCHES edges."""

PROP_HUNKS: str = "hunks"
"""Number of diff hunks in a TOUCHES edge (integer ≥ 1)."""

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_LOCAL_RE = re.compile(r"^local \d+$")

#: kind values that map unambiguously to VERTEX_FUNCTION
_FUNCTION_KINDS = frozenset(
    {"Function", "Method", "MethodSpecification", "Constructor"}
)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def vertex_type_from_descriptor(
    descriptor: str, kind: str | None = None
) -> str | None:
    """Return the AGE vertex label for a SCIP symbol descriptor.

    ``kind`` is populated by ``scip-go`` only; ``scip-python`` and
    ``scip-typescript`` leave it empty.  The function therefore uses the
    descriptor *suffix* as the primary classification signal and accepts
    ``kind`` as a tiebreaker for the one ambiguity the suffix cannot resolve.

    Args:
        descriptor: The SCIP symbol descriptor string (the portion after the
            ``<scheme> <manager> <package> <version>`` prefix in a moniker).
            Examples: ``"Circle#"``, ``"Circle#Area()."```, ``"local 0"``.
        kind: Optional ``SymbolInformation.kind`` string from the SCIP index.
            Only used to resolve the single ambiguous case: Go
            ``MethodSpecification`` uses the ``.`` suffix (same as ``Field``)
            but must be classified as ``VERTEX_FUNCTION``.  For all other
            ``kind`` values the descriptor suffix already gives the correct
            answer and ``kind`` is ignored.

    Returns:
        One of the ``VERTEX_*`` constants, or ``None`` if the symbol should
        be skipped (function-scoped locals, unrecognised descriptors).
    """
    # Function-scoped locals are not globally addressable — skip.
    if _LOCAL_RE.match(descriptor):
        return None

    # kind tiebreaker — only for the one case the suffix cannot resolve:
    # Go MethodSpecification uses "." (same as Field) but is a Function.
    # For every other kind value the suffix below is reliable and sufficient.
    if descriptor.endswith(".") and kind == "MethodSpecification":
        return VERTEX_FUNCTION

    # Descriptor-suffix (portable across all three indexers).
    # Check most-specific suffix first so "()." doesn't fall through to ".".
    if descriptor.endswith("()."):
        return VERTEX_FUNCTION
    if descriptor.endswith("/"):
        return VERTEX_PACKAGE
    if descriptor.endswith("#"):
        return VERTEX_TYPE
    if descriptor.endswith("."):
        # Ambiguous: could be Field or Go MethodSpecification.
        # Without a kind hint we default to Field (safe; the ingester can
        # correct via kind when available).
        return VERTEX_FIELD

    # Unknown descriptor shape (e.g. generics with [T], parameter `().(x)`).
    # Return None so callers can log-and-skip rather than crashing.
    return None


def is_callable(descriptor: str, kind: str | None = None) -> bool:
    """Return True if this SCIP symbol should be the target of a CALLS edge.

    Portable rule (spike Part 2, divergence #2):
      callable if ``descriptor`` ends in ``().`` **or** ``kind`` is in
      ``{Function, Method, MethodSpecification, Constructor}``.

    This handles the key cross-indexer difference: Go interface method
    *specifications* use the ``.`` suffix (not ``().``) but carry
    ``kind=MethodSpecification``; TypeScript and Python interface methods
    use ``().`` like concrete methods.

    Args:
        descriptor: SCIP symbol descriptor string.
        kind: Optional ``SymbolInformation.kind`` string.

    Returns:
        ``True`` if the symbol can appear as a callee in a CALLS edge.
    """
    return descriptor.endswith("().") or kind in _FUNCTION_KINDS
