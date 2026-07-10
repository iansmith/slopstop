package main

import (
	"encoding/json"
	"net/http"
	"time"
)

// SpendResponse is the frozen contract response for GET /spend.
type SpendResponse struct {
	Prefix         string                 `json:"prefix"`
	Run            string                 `json:"run,omitempty"`
	RouterStartedAt string                `json:"router_started_at"`
	Requests       int64                  `json:"requests"`
	TotalUSD       float64                `json:"total_usd"`
	ByTier         map[string]TierEntry   `json:"by_tier"`
	ByTicket       map[string]TicketEntry `json:"by_ticket"`
	ByModel        []ModelEntry           `json:"by_model"`
	Unpriced       UnpricedEntry          `json:"unpriced"`
	Prices         PricesEntry            `json:"prices"`
}

// TierEntry aggregates by tier.
type TierEntry struct {
	Requests int64  `json:"requests"`
	Tokens   Tokens `json:"tokens"`
	USD      float64 `json:"usd"`
}

// TicketEntry aggregates by ticket.
type TicketEntry struct {
	Requests int64  `json:"requests"`
	Tokens   Tokens `json:"tokens"`
	USD      float64 `json:"usd"`
}

// ModelEntry details a single model's usage and costs.
type ModelEntry struct {
	Model         string             `json:"model"`
	Tier          string             `json:"tier"`
	Tokens        Tokens             `json:"tokens"`
	RatesPerMTok  map[string]float64 `json:"rates_per_mtok"`
	USD           float64            `json:"usd"`
}

// UnpricedEntry aggregates unknown-model and unparseable records.
type UnpricedEntry struct {
	Requests int64              `json:"requests"`
	Tokens   Tokens             `json:"tokens"`
	Models   map[string]bool    `json:"models"`
}

// PricesEntry holds metadata about the price table.
type PricesEntry struct {
	File     string `json:"file"`
	SHA256   string `json:"sha256"`
	LoadedAt string `json:"loaded_at"`
}

// spendHandler returns a handler for GET /spend that returns aggregated meter data.
func spendHandler(meter *Meter, table PriceTable, priceFile string, priceSHA256 string) http.HandlerFunc {
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
			ByTier:          make(map[string]TierEntry),
			ByTicket:        make(map[string]TicketEntry),
			ByModel:         []ModelEntry{},
			Unpriced: UnpricedEntry{
				Requests: snapshot.Unpriced.Requests,
				Tokens:   snapshot.Unpriced.Tokens,
				Models:   snapshot.Unpriced.Models,
			},
			Prices: PricesEntry{
				File:     priceFile,
				SHA256:   priceSHA256,
				LoadedAt: time.Now().Format(time.RFC3339),
			},
		}

		// Only include run if it was supplied
		if run != "" {
			resp.Run = run
		}

		// TODO: populate by_tier, by_ticket, by_model from meter data
		// For now, return minimal response to fail tests

		w.WriteHeader(http.StatusOK)
		json.NewEncoder(w).Encode(resp)
	}
}
