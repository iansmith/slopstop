# Step 4 — Artifact classification detail

## 4a. Find the managed version on the ticket

- **Description**: managed = `$REMOTE_DESC` contains the literal string `## Original description (preserved)`. Managed body = the portion before the `---\n\n## Original description (preserved)\n\n` separator. If no marker → category: `new`.
- **DoD comment**: managed = comments whose body's first non-blank line starts with `## Definition of Done — Confirmation` (allowing the optional ` (<timestamp>)` suffix). If multiple match, pick the one with the latest `updated_at`. If none AND `$EXPECTED_DOD == null` → category: `skip`. If none AND `$EXPECTED_DOD != null` → category: `new`.
- **Findings comment**: same logic, matching first line `## Findings (from local tracking)`.

## 4b. Compare via loose-normalize

For each artifact with both a managed version AND an expected version:

Normalize both sides:

1. Collapse all sequences of whitespace (spaces, tabs, newlines) to a single space.
2. Strip leading and trailing whitespace.
3. For the DoD comment ONLY: remove the entire `Confirmed at: ...` line and the `## Definition of Done — Confirmation (<timestamp>)` header timestamp from both sides BEFORE normalizing (dynamic per-push; ignoring lets pure timestamp changes be `unchanged`).

If `normalize(expected) == normalize(actual_managed)` → category: `unchanged`.
Else → category: `divergent`.

## 4c. Category summary

| Category | Meaning | Step 6 action |
|---|---|---|
| `new` | Not yet on the ticket | Push |
| `unchanged` | Already current | Skip |
| `divergent` | Managed version differs from expected | Stop (unless `--force`) |
| `skip` | Nothing to push | Skip |
