package main

import (
	"bytes"
	"compress/flate"
	"compress/gzip"
	"os"
	"path/filepath"
	"testing"
)

// TestDecompressBody covers the response-body decoding the meter relies on to read
// compressed API responses: gzip and deflate round-trip to the original bytes, while
// an absent/unknown encoding or undecodable bytes fall back to the input unchanged.
func TestDecompressBody(t *testing.T) {
	plain := []byte(`{"usage":{"input_tokens":10,"output_tokens":5}}`)

	var gz bytes.Buffer
	zw := gzip.NewWriter(&gz)
	zw.Write(plain)
	zw.Close()

	var fl bytes.Buffer
	fw, _ := flate.NewWriter(&fl, flate.DefaultCompression)
	fw.Write(plain)
	fw.Close()

	cases := []struct {
		name     string
		body     []byte
		encoding string
		want     []byte
	}{
		{"gzip", gz.Bytes(), "gzip", plain},
		{"deflate", fl.Bytes(), "deflate", plain},
		{"identity passthrough", plain, "", plain},
		{"unknown encoding passthrough", plain, "br", plain},
		{"undecodable gzip falls back", []byte("not gzip"), "gzip", []byte("not gzip")},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			got := DecompressBody(tc.body, tc.encoding)
			if !bytes.Equal(got, tc.want) {
				t.Errorf("DecompressBody(%q) = %q, want %q", tc.encoding, got, tc.want)
			}
		})
	}
}

// usageTestFixture is a test helper that loads a fixture file from testdata.
func usageTestFixture(t *testing.T, filename string) []byte {
	t.Helper()
	testdataPath := filepath.Join("testdata", filename)
	data, err := os.ReadFile(testdataPath)
	if err != nil {
		t.Fatalf("failed to load fixture %s: %v", testdataPath, err)
	}
	return data
}

func TestUsageFromJSONAllFourComponents(t *testing.T) {
	body := usageTestFixture(t, "response_nonstreaming.json")
	tokens, ok := UsageFromJSON(body)
	if !ok {
		t.Fatal("UsageFromJSON returned ok=false")
	}

	// Verify all four components are extracted
	if tokens.InputTokens == 0 {
		t.Errorf("InputTokens not extracted: got %d", tokens.InputTokens)
	}
	if tokens.OutputTokens == 0 {
		t.Errorf("OutputTokens not extracted: got %d", tokens.OutputTokens)
	}
	if tokens.CacheCreationInputTokens == 0 {
		t.Errorf("CacheCreationInputTokens not extracted: got %d", tokens.CacheCreationInputTokens)
	}
	if tokens.CacheReadInputTokens == 0 {
		t.Errorf("CacheReadInputTokens not extracted: got %d", tokens.CacheReadInputTokens)
	}
}

func TestUsageFromSSEMatchesJSON(t *testing.T) {
	// Load JSON fixture and extract reference tokens
	jsonBody := usageTestFixture(t, "response_nonstreaming.json")
	jsonTokens, ok := UsageFromJSON(jsonBody)
	if !ok {
		t.Fatalf("UsageFromJSON failed on reference fixture")
	}

	// Load SSE fixture and extract from stream
	sseBody := usageTestFixture(t, "response_stream.sse")
	sseTokens, ok := UsageFromSSE(sseBody)
	if !ok {
		t.Fatalf("UsageFromSSE returned ok=false")
	}

	// Verify all components match
	if sseTokens.InputTokens != jsonTokens.InputTokens {
		t.Errorf("InputTokens mismatch: JSON=%d, SSE=%d", jsonTokens.InputTokens, sseTokens.InputTokens)
	}
	if sseTokens.OutputTokens != jsonTokens.OutputTokens {
		t.Errorf("OutputTokens mismatch: JSON=%d, SSE=%d", jsonTokens.OutputTokens, sseTokens.OutputTokens)
	}
	if sseTokens.CacheCreationInputTokens != jsonTokens.CacheCreationInputTokens {
		t.Errorf("CacheCreationInputTokens mismatch: JSON=%d, SSE=%d", jsonTokens.CacheCreationInputTokens, sseTokens.CacheCreationInputTokens)
	}
	if sseTokens.CacheReadInputTokens != jsonTokens.CacheReadInputTokens {
		t.Errorf("CacheReadInputTokens mismatch: JSON=%d, SSE=%d", jsonTokens.CacheReadInputTokens, sseTokens.CacheReadInputTokens)
	}
}

func TestSSECumulativeNotSummed(t *testing.T) {
	// The SSE fixture must have cumulative message_delta events.
	// With deltas of 50 then 120, sum would be 170, but final value should be 120.
	sseBody := usageTestFixture(t, "response_stream.sse")
	tokens, ok := UsageFromSSE(sseBody)
	if !ok {
		t.Fatalf("UsageFromSSE returned ok=false")
	}

	// The fixture design specifies that cumulative output is 120 (the final value),
	// not 170 (the sum of deltas).
	if tokens.OutputTokens != 120 {
		t.Errorf("OutputTokens should be final cumulative value (120), not sum. Got %d", tokens.OutputTokens)
	}
}

func TestMalformedReturnsNotOK(t *testing.T) {
	tests := map[string][]byte{
		"truncated JSON":    []byte(`{"usage":{"input_tokens":10,"output`),
		"garbage bytes":     []byte{0xFF, 0xFE, 0xFD, 0xFC},
		"empty":             []byte(""),
		"invalid JSON":      []byte(`{not valid json}`),
		"missing usage key": []byte(`{"other_key":"value"}`),
	}

	for name, body := range tests {
		t.Run(name, func(t *testing.T) {
			tokens, ok := UsageFromJSON(body)
			if ok {
				t.Errorf("expected ok=false for malformed input, got ok=true, tokens=%+v", tokens)
			}
			// Verify tokens are zero on error
			if tokens.InputTokens != 0 || tokens.OutputTokens != 0 ||
				tokens.CacheCreationInputTokens != 0 || tokens.CacheReadInputTokens != 0 {
				t.Errorf("expected zero tokens on error, got %+v", tokens)
			}
		})
	}
}

func TestNoPanicOnGarbage(t *testing.T) {
	// Verify that garbage input does not cause panic
	garbageInputs := [][]byte{
		{0xFF, 0xFE, 0xFD},
		[]byte("completely random bytes ~!@#$%^&*()"),
		[]byte("\x00\x01\x02\x03"),
	}

	for _, garbage := range garbageInputs {
		// Should not panic
		_, _ = UsageFromJSON(garbage)
		_, _ = UsageFromSSE(garbage)
	}
}

func TestModelFromRequest(t *testing.T) {
	tests := map[string]struct {
		body          []byte
		expectedModel string
		expectOK      bool
	}{
		"valid model": {
			body:          []byte(`{"model":"claude-opus-4-8"}`),
			expectedModel: "claude-opus-4-8",
			expectOK:      true,
		},
		"different model": {
			body:          []byte(`{"model":"claude-haiku-4-5"}`),
			expectedModel: "claude-haiku-4-5",
			expectOK:      true,
		},
		"no model field": {
			body:     []byte(`{"other":"value"}`),
			expectOK: false,
		},
		"empty JSON": {
			body:     []byte(`{}`),
			expectOK: false,
		},
		"invalid JSON": {
			body:     []byte(`{invalid}`),
			expectOK: false,
		},
	}

	for name, tt := range tests {
		t.Run(name, func(t *testing.T) {
			model, ok := ModelFromRequest(tt.body)
			if ok != tt.expectOK {
				t.Errorf("expected ok=%v, got ok=%v", tt.expectOK, ok)
			}
			if ok && model != tt.expectedModel {
				t.Errorf("expected model=%q, got model=%q", tt.expectedModel, model)
			}
			if !ok && model != "" {
				t.Errorf("expected empty model on error, got %q", model)
			}
		})
	}
}
