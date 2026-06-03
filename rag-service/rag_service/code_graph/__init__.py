"""AGE code graph — schema constants and pure classification helpers.

Public API re-exported from :mod:`rag_service.code_graph.schema`.

Usage::

    from rag_service.code_graph import (
        VERTEX_FUNCTION, EDGE_CALLS,
        vertex_type_from_descriptor, is_callable,
    )

See :mod:`rag_service.code_graph.schema` for the full symbol list and
design rationale (BILL-54).
"""

from rag_service.code_graph.schema import (
    # Vertex labels
    VERTEX_PACKAGE,
    VERTEX_FILE,
    VERTEX_TYPE,
    VERTEX_FUNCTION,
    VERTEX_FIELD,
    VERTEX_EXTERNAL,
    # Edge types
    EDGE_CONTAINS,
    EDGE_DEFINES,
    EDGE_CALLS,
    EDGE_IMPLEMENTS,
    EDGE_REFERENCES,
    # Property keys
    PROP_MONIKER,
    PROP_FILE_PATH,
    PROP_RANGE,
    PROP_ENCLOSING_RANGE,
    PROP_LANG,
    PROP_EXTERNAL,
    PROP_TEST,
    PROP_REPO,
    # Pure helpers
    vertex_type_from_descriptor,
    is_callable,
)

__all__ = [
    "VERTEX_PACKAGE",
    "VERTEX_FILE",
    "VERTEX_TYPE",
    "VERTEX_FUNCTION",
    "VERTEX_FIELD",
    "VERTEX_EXTERNAL",
    "EDGE_CONTAINS",
    "EDGE_DEFINES",
    "EDGE_CALLS",
    "EDGE_IMPLEMENTS",
    "EDGE_REFERENCES",
    "PROP_MONIKER",
    "PROP_FILE_PATH",
    "PROP_RANGE",
    "PROP_ENCLOSING_RANGE",
    "PROP_LANG",
    "PROP_EXTERNAL",
    "PROP_TEST",
    "PROP_REPO",
    "vertex_type_from_descriptor",
    "is_callable",
]
