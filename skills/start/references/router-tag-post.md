# Router /tag POST recipe

Shared step: conditionally POST to the router's `/tag` endpoint to attribute work to a run-id when the router is healthy and a run-id is available in the environment.

## Gate on router enabled

Check `[fleet.router] enabled` in `.project-conf.toml`. If false or absent, skip this step silently and proceed with all other `:start` behavior unchanged.

## Extract run-id from environment

Read `ANTHROPIC_CUSTOM_HEADERS` environment variable. Parse the header dictionary for `X-Slopstop-Run`. If absent:
- Report: `"Attribution unavailable — session launched without X-Slopstop-Run. Relaunch with a run-id to enable per-ticket metering."`
- Do NOT POST.
- Do NOT error. Continue with all other `:start` behavior unchanged.
- Do NOT mint a run-id for this purpose.

If present, capture the run-id value.

## Health-check the router

Attempt a health check: `curl -s http://<host>:<port>/spend` where host/port come from `[fleet.router]` config.

On curl timeout or connection failure: skip the POST silently and proceed. The router being unreachable never blocks `:start`.

On 2xx response: the router is healthy; proceed to POST.

On other HTTP status: skip the POST silently and proceed (e.g., 500 from an unhealthy router).

## POST /tag with run-id and ticket

Send: `curl -X POST -H "Content-Type: application/json" -d '{"run":"<run-id>","ticket":"<TICKET>"}' http://<host>:<port>/tag`

On success (2xx response): log `"Attribution POST /tag succeeded (run-id: <run-id>, ticket: <TICKET>)."` and proceed.

On failure (any HTTP error or timeout):
- Warn: `"Attribution POST /tag failed (status: <status> or timeout); proceeding without tagging."`
- Do NOT error or block `:start`.
- Proceed with all other `:start` behavior unchanged.

## Re-attribution on ticket change

If `:start` is re-invoked in the same session with a different ticket, re-run this recipe with the new `<TICKET>`. The router updates the run→ticket mapping; old tickets are dis-associated if a run is reassigned to a new ticket (expected when the user switches contexts mid-session).

## No silent failures

If the recipe is invoked but the caller never sees a message (either "succeeded" or "failed"), the recipe is broken. A missing log line is a bug — it means the POST ran without the operator knowing whether it succeeded or failed.
