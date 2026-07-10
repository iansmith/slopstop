package main

import (
	"crypto/sha256"
	"fmt"
	"os"
	"path/filepath"
	"testing"
)

// pricesTestTable creates a temporary TOML file with test rate data.
// The TOML is written as an inline string to t.TempDir() and returns the path.
func pricesTestTable(t *testing.T) string {
	tomlContent := `
# Test pricing table

[small]
tier = "small"
input = 0.15
output = 0.60
cache_write = 1.50
cache_read = 0.30

[medium]
tier = "medium"
input = 1.00
output = 5.00
cache_write = 7.50
cache_read = 1.00

[big]
tier = "big"
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
	if prices["big"] == nil {
		t.Errorf("big tier not found in prices")
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
		InputTokens:   1_000_000,
		OutputTokens:  500_000,
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
