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
| `-prices` | *(empty)* | Dev/test override: path to a price table read from disk. **Absent → the embedded manifest is loaded** (no file read); the router binary is self-contained. |

Prices load **once at startup** — the embedded manifest by default, or the `-prices`
override file when passed. Editing the override file (or rebuilding to change the
embed) while the router is running has no effect until you restart it; the loaded
manifest's provenance — `source` (`"embedded"` or the override path), `sha256` of the
exact content loaded, and load time — is disclosed in every `/spend` response under
`prices`.

## Tagging: how a request gets attributed

Each proxied request is tagged with a **run id**, a **ticket**, and a **prefix**
(derived from the ticket). Anything untagged is bucketed as `untagged`.

**Run id** — resolved in this order:

1. `X-Slopstop-Run` header (wins if present).
2. A `/r/<run-id>` path prefix, e.g. `POST /r/twilio-20260709-1802/v1/messages`. The
   `/r/<run-id>` segment is **always stripped** before forwarding upstream, even when
   the header supplied the run id.
3. `untagged` if neither is present.

**Ticket and prefix** — resolved in this order:

1. `X-Slopstop-Ticket` header (wins if present). The value must match
   `^[A-Za-z][A-Za-z0-9]*-\d+$` (e.g. `BILL-201`); the **prefix** is the leading
   alpha-run before the `-` (`BILL`). A malformed header value buckets as `untagged`.
2. The `/tag` run→ticket map (consulted only when no `X-Slopstop-Ticket` header is
   present on the request — see below).
3. `untagged` if neither resolves a ticket.

This precedence exists because interactive sessions are long-lived and work many
tickets over their lifetime — a header fixed at process launch can't track that, but
a run-id can stay constant while the *current ticket* changes underneath it.

### The `/tag` endpoint — dynamic run→ticket attribution

`POST /tag` and `GET /tag` maintain an in-memory, `sync.RWMutex`-guarded map from
run-id to the ticket that run-id's session is currently working. It exists so a
long-lived interactive session — which launches once with a stable `X-Slopstop-Run`
but no `X-Slopstop-Ticket` — can still get its spend attributed correctly as it
moves between tickets, without relaunching the process. Fleet-agent launches don't
need this: they already carry a fixed `X-Slopstop-Ticket` header per agent, which
always wins over the map (see the precedence above).

**`POST /tag`** — body `{"run": "<run-id>", "ticket": "<TICKET>"}`:

```bash
curl -X POST -H 'Content-Type: application/json' \
  -d '{"run":"twilio-20260709-1802","ticket":"BILL-201"}' \
  http://127.0.0.1:8484/tag
# -> 200 {"run":"twilio-20260709-1802","ticket":"BILL-201","prefix":"BILL"}
```

- `ticket` empty or `"untagged"` **clears** the mapping for that run-id (subsequent
  headerless requests for that run meter as `untagged`).
- `run` empty or equal to `"untagged"` is rejected with `400` — the map can never be
  poisoned with an `untagged` key, so an untagged run can never accidentally resolve
  through it.
- A malformed `ticket` is rejected with `400` and leaves any existing mapping for
  that run-id **unchanged**.

**`GET /tag`** returns the full current map as `{"<run-id>": "<ticket>", ...}` (empty
map → `{}`).

The two client-side tagging points that call this endpoint are the `/slopstop:start`
skill (POSTs on ticket start, when a run-id is available) and the `/slopstop:focus
<TICKET>` command (re-points attribution mid-session without any other side effect —
no branch, no ticket-system transition, no tracking-file write). Both are best-effort:
a disabled or unreachable router never blocks either command, and `:focus` reports
that condition explicitly rather than failing silently.

The fleet's pre-pointed launch recipe sets the run-id header via `ANTHROPIC_CUSTOM_HEADERS`:

```bash
ANTHROPIC_BASE_URL=http://127.0.0.1:8484 \
ANTHROPIC_CUSTOM_HEADERS=$'X-Slopstop-Run: twilio-20260709-1802' \
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
- **`format` is optional.** When set to `html`, returns an interactive HTML dashboard; when
  set to `json` or omitted, returns JSON (the default). Errors always return JSON regardless of
  the format parameter; an invalid or missing `prefix` returns `400` with `{"error":"..."}` even
  if `format=html` was requested. The HTML dashboard embeds the complete JSON response in a
  `<script id="spend-data" type="application/json">` block for client-side consumption.

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
  "total_usd_display": "$0.01 (estimated 0.00% of $1100)",
  "by_tier":  { "large": { "requests": 2, "tokens": { ... }, "usd": 0.0123 } },
  "by_ticket": { "BILL-201": { "requests": 2, "tokens": { ... }, "usd": 0.0123 } },
  "by_model": [
    {
      "model": "claude-opus-4-8",
      "tier": "large",
      "provider": "anthropic",
      "family": "opus",
      "version": "4.8",
      "tokens": { "input_tokens": 900, "output_tokens": 300, "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0 },
      "rates_per_mtok": { "input": 6.50, "output": 32.50, "cache_write": 8.125, "cache_read": 0.65 },
      "usd": 0.0123,
      "usd_display": "$0.01 (estimated 0.00% of $1100)"
    }
  ],
  "unpriced": { "requests": 0, "tokens": { ... }, "models": {} },
  "prices": { "source": "embedded", "sha256": "…", "loaded_at": "2026-07-12T14:00:00Z" }
}
```

`by_model` **shows the work**: for every model seen it carries the raw token counts,
the loaded model metadata (`provider` / `family` / `version`), **and** the
`rates_per_mtok` used, so `usd` is auditable from the response alone. (`provider` /
`family` / `version` are empty for a model seen on the wire but absent from the
manifest.) It is sorted deterministically by `(model, tier)`. `router_started_at` is
the meter's zero point (see limits). The `prices` block is the manifest provenance:
`source` is `"embedded"` for the compiled-in manifest or the `-prices` override path,
`sha256` is over the exact content loaded, and `loaded_at` is process start for the
embedded manifest. This shape is frozen — a golden test (`TestSpendContractGolden` in
`spend_test.go`) pins it.

Alongside the numeric `total_usd` (grand total) and each model's `usd`, the response
carries a human-readable companion — `total_usd_display` and per-model `usd_display` —
formatted `"$X.YY (estimated A.AA% of $1100)"`, expressing the amount as a percentage
of the monthly-budget constant (`MonthlyBudgetUSD`, currently $1100), to 2 decimals.

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

## End-to-end verification (`verify.sh`)

`router/verify.sh` is the executable acceptance test. It builds the binary, starts it
on a free loopback port, launches a **real headless `claude -p` session through the
router** with the pre-pointed recipe, then asserts `/spend` shows the session metered
(a `by_model` entry with a real tier, `total_usd > 0`, the tagged ticket in
`by_ticket`).

Run it from a terminal (not embedded in another agent) with an authenticated `claude`:

```bash
cd router
bash verify.sh          # PASS + exit 0 means a live agent session was metered
```

**Auth:** the agent session uses whatever the `claude` CLI is logged in with. A Claude
subscription (`/login`, OAuth) is enough — it flows through the custom
`ANTHROPIC_BASE_URL` unchanged, **no api key required**. If `ANTHROPIC_API_KEY` is set,
`verify.sh` additionally runs a hand-built `curl` smoke request (which needs the key);
without one, the live agent session alone is the check. No key is ever hardcoded, and
the captured `/spend` JSON is written under gitignored `scratch/`.

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
