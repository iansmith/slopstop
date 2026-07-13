package main

import (
	"crypto/sha256"
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

// pricesTestTable creates a temporary TOML file with test rate data using the new nested format.
// The TOML is written as an inline string to t.TempDir() and returns the path.
func pricesTestTable(t *testing.T) string {
	tomlContent := `
# Test pricing table

[providers.test]
url = "https://test.example.com"
auth = "passthrough"

[models."small"]
provider = "test"
family = "small"
version = "1.0"
tier = "small"
input = 0.15
output = 0.60
cache_write = 1.50
cache_read = 0.30

[models."medium"]
provider = "test"
family = "medium"
version = "1.0"
tier = "medium"
input = 1.00
output = 5.00
cache_write = 7.50
cache_read = 1.00

[models."large"]
provider = "test"
family = "large"
version = "1.0"
tier = "large"
input = 3.00
output = 15.00
cache_write = 22.50
cache_read = 3.00
`

	tmpDir := t.TempDir()
	path := filepath.Join(tmpDir, "prices.toml")
	if err := os.WriteFile(path, []byte(tomlContent), 0644); err != nil {
		t.Fatalf("failed to write test TOML: %v", err)
	}
	return path
}

// TestLoadFixtureTable tests that LoadPrices can decode a TOML fixture.
func TestLoadFixtureTable(t *testing.T) {
	path := pricesTestTable(t)
	prices, sha256Hash, timestamp, err := LoadPrices(path)
	if err != nil {
		t.Fatalf("LoadPrices failed: %v", err)
	}

	if prices == nil {
		t.Errorf("LoadPrices returned nil prices map")
	}

	if len(prices) == 0 {
		t.Errorf("LoadPrices returned empty prices map")
	}

	// Verify we can access the tier entries
	if prices["small"] == nil {
		t.Errorf("small tier not found in prices")
	}
	if prices["medium"] == nil {
		t.Errorf("medium tier not found in prices")
	}
	if prices["large"] == nil {
		t.Errorf("large tier not found in prices")
	}

	if sha256Hash == "" {
		t.Errorf("LoadPrices returned empty SHA256 hash")
	}

	if timestamp.IsZero() {
		t.Errorf("LoadPrices returned zero timestamp")
	}
}

// TestCostArithmeticHandComputed tests the exact arithmetic:
// 1,000,000 input tokens @ $1.00/MTok + 500,000 output tokens @ $5.00/MTok = $3.50
func TestCostArithmeticHandComputed(t *testing.T) {
	path := pricesTestTable(t)
	prices, _, _, err := LoadPrices(path)
	if err != nil {
		t.Fatalf("LoadPrices failed: %v", err)
	}

	// Using the "medium" tier from the fixture
	tokens := Tokens{
		InputTokens:  1_000_000,
		OutputTokens: 500_000,
	}

	usd, known := prices.Cost("medium", tokens)
	if !known {
		t.Errorf("Cost returned known=false for medium tier")
	}

	// Expected: (1_000_000 / 1e6) * 1.00 + (500_000 / 1e6) * 5.00
	//         = 1.00 + 2.50 = 3.50
	expected := 3.50
	if usd != expected {
		t.Errorf("Cost returned %.10f, expected %.10f", usd, expected)
	}
}

// TestUnknownModelZeroPricedKnownFalse tests that an unknown model returns known=false, usd=0, no error.
func TestUnknownModelZeroPricedKnownFalse(t *testing.T) {
	path := pricesTestTable(t)
	prices, _, _, err := LoadPrices(path)
	if err != nil {
		t.Fatalf("LoadPrices failed: %v", err)
	}

	tokens := Tokens{
		InputTokens:  1000,
		OutputTokens: 500,
	}

	usd, known := prices.Cost("unknown-model-xyz", tokens)
	if known {
		t.Errorf("Cost returned known=true for unknown model, expected false")
	}

	if usd != 0 {
		t.Errorf("Cost returned usd=%.2f for unknown model, expected 0", usd)
	}
}

// TestSha256MatchesFile tests that LoadPrices returns a SHA256 equal to `shasum -a 256 <file>`.
func TestSha256MatchesFile(t *testing.T) {
	path := pricesTestTable(t)
	_, returnedHash, _, err := LoadPrices(path)
	if err != nil {
		t.Fatalf("LoadPrices failed: %v", err)
	}

	// Compute SHA256 independently
	data, err := os.ReadFile(path)
	if err != nil {
		t.Fatalf("failed to read file: %v", err)
	}
	expectedHash := fmt.Sprintf("%x", sha256.Sum256(data))

	if returnedHash != expectedHash {
		t.Errorf("LoadPrices returned hash %q, expected %q", returnedHash, expectedHash)
	}
}

// TestAllFourComponentsPriced tests that all four token components contribute to the cost.
func TestAllFourComponentsPriced(t *testing.T) {
	path := pricesTestTable(t)
	prices, _, _, err := LoadPrices(path)
	if err != nil {
		t.Fatalf("LoadPrices failed: %v", err)
	}

	// Use small tier with one token of each type
	tokens := Tokens{
		InputTokens:              1_000_000,
		OutputTokens:             1_000_000,
		CacheCreationInputTokens: 1_000_000,
		CacheReadInputTokens:     1_000_000,
	}

	usd, known := prices.Cost("small", tokens)
	if !known {
		t.Errorf("Cost returned known=false for small tier")
	}

	// Expected (small tier):
	// input:       (1_000_000 / 1e6) * 0.15 = 0.15
	// output:      (1_000_000 / 1e6) * 0.60 = 0.60
	// cache_write: (1_000_000 / 1e6) * 1.50 = 1.50
	// cache_read:  (1_000_000 / 1e6) * 0.30 = 0.30
	// Total = 2.55
	expected := 2.55
	if usd != expected {
		t.Errorf("Cost returned %.10f, expected %.10f", usd, expected)
	}
}

// TestCostWithZeroTokens tests that zero tokens return $0 cost.
func TestCostWithZeroTokens(t *testing.T) {
	path := pricesTestTable(t)
	prices, _, _, err := LoadPrices(path)
	if err != nil {
		t.Fatalf("LoadPrices failed: %v", err)
	}

	tokens := Tokens{}

	usd, known := prices.Cost("medium", tokens)
	if !known {
		t.Errorf("Cost returned known=false for medium tier")
	}

	if usd != 0.0 {
		t.Errorf("Cost returned %.2f for zero tokens, expected 0.0", usd)
	}
}

// TestRealPricesTomlTierMapping loads the committed prices.toml and asserts the
// four-tier mapping (umbrella #237): haiku-4-5=small, sonnet-5=medium,
// opus-4-8=large, fable-5=huge. Mutation-resistant: reverting any tier label in
// prices.toml (e.g. reverting fable-5 to its old label) fails this test.
func TestRealPricesTomlTierMapping(t *testing.T) {
	prices, _, _, err := LoadPrices("prices.toml")
	if err != nil {
		t.Fatalf("LoadPrices(\"prices.toml\") failed: %v", err)
	}
	want := map[string]string{
		"claude-haiku-4-5": "small",
		"claude-sonnet-5":  "medium",
		"claude-opus-4-8":  "large",
		"claude-fable-5":   "huge",
	}
	for model, tier := range want {
		r, ok := prices[model]
		if !ok {
			t.Errorf("model %q missing from prices.toml", model)
			continue
		}
		if r.Tier != tier {
			t.Errorf("prices.toml %s tier: got %q, want %q", model, r.Tier, tier)
		}
	}
}

// TestParserHandlesNestedProviderModelsStructure tests that LoadPrices can parse
// the new [providers.<name>] and [models.<key>] nested structure.
func TestParserHandlesNestedProviderModelsStructure(t *testing.T) {
	tomlContent := `
[providers.anthropic]
url = "https://api.anthropic.com"
auth = "passthrough"

[models."claude-opus-4-8"]
provider = "anthropic"
family = "opus"
version = "4.8"
tier = "large"
input = 6.50
output = 32.50
cache_write = 8.125
cache_read = 0.65
`
	tmpDir := t.TempDir()
	path := filepath.Join(tmpDir, "prices.toml")
	if err := os.WriteFile(path, []byte(tomlContent), 0644); err != nil {
		t.Fatalf("failed to write test TOML: %v", err)
	}

	prices, _, _, err := LoadPrices(path)
	if err != nil {
		t.Fatalf("LoadPrices failed: %v", err)
	}

	if prices == nil {
		t.Errorf("LoadPrices returned nil prices map")
	}

	if len(prices) == 0 {
		t.Errorf("LoadPrices returned empty prices map")
	}

	if prices["claude-opus-4-8"] == nil {
		t.Errorf("claude-opus-4-8 not found in prices")
	}
}

// TestLegacyFlatFormatRejected tests that flat top-level [claude-*] tables
// trigger load errors with informative messages.
func TestLegacyFlatFormatRejected(t *testing.T) {
	tomlContent := `
[claude-opus-4-8]
tier = "large"
input = 6.50
output = 32.50
cache_write = 8.125
cache_read = 0.65
`
	tmpDir := t.TempDir()
	path := filepath.Join(tmpDir, "prices.toml")
	if err := os.WriteFile(path, []byte(tomlContent), 0644); err != nil {
		t.Fatalf("failed to write test TOML: %v", err)
	}

	_, _, _, err := LoadPrices(path)
	if err == nil {
		t.Fatalf("LoadPrices did not reject legacy flat [claude-*] format")
	}
	msg := err.Error()
	if !strings.Contains(msg, "providers") || !strings.Contains(msg, "models") {
		t.Errorf("error message %q does not name the new [providers]/[models] format", msg)
	}
	if !strings.Contains(msg, "model-version-spec-20260713-04-36") {
		t.Errorf("error message %q does not contain the required run id model-version-spec-20260713-04-36", msg)
	}
}

// TestURLResolutionModelInheritsProvider tests that models inherit provider URLs
// unless overridden.
func TestURLResolutionModelInheritsProvider(t *testing.T) {
	tomlContent := `
[providers.anthropic]
url = "https://api.anthropic.com"
auth = "passthrough"

[providers.custom]
url = "https://custom.api.example.com"
auth = "passthrough"

[models."claude-opus-4-8"]
provider = "anthropic"
family = "opus"
version = "4.8"
tier = "large"
input = 6.50
output = 32.50
cache_write = 8.125
cache_read = 0.65

[models."claude-sonnet-5"]
provider = "custom"
family = "sonnet"
version = "5"
tier = "medium"
input = 2.60
output = 13.00
cache_write = 3.25
cache_read = 0.26
`
	tmpDir := t.TempDir()
	path := filepath.Join(tmpDir, "prices.toml")
	if err := os.WriteFile(path, []byte(tomlContent), 0644); err != nil {
		t.Fatalf("failed to write test TOML: %v", err)
	}

	_, _, _, err := LoadPrices(path)
	if err != nil {
		t.Fatalf("LoadPrices failed: %v", err)
	}
}

// TestAnthropicNamingValidation tests that keys for provider="anthropic" must
// match the pattern claude-<family>-<version>.
func TestAnthropicNamingValidation(t *testing.T) {
	tomlContent := `
[providers.anthropic]
url = "https://api.anthropic.com"
auth = "passthrough"

[models."invalid-model-key"]
provider = "anthropic"
family = "opus"
version = "4.8"
tier = "large"
input = 6.50
output = 32.50
cache_write = 8.125
cache_read = 0.65
`
	tmpDir := t.TempDir()
	path := filepath.Join(tmpDir, "prices.toml")
	if err := os.WriteFile(path, []byte(tomlContent), 0644); err != nil {
		t.Fatalf("failed to write test TOML: %v", err)
	}

	_, _, _, err := LoadPrices(path)
	if err == nil {
		t.Errorf("LoadPrices did not reject invalid Anthropic model key")
	}
}

// TestRatePreservationTransferred (rates-numbers-neutral) tests that all four
// production Anthropic models' rate values are byte-for-byte equal to the
// pre-migration prices.toml figures, loaded from the real committed file.
func TestRatePreservationTransferred(t *testing.T) {
	prices, _, _, err := LoadPrices("prices.toml")
	if err != nil {
		t.Fatalf("LoadPrices(\"prices.toml\") failed: %v", err)
	}

	type want struct {
		input, output, cacheWrite, cacheRead float64
	}
	wantRates := map[string]want{
		"claude-haiku-4-5": {input: 1.00, output: 5.00, cacheWrite: 1.25, cacheRead: 0.10},
		"claude-sonnet-5":  {input: 2.60, output: 13.00, cacheWrite: 3.25, cacheRead: 0.26},
		"claude-opus-4-8":  {input: 6.50, output: 32.50, cacheWrite: 8.125, cacheRead: 0.65},
		"claude-fable-5":   {input: 13.00, output: 65.00, cacheWrite: 16.25, cacheRead: 1.30},
	}

	for model, w := range wantRates {
		rate, ok := prices[model]
		if !ok {
			t.Errorf("%s not found in prices.toml", model)
			continue
		}
		if rate.Input != w.input {
			t.Errorf("%s Input: got %v, want %v", model, rate.Input, w.input)
		}
		if rate.Output != w.output {
			t.Errorf("%s Output: got %v, want %v", model, rate.Output, w.output)
		}
		if rate.CacheWrite != w.cacheWrite {
			t.Errorf("%s CacheWrite: got %v, want %v", model, rate.CacheWrite, w.cacheWrite)
		}
		if rate.CacheRead != w.cacheRead {
			t.Errorf("%s CacheRead: got %v, want %v", model, rate.CacheRead, w.cacheRead)
		}
	}
}

// TestAuthEnumRejectsThirdValue tests that a provider's auth field outside
// {"passthrough", "none"} is a load error (charter 6).
func TestAuthEnumRejectsThirdValue(t *testing.T) {
	tomlContent := `
[providers.anthropic]
url = "https://api.anthropic.com"
auth = "bogus-mode"

[models."claude-opus-4-8"]
provider = "anthropic"
family = "opus"
version = "4.8"
tier = "large"
input = 6.50
output = 32.50
cache_write = 8.125
cache_read = 0.65
`
	tmpDir := t.TempDir()
	path := filepath.Join(tmpDir, "prices.toml")
	if err := os.WriteFile(path, []byte(tomlContent), 0644); err != nil {
		t.Fatalf("failed to write test TOML: %v", err)
	}

	_, _, _, err := LoadPrices(path)
	if err == nil {
		t.Fatalf("LoadPrices did not reject auth = \"bogus-mode\"")
	}
	if !strings.Contains(err.Error(), "bogus-mode") {
		t.Errorf("error message %q does not name the rejected auth value", err.Error())
	}
}

// TestEffectiveURLResolutionWithPerModelOverride tests that a model with no
// per-model URL inherits its provider's URL, and a model with an explicit
// per-model URL override resolves to that override instead.
func TestEffectiveURLResolutionWithPerModelOverride(t *testing.T) {
	tomlContent := `
[providers.anthropic]
url = "https://api.anthropic.com"
auth = "passthrough"

[models."claude-opus-4-8"]
provider = "anthropic"
family = "opus"
version = "4.8"
tier = "large"
input = 6.50
output = 32.50
cache_write = 8.125
cache_read = 0.65

[models."claude-sonnet-5"]
provider = "anthropic"
family = "sonnet"
version = "5"
tier = "medium"
url = "https://custom-endpoint.example.com/v1"
input = 2.60
output = 13.00
cache_write = 3.25
cache_read = 0.26
`
	tmpDir := t.TempDir()
	path := filepath.Join(tmpDir, "prices.toml")
	if err := os.WriteFile(path, []byte(tomlContent), 0644); err != nil {
		t.Fatalf("failed to write test TOML: %v", err)
	}

	prices, _, _, err := LoadPrices(path)
	if err != nil {
		t.Fatalf("LoadPrices failed: %v", err)
	}

	inherited, ok := prices["claude-opus-4-8"]
	if !ok {
		t.Fatalf("claude-opus-4-8 not found in prices")
	}
	if inherited.EffectiveURL != "https://api.anthropic.com" {
		t.Errorf("claude-opus-4-8 EffectiveURL: got %q, want provider URL %q (inherited, no override)", inherited.EffectiveURL, "https://api.anthropic.com")
	}
	if inherited.AuthMode != "passthrough" {
		t.Errorf("claude-opus-4-8 AuthMode: got %q, want %q", inherited.AuthMode, "passthrough")
	}

	overridden, ok := prices["claude-sonnet-5"]
	if !ok {
		t.Fatalf("claude-sonnet-5 not found in prices")
	}
	if overridden.EffectiveURL != "https://custom-endpoint.example.com/v1" {
		t.Errorf("claude-sonnet-5 EffectiveURL: got %q, want per-model override %q", overridden.EffectiveURL, "https://custom-endpoint.example.com/v1")
	}
}

// TestAnthropicKeyCompositionMismatchErrors tests that an anthropic model key
// which matches the claude-<family>-<version> shape but does not actually
// compose from the model's declared family/version fields is a load error.
func TestAnthropicKeyCompositionMismatchErrors(t *testing.T) {
	tomlContent := `
[providers.anthropic]
url = "https://api.anthropic.com"
auth = "passthrough"

[models."claude-opus-4-8"]
provider = "anthropic"
family = "opus"
version = "9.9"
tier = "large"
input = 6.50
output = 32.50
cache_write = 8.125
cache_read = 0.65
`
	tmpDir := t.TempDir()
	path := filepath.Join(tmpDir, "prices.toml")
	if err := os.WriteFile(path, []byte(tomlContent), 0644); err != nil {
		t.Fatalf("failed to write test TOML: %v", err)
	}

	_, _, _, err := LoadPrices(path)
	if err == nil {
		t.Fatalf("LoadPrices did not reject key/family+version composition mismatch (key claude-opus-4-8 vs family=opus version=9.9)")
	}
	if !strings.Contains(err.Error(), "claude-opus-4-8") || !strings.Contains(err.Error(), "9.9") {
		t.Errorf("error message %q does not name both the key and the mismatched composition", err.Error())
	}
}

// TestUnknownProviderErrors tests that a model referencing a provider not
// present in [providers.*] is a load error.
func TestUnknownProviderErrors(t *testing.T) {
	tomlContent := `
[providers.anthropic]
url = "https://api.anthropic.com"
auth = "passthrough"

[models."claude-opus-4-8"]
provider = "nonexistent-provider"
family = "opus"
version = "4.8"
tier = "large"
input = 6.50
output = 32.50
cache_write = 8.125
cache_read = 0.65
`
	tmpDir := t.TempDir()
	path := filepath.Join(tmpDir, "prices.toml")
	if err := os.WriteFile(path, []byte(tomlContent), 0644); err != nil {
		t.Fatalf("failed to write test TOML: %v", err)
	}

	_, _, _, err := LoadPrices(path)
	if err == nil {
		t.Fatalf("LoadPrices did not reject model referencing unknown provider")
	}
	if !strings.Contains(err.Error(), "nonexistent-provider") {
		t.Errorf("error message %q does not name the unknown provider", err.Error())
	}
}

// TestEmptyProvidersTable tests that a manifest with models but no
// [providers.*] table at all is a load error (every model's provider
// reference is necessarily unknown).
func TestEmptyProvidersTable(t *testing.T) {
	tomlContent := `
[models."claude-opus-4-8"]
provider = "anthropic"
family = "opus"
version = "4.8"
tier = "large"
input = 6.50
output = 32.50
cache_write = 8.125
cache_read = 0.65
`
	tmpDir := t.TempDir()
	path := filepath.Join(tmpDir, "prices.toml")
	if err := os.WriteFile(path, []byte(tomlContent), 0644); err != nil {
		t.Fatalf("failed to write test TOML: %v", err)
	}

	_, _, _, err := LoadPrices(path)
	if err == nil {
		t.Fatalf("LoadPrices did not reject a model referencing a provider when no [providers] table is present at all")
	}
}

// TestDuplicateModelKeyRejected tests that a manifest with a repeated
// [models."x"] table header is rejected as a TOML parse error rather than
// silently keeping one of the two definitions.
func TestDuplicateModelKeyRejected(t *testing.T) {
	tomlContent := `
[providers.anthropic]
url = "https://api.anthropic.com"
auth = "passthrough"

[models."claude-opus-4-8"]
provider = "anthropic"
family = "opus"
version = "4.8"
tier = "large"
input = 6.50
output = 32.50
cache_write = 8.125
cache_read = 0.65

[models."claude-opus-4-8"]
provider = "anthropic"
family = "opus"
version = "4.8"
tier = "large"
input = 999.0
output = 999.0
cache_write = 999.0
cache_read = 999.0
`
	tmpDir := t.TempDir()
	path := filepath.Join(tmpDir, "prices.toml")
	if err := os.WriteFile(path, []byte(tomlContent), 0644); err != nil {
		t.Fatalf("failed to write test TOML: %v", err)
	}

	_, _, _, err := LoadPrices(path)
	if err == nil {
		t.Fatalf("LoadPrices did not reject duplicate [models.\"claude-opus-4-8\"] table headers")
	}
}
