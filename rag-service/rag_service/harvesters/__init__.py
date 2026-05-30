"""Upstream ticket harvesters for the rag-service.

Each harvester (Linear, GitHub, JIRA) fetches a ticket from its source system,
normalizes it into the source-neutral `HarvestedTicket` shape, and feeds it
through the shared ingestion spine in `_common.py` (chunking, code/ticket-ref
extraction, embedding, full-resync DB write).

The shared spine lives here — built first by BILL-37 (Linear), reused verbatim
by BILL-32 (GitHub) and a future JIRA harvester. Source-specific code
(API clients, payload→HarvestedTicket mapping, CLI) lives in the per-source
modules (`linear.py`, `github.py`, ...).
"""

from __future__ import annotations

from rag_service.harvesters._common import (
    ChunkRow,
    ComplexityBudget,
    HarvestedComment,
    HarvestedTicket,
    RateLimiter,
    chunk_ticket,
    embed_rows,
    extract_code_refs,
    extract_ticket_refs,
    strip_code_blocks,
    synthesize_code_sentence,
    write_ticket,
)

__all__ = [
    "ChunkRow",
    "ComplexityBudget",
    "HarvestedComment",
    "HarvestedTicket",
    "RateLimiter",
    "chunk_ticket",
    "embed_rows",
    "extract_code_refs",
    "extract_ticket_refs",
    "strip_code_blocks",
    "synthesize_code_sentence",
    "write_ticket",
]

# The Linear-specific harvester (sync_ticket / sync_recent / LinearClient) lives
# in rag_service.harvesters.linear and is imported directly by callers; it is
# intentionally NOT re-exported here to keep this package's surface
# source-agnostic (BILL-32's github.py will sit alongside it the same way).
