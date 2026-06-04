-- 005_add_code_symbol_columns.sql — BILL-57
-- Add moniker and repo columns to ticket_chunks for SCIP docstring linkage.
ALTER TABLE ticket_chunks ADD COLUMN IF NOT EXISTS moniker TEXT;
ALTER TABLE ticket_chunks ADD COLUMN IF NOT EXISTS repo    TEXT;
CREATE INDEX IF NOT EXISTS ticket_chunks_source_repo_idx
    ON ticket_chunks (source, repo);
