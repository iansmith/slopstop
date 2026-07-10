package main

import (
	"crypto/sha256"
	"fmt"
	"os"
	"time"

	"github.com/BurntSushi/toml"
)

// Tier is a label for pricing tiers: small, medium, big.
type Tier string

const (
	Small  Tier = "small"
	Medium Tier = "medium"
	Big    Tier = "big"
)

// Rates holds the per-model pricing rates in USD per million tokens.
type Rates struct {
	Tier       string  `toml:"tier"`
	Input      float64 `toml:"input"`
	Output     float64 `toml:"output"`
	CacheWrite float64 `toml:"cache_write"`
	CacheRead  float64 `toml:"cache_read"`
}

// PriceTable holds the per-model pricing rates loaded from TOML.
type PriceTable map[string]*Rates

// LoadPrices loads the pricing table from a TOML file.
// Returns the parsed PriceTable, the file's SHA256 hash (hex), the load timestamp, and any error.
func LoadPrices(path string) (PriceTable, string, time.Time, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, "", time.Time{}, fmt.Errorf("failed to read prices file: %w", err)
	}

	prices := make(PriceTable)
	if err := toml.Unmarshal(data, &prices); err != nil {
		return nil, "", time.Time{}, fmt.Errorf("failed to decode prices TOML: %w", err)
	}

	sha256Hash := fmt.Sprintf("%x", sha256.Sum256(data))
	timestamp := time.Now()

	return prices, sha256Hash, timestamp, nil
}

// Cost calculates the USD cost for a given model and token usage.
// If the model is unknown, returns (0, false).
// Otherwise, returns (usd, true) where usd is calculated as:
// Σ (token_component / 1e6 × rate_component) for all four token types.
func (pt PriceTable) Cost(model string, t Tokens) (float64, bool) {
	rates, ok := pt[model]
	if !ok {
		return 0, false
	}

	usd := float64(t.InputTokens)/1e6*rates.Input +
		float64(t.OutputTokens)/1e6*rates.Output +
		float64(t.CacheCreationInputTokens)/1e6*rates.CacheWrite +
		float64(t.CacheReadInputTokens)/1e6*rates.CacheRead

	return usd, true
}
