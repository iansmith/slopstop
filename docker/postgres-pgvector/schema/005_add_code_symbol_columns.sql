-- 005_add_code_symbol_columns.sql — BILL-57
-- Add moniker and repo columns to ticket_chunks for SCIP docstring linkage.
ALTER TABLE ticket_chunks ADD COLUMN IF NOT EXISTS moniker TEXT;
ALTER TABLE ticket_chunks ADD COLUMN IF NOT EXISTS repo    TEXT;
CREATE INDEX IF NOT EXISTS ticket_chunks_source_repo_idx
    ON ticket_chunks (source, repo);

-- Replace the catch-all UNIQUE(source, ticket_id, provenance, kind, seq) with
-- two partial indexes so SCIP rows from different repos can coexist safely.
-- Non-SCIP rows (tickets) keep the original key; SCIP rows include repo so that
-- two repos sharing the same Go module path (e.g. a fork) don't collide.
ALTER TABLE ticket_chunks
    DROP CONSTRAINT IF EXISTS ticket_chunks_source_ticket_id_provenance_kind_seq_key;

CREATE UNIQUE INDEX IF NOT EXISTS ticket_chunks_nonscip_unique_idx
    ON ticket_chunks (source, ticket_id, provenance, kind, seq)
    WHERE source != 'scip';

CREATE UNIQUE INDEX IF NOT EXISTS ticket_chunks_scip_unique_idx
    ON ticket_chunks (source, repo, ticket_id, provenance, kind, seq)
    WHERE source = 'scip';
