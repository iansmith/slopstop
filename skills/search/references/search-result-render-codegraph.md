# Search result rendering — code-graph modes

## Mode-specific heading

| Mode | Heading |
|---|---|
| `callers` | `## Callers of \`$MONIKER\`` |
| `implementors` | `## Implementors of \`$MONIKER\`` |
| `blast-radius` | `## Blast radius of \`$MONIKER\`` |
| `ticket-code` | `## Code touched by $TICKET_ID` |

## Result list

If zero results: print `"No results found."` and stop.

For each result row (fields: `moniker`, `file_path`, `line`, `location`, `lang`, `repo`, `external`):
- If `external` is true: `- \`result.moniker\` _(external — not in local index)_`
- Otherwise: `- \`$location\`` where `location` is in `file_path:line` form — if `location` is already pre-formatted by the server use it directly, otherwise construct it.

## Footer

After listing results, append:
```
$N result(s).
```
