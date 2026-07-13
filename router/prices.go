package main

import (
	"crypto/sha256"
	"fmt"
	"os"
	"regexp"
	"time"

	"github.com/BurntSushi/toml"
)

// Tier is a label for pricing tiers: small, medium, large, huge.
type Tier string

const (
	Small  Tier = "small"
	Medium Tier = "medium"
	Large  Tier = "large"
	Huge   Tier = "huge"
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

// Provider holds provider configuration (URL and auth method).
type Provider struct {
	URL  string `toml:"url"`
	Auth string `toml:"auth"`
}

// Model holds model configuration with pricing rates.
type Model struct {
	Provider   string  `toml:"provider"`
	Family     string  `toml:"family"`
	Version    string  `toml:"version"`
	Tier       string  `toml:"tier"`
	URL        string  `toml:"url"`
	Input      float64 `toml:"input"`
	Output     float64 `toml:"output"`
	CacheWrite float64 `toml:"cache_write"`
	CacheRead  float64 `toml:"cache_read"`
}

// RawConfig holds the parsed TOML structure (both old and new formats).
type RawConfig struct {
	Providers map[string]*Provider `toml:"providers"`
	Models    map[string]*Model    `toml:"models"`
}

// LoadPrices loads the pricing table from a TOML file.
// Supports the new nested [providers.<name>] and [models.<key>] structure.
// Rejects the legacy flat [claude-*] format.
// Returns the parsed PriceTable, the file's SHA256 hash (hex), the load timestamp, and any error.
func LoadPrices(path string) (PriceTable, string, time.Time, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, "", time.Time{}, fmt.Errorf("failed to read prices file: %w", err)
	}

	// Check for legacy flat [claude-*] format first
	if err := checkLegacyFormat(data); err != nil {
		return nil, "", time.Time{}, err
	}

	// Parse the new nested structure
	var raw RawConfig
	if err := toml.Unmarshal(data, &raw); err != nil {
		return nil, "", time.Time{}, fmt.Errorf("failed to decode prices TOML: %w", err)
	}

	// Build the price table from the new structure
	prices := make(PriceTable)

	if raw.Models != nil {
		anthropicPattern := regexp.MustCompile(`^claude-([a-z]+)-([0-9.-]+)$`)

		for modelKey, modelConfig := range raw.Models {
			if modelConfig == nil {
				continue
			}

			// Validate Anthropic naming if provider is anthropic
			if modelConfig.Provider == "anthropic" {
				if !anthropicPattern.MatchString(modelKey) {
					return nil, "", time.Time{}, fmt.Errorf("model key %q does not match pattern claude-<family>-<version> for provider anthropic", modelKey)
				}
			}

			// Check that provider exists
			if modelConfig.Provider != "" {
				if raw.Providers == nil || raw.Providers[modelConfig.Provider] == nil {
					return nil, "", time.Time{}, fmt.Errorf("model %q references unknown provider %q", modelKey, modelConfig.Provider)
				}
			}

			// Create Rates entry for this model
		rates := &Rates{
			Tier:       modelConfig.Tier,
			Input:      modelConfig.Input,
			Output:     modelConfig.Output,
			CacheWrite: modelConfig.CacheWrite,
			CacheRead:  modelConfig.CacheRead,
		}

			prices[modelKey] = rates
		}
	}

	sha256Hash := fmt.Sprintf("%x", sha256.Sum256(data))
	timestamp := time.Now()

	return prices, sha256Hash, timestamp, nil
}

// checkLegacyFormat checks if the TOML file contains legacy flat [claude-*] entries.
func checkLegacyFormat(data []byte) error {
	legacyPattern := regexp.MustCompile(`^\[claude-[a-z0-9-]+\]`)
	lines := string(data)
	for _, line := range regexp.MustCompile(`\n`).Split(lines, -1) {
		line = regexp.MustCompile(`^\s+`).ReplaceAllString(line, "")
		if legacyPattern.MatchString(line) {
			return fmt.Errorf("legacy flat [claude-*] format detected; use nested [providers.<name>] and [models.<key>] instead")
		}
	}
	return nil
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
