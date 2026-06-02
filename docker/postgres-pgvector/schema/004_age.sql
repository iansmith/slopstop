-- BILL-52 — Apache AGE (A Graph Extension): graph layer alongside pgvector.
--
-- Applied on every container start by entrypoint.sh, idempotently, in a
-- single transaction with ON_ERROR_STOP=1 (same path as 001-003). Every
-- statement here MUST be idempotent — hard repo convention for schema/*.sql.
--
-- CREATE EXTENSION does NOT require age.so to be preloaded or LOAD'ed: it only
-- registers the ag_catalog schema, the agtype type, and the C-function
-- definitions. Actually *running* Cypher needs the library loaded in-session
-- (LOAD 'age') or server-wide (shared_preload_libraries='age'); that is a
-- connection-level concern handled by the app / smoke test, not here.
CREATE EXTENSION IF NOT EXISTS age;

-- Bootstrap the code graph idempotently. create_graph() has no IF NOT EXISTS
-- form, so guard against the ag_catalog.ag_graph registry. LOAD is required
-- because create_graph() is a C function in age.so.
LOAD 'age';
SET search_path = ag_catalog, "$user", public;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM ag_catalog.ag_graph WHERE name = 'code_graph') THEN
        PERFORM ag_catalog.create_graph('code_graph');
    END IF;
END
$$;
