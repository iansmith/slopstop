# Search result rendering — semantic ticket search

## Empty result

If the result list is empty:
```
No results found for '$QUERY'.

The corpus may not be indexed yet — see rag-service/README.md for sync instructions.
```
Stop.

## Per-result loop (rank 1–N, already sorted by the service)

Bind these fields from each chunk:
- `$RESULT_TICKET_ID` = `result.ticket_id` (e.g. `BILL-42`).
- `$RANK` = 1-based position in the result list.
- `$SCORE` = formatted to two decimal places (e.g. `0.87`).
- `$KIND` = the `kind` field (e.g. `description`, `comment`).
- `$CHUNK_TEXT` = the `text` field truncated to the first 3 lines (split on `\n`), then truncated to 240 characters if still over; append `…` if truncated.

Render:

```
### $RANK. **$RESULT_TICKET_ID** · $KIND · score $SCORE

$CHUNK_TEXT
```

## Footer

After rendering all results, append:
```
_Top $N results. For more filters (source, kind, provenance, date range) use the `search_tickets` MCP tool directly._
```
