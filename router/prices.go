package main

import (
	"crypto/sha256"
	"fmt"
	"os"
	"regexp"
	"strings"
	"time"

	"github.com/BurntSushi/toml"
)

// legacyFormatRunID is the run id required in the reject-old-flat-shape error
// message (charter 8) — see model-version-spec-20260713-04-36.
const legacyFormatRunID = "model-version-spec-20260713-04-36"

// validAuthModes is the closed enum for Provider.Auth (charter 6): only these
// two modes exist, so any other value must be a load error rather than
// silently degrading to passthrough and leaking an Anthropic credential.
var validAuthModes = map[string]bool{
	"passthrough": true,
	"none":        true,
}

// Tier is a label for pricing tiers: small, medium, large, huge.
type Tier string

const (
	Small  Tier = "small"
	Medium Tier = "medium"
	Large  Tier = "large"
	Huge   Tier = "huge"
)

// Rates holds the per-model pricing rates in USD per million tokens, plus
// the provider/family/version/effective-url/auth-mode resolved at load time.
type Rates struct {
	Tier         string  `toml:"tier"`
	Input        float64 `toml:"input"`
	Output       float64 `toml:"output"`
	CacheWrite   float64 `toml:"cache_write"`
	CacheRead    float64 `toml:"cache_read"`
	Provider     string
	Family       string
	Version      string
	EffectiveURL string
	AuthMode     string
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

	// Validate every declared provider's auth mode before any model resolves
	// against it (charter 6).
	if err := validateProviderAuthModes(raw.Providers); err != nil {
		return nil, "", time.Time{}, err
	}

	// Build the price table from the new structure
	prices := make(PriceTable)
	for modelKey, modelConfig := range raw.Models {
		if modelConfig == nil {
			continue
		}
		rates, err := resolveModelRates(modelKey, modelConfig, raw.Providers)
		if err != nil {
			return nil, "", time.Time{}, err
		}
		prices[modelKey] = rates
	}

	sha256Hash := fmt.Sprintf("%x", sha256.Sum256(data))
	timestamp := time.Now()

	return prices, sha256Hash, timestamp, nil
}

// validateProviderAuthModes checks every declared provider's auth mode
// against the closed enum (charter 6), normalizing the empty-string default
// onto the provider itself so downstream resolution reads one canonical
// value.
func validateProviderAuthModes(providers map[string]*Provider) error {
	for providerName, provider := range providers {
		if provider == nil {
			continue
		}
		if provider.Auth == "" {
			provider.Auth = "passthrough"
		}
		if !validAuthModes[provider.Auth] {
			return fmt.Errorf("provider %q has invalid auth mode %q; must be one of \"passthrough\", \"none\"", providerName, provider.Auth)
		}
	}
	return nil
}

// resolveModelRates validates a single model entry against its provider
// (existence, Anthropic key composition) and resolves its effective URL and
// auth mode into a Rates value.
func resolveModelRates(modelKey string, modelConfig *Model, providers map[string]*Provider) (*Rates, error) {
	provider, ok := providers[modelConfig.Provider]
	if modelConfig.Provider == "" || !ok || provider == nil {
		return nil, fmt.Errorf("model %q references unknown provider %q", modelKey, modelConfig.Provider)
	}

	// Validate Anthropic key composition: the key must equal
	// claude-<family>-<version> built from the model's own declared fields,
	// not merely match the shape (a shape-only check would let
	// claude-opus-4-8 pair with family=opus, version=9.9).
	if modelConfig.Provider == "anthropic" {
		expectedKey := fmt.Sprintf("claude-%s-%s", modelConfig.Family, strings.ReplaceAll(modelConfig.Version, ".", "-"))
		if modelKey != expectedKey {
			return nil, fmt.Errorf("model key %q does not match composition claude-<family>-<version> of its declared family %q and version %q (expected %q)", modelKey, modelConfig.Family, modelConfig.Version, expectedKey)
		}
	}

	// Resolve effective URL: per-model override else provider URL.
	effectiveURL := modelConfig.URL
	if effectiveURL == "" {
		effectiveURL = provider.URL
	}

	return &Rates{
		Tier:         modelConfig.Tier,
		Input:        modelConfig.Input,
		Output:       modelConfig.Output,
		CacheWrite:   modelConfig.CacheWrite,
		CacheRead:    modelConfig.CacheRead,
		Provider:     modelConfig.Provider,
		Family:       modelConfig.Family,
		Version:      modelConfig.Version,
		EffectiveURL: effectiveURL,
		AuthMode:     provider.Auth,
	}, nil
}

// legacyHeaderPattern matches a legacy flat top-level table header for a
// claude-* model, whether the key is bare or quoted — [claude-opus-4-8],
// ["claude-opus-4-8"], and ['claude-opus-4-8'] all match. Quoted headers are
// valid TOML and are the syntax the pre-migration fixtures used, so they must
// reject too rather than slipping past a bare-header-only check and loading as
// an empty, error-free PriceTable (behavior #2 forbids silent degradation).
var legacyHeaderPattern = regexp.MustCompile(`^\[\s*['"]?claude-[a-z0-9.-]+['"]?\s*\]`)

// checkLegacyFormat checks if the TOML file contains legacy flat [claude-*] entries.
func checkLegacyFormat(data []byte) error {
	for _, line := range strings.Split(string(data), "\n") {
		if legacyHeaderPattern.MatchString(strings.TrimSpace(line)) {
			return fmt.Errorf("legacy flat [claude-*] format detected; use the nested [providers.<name>] and [models.<key>] format instead (run %s)", legacyFormatRunID)
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
