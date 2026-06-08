# doc-sync: Linear backend

## system = "linear"

1. **Pre-flight:** verify the Linear MCP is reachable. If not, stop with `"Linear MCP not available."`

2. **List existing upstream docs** via `mcp__linear-server__list_documents` scoped to the team / project for `$KEY`.

3. **For each `design/*.md`** (excluding subdirectories):

   - Parse frontmatter → `$TITLE`.
   - Strip frontmatter from the body.
   - Look for an existing upstream doc with matching `$TITLE`.
   - If found: call `mcp__linear-server__save_document` with the existing doc's ID and the new body.
   - If not: call `mcp__linear-server__save_document` to create.

4. **Orphan prune:** for each upstream doc whose title doesn't match any current `design/` source title: delete it via the Linear MCP.

5. **Confirm:** `"Synced N design docs to Linear ($KEY)."`
