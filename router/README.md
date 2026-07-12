# slopstop router — Phase 1 metering proxy

A tiny loopback reverse proxy that sits between the slopstop fleet and
`api.anthropic.com`. It **passes every request through unchanged** and meters what
it sees — model, token usage, and cost — bucketed by run, ticket, and tier. Query
`GET /spend` to read the running totals.

Phase 1 is **metering only**. It never rewrites, drops, or re-routes a request; it
observes and forwards. Phase 2 (actual model routing) is out of scope here — see
[Phase-1 limits](#phase-1-limits) below.

## Purpose

The v3 process runs stages and fleet agents at different model tiers. To see what a
run actually costs — and to attribute spend to individual tickets — the fleet points
its agents at this proxy (`ANTHROPIC_BASE_URL=http://127.0.0.1:8484`) with two tagging
headers. The proxy records each response's `usage` block against the committed price
table and exposes the aggregate at `/spend`.

## Build and run

```bash
cd router
go build -o build/slopstop-router .
./build/slopstop-router        # listens on 127.0.0.1:8484, forwards to api.anthropic.com
```

The server binds **loopback only** (`127.0.0.1`) — it is a local dev/fleet aid, never
a public endpoint.

### Flags

| Flag | Default | Meaning |
|---|---|---|
| `-port` | `8484` | Port to listen on (always `127.0.0.1`). |
| `-upstream` | `https://api.anthropic.com` | Upstream the proxy forwards to. |
| `-prices` | `prices.toml` | Path to the price table (resolved from the working directory). |

Prices load **once at startup**. Editing `prices.toml` while the router is running has
no effect until you restart it; the loaded file's SHA256 and load time are disclosed in
every `/spend` response under `prices`.

## Tagging: how a request gets attributed

Each proxied request is tagged with a **run id**, a **ticket**, and a **prefix**
(derived from the ticket). Anything untagged is bucketed as `untagged`.

**Run id** — resolved in this order:

1. `X-Slopstop-Run` header (wins if present).
2. A `/r/<run-id>` path prefix, e.g. `POST /r/twilio-20260709-1802/v1/messages`. The
   `/r/<run-id>` segment is **always stripped** before forwarding upstream, even when
   the header supplied the run id.
3. `untagged` if neither is present.

**Ticket and prefix** — from the `X-Slopstop-Ticket` header. The value must match
`^[A-Za-z][A-Za-z0-9]*-\d+$` (e.g. `BILL-201`); the **prefix** is the leading
alpha-run before the `-` (`BILL`). A missing or malformed ticket buckets as `untagged`.

The fleet's pre-pointed launch recipe sets both headers via `ANTHROPIC_CUSTOM_HEADERS`:

```bash
ANTHROPIC_BASE_URL=http://127.0.0.1:8484 \
ANTHROPIC_CUSTOM_HEADERS=$'X-Slopstop-Run: twilio-20260709-1802\nX-Slopstop-Ticket: BILL-201' \
  claude -p 'reply with the single word ok'
```

## `prices.toml` format

One TOML table per model id (matched against the request body's `model` field). Rates
are **USD per million tokens (MTok)**:

```toml
[claude-opus-4-8]
tier = "large"          # one of: small | medium | large | huge
input = 6.50
output = 32.50
cache_write = 8.125
cache_read = 0.65
```

The four tiers are `small` / `medium` / `large` / `huge`. Cost for a response is
`Σ (component_tokens / 1e6 × component_rate)` across `input`, `output`, `cache_write`,
and `cache_read`. A model **not** in the table is metered as **unpriced** — its
requests and tokens are counted (under `unpriced`), but contribute `$0` to totals and
carry tier `untagged`.

> **Rate basis is EFFECTIVE (tokenizer-adjusted), not invoice-accurate.** New-tokenizer
> models (Sonnet 5, Opus 4.8, Fable 5) have their rates multiplied by ~1.3 so figures
> compare models on a same-text basis. Metered USD for those models therefore reads
> ~30% above the literal Anthropic invoice — deliberate. See the header comment in
> `prices.toml` for the invoice-accurate divisors.

## The `/spend` contract

`GET /spend?prefix=<PREFIX>[&run=<run-id>]`

- **`prefix` is required.** Omitting it → **`400`** with
  `{"error":"missing required parameter: prefix"}`.
- **`run` is optional.** When supplied, totals are filtered to that run and the value
  is echoed back in the `run` field; when omitted, `run` is absent from the response.
- **An unknown prefix is not an error.** It returns **`200` with zeroed counters**
  (`requests: 0`, `total_usd: 0`, empty `by_*` maps) — so a health probe against a
  fresh prefix succeeds rather than 404-ing.

### Response shape

```json
{
  "prefix": "BILL",
  "run": "twilio-20260709-1802",
  "router_started_at": "2026-07-12T14:00:00Z",
  "requests": 2,
  "total_usd": 0.0123,
  "by_tier":  { "large": { "requests": 2, "tokens": { ... }, "usd": 0.0123 } },
  "by_ticket": { "BILL-201": { "requests": 2, "tokens": { ... }, "usd": 0.0123 } },
  "by_model": [
    {
      "model": "claude-opus-4-8",
      "tier": "large",
      "tokens": { "input_tokens": 900, "output_tokens": 300, "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0 },
      "rates_per_mtok": { "input": 6.50, "output": 32.50, "cache_write": 8.125, "cache_read": 0.65 },
      "usd": 0.0123
    }
  ],
  "unpriced": { "requests": 0, "tokens": { ... }, "models": {} },
  "prices": { "file": "prices.toml", "sha256": "…", "loaded_at": "2026-07-12T14:00:00Z" }
}
```

`by_model` **shows the work**: for every model seen it carries the raw token counts
**and** the `rates_per_mtok` used, so `usd` is auditable from the response alone. It is
sorted deterministically by `(model, tier)`. `router_started_at` is the meter's
zero point (see limits). This shape is frozen — a golden test
(`TestSpendContractGolden` in `spend_test.go`) pins it.

## sophie-status snippet — paste into `~/sophie`, this repo never edits it

On the reference machine the router runs as a `[[server]]` entry under **sophie-status**
(Ian's fleet supervisor). The block below is **for you to paste** into
`~/sophie/sophie-status.toml`. **This repo does not read, write, or own any sophie
config** — the snippet lives here purely as copy-paste source; sophie's config is yours.

```toml
[[server]]
name  = "slopstop-router"
type  = "source"
dir   = "~/slopstop/router"
build = "go build -o build/slopstop-router ."
run   = "./build/slopstop-router -port 8484"
port  = 8484
health = "GET /spend?prefix=SOP"
```

`health` uses the prefix-required probe: any `200` (including the zeroed unknown-prefix
response) means the proxy is live.

## Phase-1 limits

1. **In-memory only.** Counters live in process memory; **a restart zeroes them.** The
   zero point is disclosed as `router_started_at` in every `/spend` response — treat any
   figure as "since that timestamp", not lifetime.
2. **Stage-1 (`:design`) traffic is not metered.** A session cannot re-point itself at
   the router mid-flight, so metering requires the **pre-pointed launch** (the
   `ANTHROPIC_BASE_URL` + headers recipe above) — which only later stages get. When
   `:design` mints its own run id, it records "Stage 1 unmetered".
3. **No routing.** Phase 1 forwards every request to the single `-upstream` unchanged.
   Tier-aware model routing is Phase 2 and is **not** implemented here.
