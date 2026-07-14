package main

	import (
		"bytes"
		"encoding/json"
		"html/template"
		"net/http"
		"sort"
		"time"
	)

// SpendResponse is the frozen contract response for GET /spend.
type SpendResponse struct {
	Prefix          string                 `json:"prefix"`
	Run             string                 `json:"run,omitempty"`
	RouterStartedAt string                 `json:"router_started_at"`
	Requests        int64                  `json:"requests"`
	TotalUSD        float64                `json:"total_usd"`
	TotalUSDDisplay string                 `json:"total_usd_display"`
	ByTier          map[string]TierEntry   `json:"by_tier"`
	ByTicket        map[string]TicketEntry `json:"by_ticket"`
	ByModel         []ModelEntry           `json:"by_model"`
	Unpriced        UnpricedEntry          `json:"unpriced"`
	Prices          PricesEntry            `json:"prices"`
}

// TierEntry aggregates by tier.
type TierEntry struct {
	Requests int64   `json:"requests"`
	Tokens   Tokens  `json:"tokens"`
	USD      float64 `json:"usd"`
}

// TicketEntry aggregates by ticket.
type TicketEntry struct {
	Requests int64   `json:"requests"`
	Tokens   Tokens  `json:"tokens"`
	USD      float64 `json:"usd"`
}

// ModelEntry details a single model's usage and costs. Provider/Family/Version
// come from the loaded model metadata (the price table's Rates); they are empty
// for a model seen on the wire but absent from the table (unpriced).
type ModelEntry struct {
	Model        string             `json:"model"`
	Tier         string             `json:"tier"`
	Provider     string             `json:"provider"`
	Family       string             `json:"family"`
	Version      string             `json:"version"`
	Tokens       Tokens             `json:"tokens"`
	RatesPerMTok map[string]float64 `json:"rates_per_mtok"`
	USD          float64            `json:"usd"`
	USDDisplay   string             `json:"usd_display"`
}

// UnpricedEntry aggregates unknown-model and unparseable records.
type UnpricedEntry struct {
	Requests int64           `json:"requests"`
	Tokens   Tokens          `json:"tokens"`
	Models   map[string]bool `json:"models"`
}

// PricesEntry holds provenance for the loaded price manifest: where it came from
// ("embedded" or an override path), the SHA256 of the exact content loaded, and
// when it was loaded (process start for the embedded manifest).
type PricesEntry struct {
	Source   string `json:"source"`
	SHA256   string `json:"sha256"`
	LoadedAt string `json:"loaded_at"`
}

// spendHandler returns a handler for GET /spend that returns aggregated meter data.
// priceSource is the provenance label: "embedded" when the compiled-in manifest
// was loaded, or the -prices override path.
func spendHandler(meter *Meter, table PriceTable, priceSource string, priceSHA256 string, loadedAt time.Time) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")

		// Parse required prefix parameter
		prefix := r.URL.Query().Get("prefix")
		if prefix == "" {
			w.WriteHeader(http.StatusBadRequest)
			json.NewEncoder(w).Encode(map[string]string{
				"error": "missing required parameter: prefix",
			})
			return
		}

		// Parse optional run parameter
		run := r.URL.Query().Get("run")

		// Get meter snapshot
		snapshot := meter.Snapshot(prefix, run)

		// Build response
		resp := SpendResponse{
			Prefix:          prefix,
			RouterStartedAt: meter.StartedAt.Format(time.RFC3339),
			Requests:        snapshot.Requests,
			TotalUSD:        snapshot.USD,
			TotalUSDDisplay: formatSpendDisplay(snapshot.USD),
			ByTier:          make(map[string]TierEntry),
			ByTicket:        make(map[string]TicketEntry),
			ByModel:         []ModelEntry{},
			Unpriced: UnpricedEntry{
				Requests: snapshot.Unpriced.Requests,
				Tokens:   snapshot.Unpriced.Tokens,
				Models:   snapshot.Unpriced.Models,
			},
			Prices: PricesEntry{
				Source:   priceSource,
				SHA256:   priceSHA256,
				LoadedAt: loadedAt.Format(time.RFC3339),
			},
		}

		// Only include run if it was supplied
		if run != "" {
			resp.Run = run
		}

		// Populate by_tier
		tierAggs := meter.AggregatesByTier(prefix, run)
		for tier, agg := range tierAggs {
			resp.ByTier[tier] = TierEntry{
				Requests: agg.Requests,
				Tokens:   agg.Tokens,
				USD:      agg.USD,
			}
		}

		// Populate by_ticket
		ticketAggs := meter.AggregatesByTicket(prefix, run)
		for ticket, agg := range ticketAggs {
			resp.ByTicket[ticket] = TicketEntry{
				Requests: agg.Requests,
				Tokens:   agg.Tokens,
				USD:      agg.USD,
			}
		}

		// Populate by_model
		modelDetails := meter.ModelDetails(prefix, run)
		for _, md := range modelDetails {
			entry := ModelEntry{
				Model:        md.Model,
				Tier:         md.Tier,
				Tokens:       md.Agg.Tokens,
				RatesPerMTok: make(map[string]float64),
				USD:          md.Agg.USD,
				USDDisplay:   formatSpendDisplay(md.Agg.USD),
			}

			// Look up rates + model metadata for this model. Absent (unpriced)
			// models keep empty provider/family/version and no rates.
			if rates, ok := table[md.Model]; ok {
				entry.Provider = rates.Provider
				entry.Family = rates.Family
				entry.Version = rates.Version
				entry.RatesPerMTok["input"] = rates.Input
				entry.RatesPerMTok["output"] = rates.Output
				entry.RatesPerMTok["cache_write"] = rates.CacheWrite
				entry.RatesPerMTok["cache_read"] = rates.CacheRead
			}

			resp.ByModel = append(resp.ByModel, entry)
		}

		// Sort by_model deterministically by (model, tier) before encoding
		sort.Slice(resp.ByModel, func(i, j int) bool {
			if resp.ByModel[i].Model != resp.ByModel[j].Model {
				return resp.ByModel[i].Model < resp.ByModel[j].Model
			}
			return resp.ByModel[i].Tier < resp.ByModel[j].Tier
		})

		// Check format parameter
		format := r.URL.Query().Get("format")
		if format == "html" {
			renderSpendHTML(w, resp)
			return
		}

		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusOK)
		json.NewEncoder(w).Encode(resp)
	}
}


// renderSpendHTML renders the SpendResponse as an HTML dashboard.
func renderSpendHTML(w http.ResponseWriter, resp SpendResponse) {
	funcMap := template.FuncMap{
		"div": func(a, b float64) float64 {
			if b == 0 {
				return 0
			}
			return a / b
		},
	}
	tmpl := template.Must(template.New("spend").Funcs(funcMap).Parse(`
<!DOCTYPE html>
<html lang="en">
<head>
	<meta charset="UTF-8">
	<meta name="viewport" content="width=device-width, initial-scale=1.0">
	<title>Spend Dashboard</title>
	<style>
		body { font-family: system-ui, -apple-system, sans-serif; margin: 0; padding: 20px; background: #f5f5f5; }
		.container { max-width: 1200px; margin: 0 auto; background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
		h1, h2 { color: #333; }
		.headline { background: #f0f0f0; padding: 20px; border-radius: 4px; margin-bottom: 20px; }
		.metric { display: inline-block; margin-right: 30px; }
		.metric-label { color: #666; font-size: 12px; text-transform: uppercase; }
		.metric-value { font-size: 24px; font-weight: bold; color: #333; }
		.progress-bar { width: 200px; height: 20px; background: #ddd; border-radius: 4px; overflow: hidden; }
		.progress-fill { height: 100%; background: #4CAF50; transition: width 0.3s; }
		table { width: 100%; border-collapse: collapse; margin: 20px 0; }
		th { background: #f0f0f0; padding: 12px; text-align: left; font-weight: 600; border-bottom: 2px solid #ddd; }
		td { padding: 12px; border-bottom: 1px solid #ddd; }
		tr:hover { background: #f9f9f9; }
		.section { margin-bottom: 30px; }
		.footer { margin-top: 40px; padding-top: 20px; border-top: 1px solid #ddd; color: #666; font-size: 12px; }
		details { margin: 20px 0; }
		summary { cursor: pointer; font-weight: 600; padding: 10px; background: #f9f9f9; border-radius: 4px; }
		pre { background: #f5f5f5; padding: 15px; border-radius: 4px; overflow-x: auto; }
		script { display: block; width: 0; height: 0; }
	</style>
</head>
<body>
	<div class="container">
		<h1>Spend Dashboard</h1>

		<div class="section headline">
			<div class="metric">
				<div class="metric-label">Total USD</div>
				<div class="metric-value">{{.TotalUSDDisplay}}</div>
			</div>
			<div class="metric">
				<div class="metric-label">Requests</div>
				<div class="metric-value">{{.Requests}}</div>
			</div>
			<div class="metric">
				<div class="metric-label">Budget Progress</div>
				<div class="progress-bar">
					<div class="progress-fill" style="width: {{printf "%.1f" (div .TotalUSD 11.0)}}%;"></div>
				</div>
			</div>
		</div>

		<div class="section">
			<h2>By Tier</h2>
			<table>
				<thead>
					<tr><th>Tier</th><th>Requests</th><th>USD</th></tr>
				</thead>
				<tbody>
					{{range $tier, $entry := .ByTier}}
					<tr><td>{{$tier}}</td><td>{{$entry.Requests}}</td><td>${{printf "%.2f" $entry.USD}}</td></tr>
					{{end}}
				</tbody>
			</table>
		</div>

		<div class="section">
			<h2>By Ticket</h2>
			<table>
				<thead>
					<tr><th>Ticket</th><th>Requests</th><th>USD</th></tr>
				</thead>
				<tbody>
					{{range $ticket, $entry := .ByTicket}}
					<tr><td>{{$ticket}}</td><td>{{$entry.Requests}}</td><td>${{printf "%.2f" $entry.USD}}</td></tr>
					{{end}}
				</tbody>
			</table>
		</div>

		<div class="section">
			<h2>By Model</h2>
			<table>
				<thead>
					<tr><th>Model</th><th>Tier</th><th>Provider</th><th>Family</th><th>Version</th><th>Input Tokens</th><th>Output Tokens</th><th>Rates (per MTok)</th><th>USD</th></tr>
				</thead>
				<tbody>
					{{range .ByModel}}
					<tr>
						<td>{{.Model}}</td>
						<td>{{.Tier}}</td>
						<td>{{.Provider}}</td>
						<td>{{.Family}}</td>
						<td>{{.Version}}</td>
						<td>{{.Tokens.InputTokens}}</td>
						<td>{{.Tokens.OutputTokens}}</td>
						<td>input: ${{printf "%.6f" (index .RatesPerMTok "input")}}, output: ${{printf "%.6f" (index .RatesPerMTok "output")}}</td>
						<td>{{.USDDisplay}}</td>
					</tr>
					{{end}}
				</tbody>
			</table>
		</div>

		<div class="footer">
			<h3>Provenance</h3>
			<p><strong>Router Started:</strong> {{.RouterStartedAt}}</p>
			<p><strong>Prices Source:</strong> {{.Prices.Source}}</p>
			<p><strong>Prices SHA256:</strong> {{.Prices.SHA256}}</p>
			<p><strong>Prices Loaded At:</strong> {{.Prices.LoadedAt}}</p>
		</div>

		<details>
			<summary>Raw JSON</summary>
			<pre><script id="spend-data" type="application/json">{{.JSON}}</script></pre>
		</details>
	</div>

	<script id="spend-data" type="application/json">{{.JSON}}</script>
</body>
</html>
`))

	// Marshal response to JSON string for embedding
	jsonBytes, _ := json.MarshalIndent(resp, "", "  ")
	
	data := map[string]interface{}{
		"TotalUSD":        resp.TotalUSD,
		"TotalUSDDisplay": resp.TotalUSDDisplay,
		"Requests":        resp.Requests,
		"ByTier":          resp.ByTier,
		"ByTicket":        resp.ByTicket,
		"ByModel":         resp.ByModel,
		"Prices":          resp.Prices,
		"RouterStartedAt": resp.RouterStartedAt,
		"JSON":            template.JS(jsonBytes),
	}

	w.Header().Set("Content-Type", "text/html; charset=utf-8")
	w.WriteHeader(http.StatusOK)
	
	var buf bytes.Buffer
	if err := tmpl.Execute(&buf, data); err != nil {
		w.WriteHeader(http.StatusInternalServerError)
		return
	}
	
	w.Write(buf.Bytes())
}

