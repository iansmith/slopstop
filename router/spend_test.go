package main

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

func TestMissingPrefixReturns400(t *testing.T) {
	meter := NewMeter()
	table := make(PriceTable)
	handler := spendHandler(meter, table, "", "")

	req := httptest.NewRequest("GET", "/spend", nil)
	w := httptest.NewRecorder()
	handler(w, req)

	if w.Code != http.StatusBadRequest {
		t.Errorf("expected 400, got %d", w.Code)
	}
	body := w.Body.String()
	if body == "" {
		t.Error("expected error message in body, got empty")
	}
	if len(body) < 10 {
		t.Errorf("expected descriptive error message, got: %s", body)
	}
}

func TestUnknownPrefixReturns200Zeros(t *testing.T) {
	meter := NewMeter()
	table := make(PriceTable)
	handler := spendHandler(meter, table, "", "")

	req := httptest.NewRequest("GET", "/spend?prefix=unknown", nil)
	w := httptest.NewRecorder()
	handler(w, req)

	if w.Code != http.StatusOK {
		t.Errorf("expected 200, got %d", w.Code)
	}

	var response map[string]interface{}
	if err := json.Unmarshal(w.Body.Bytes(), &response); err != nil {
		t.Fatalf("failed to unmarshal response: %v", err)
	}

	// Verify it's NOT a 404-like response (should have data structure)
	if _, ok := response["prefix"]; !ok {
		t.Error("expected 'prefix' key in response")
	}
	// Verify aggregates are zeroed
	if requests, ok := response["requests"].(float64); ok && requests != 0 {
		t.Errorf("expected requests=0 for unknown prefix, got %v", requests)
	}
}

func TestKnownPrefixUnknownRunReturns200Zeros(t *testing.T) {
	meter := NewMeter()
	table := make(PriceTable)
	handler := spendHandler(meter, table, "", "")

	// Record something with known prefix to make it "known"
	meter.Record(Tags{Prefix: "TEST", Run: "run1", Ticket: "TEST-1"}, "claude-3-opus", string(Medium), Tokens{InputTokens: 100}, 0.01, true)

	req := httptest.NewRequest("GET", "/spend?prefix=TEST&run=unknown-run", nil)
	w := httptest.NewRecorder()
	handler(w, req)

	if w.Code != http.StatusOK {
		t.Errorf("expected 200 for known prefix + unknown run, got %d", w.Code)
	}

	var response map[string]interface{}
	if err := json.Unmarshal(w.Body.Bytes(), &response); err != nil {
		t.Fatalf("failed to unmarshal response: %v", err)
	}

	// Verify aggregates are zeroed for unknown run
	if requests, ok := response["requests"].(float64); ok && requests != 0 {
		t.Errorf("expected requests=0 for unknown run, got %v", requests)
	}
}

func TestRunKeyOnlyWhenRequested(t *testing.T) {
	meter := NewMeter()
	table := make(PriceTable)
	handler := spendHandler(meter, table, "", "")

	// Request without &run=
	req1 := httptest.NewRequest("GET", "/spend?prefix=TEST", nil)
	w1 := httptest.NewRecorder()
	handler(w1, req1)

	var resp1 map[string]interface{}
	json.Unmarshal(w1.Body.Bytes(), &resp1)
	if _, hasRun := resp1["run"]; hasRun {
		t.Error("expected 'run' key to be absent when &run= not supplied")
	}

	// Request with &run=
	req2 := httptest.NewRequest("GET", "/spend?prefix=TEST&run=myrun", nil)
	w2 := httptest.NewRecorder()
	handler(w2, req2)

	var resp2 map[string]interface{}
	json.Unmarshal(w2.Body.Bytes(), &resp2)
	if _, hasRun := resp2["run"]; !hasRun {
		t.Error("expected 'run' key to be present when &run= supplied")
	}
}

func TestResponseKeySetMatchesPRD(t *testing.T) {
	meter := NewMeter()
	table := make(PriceTable)
	handler := spendHandler(meter, table, "", "")

	req := httptest.NewRequest("GET", "/spend?prefix=TEST&run=myrun", nil)
	w := httptest.NewRecorder()
	handler(w, req)

	var response map[string]interface{}
	if err := json.Unmarshal(w.Body.Bytes(), &response); err != nil {
		t.Fatalf("failed to unmarshal response: %v", err)
	}

	// Expected keys per PRD D6
	expectedKeys := map[string]bool{
		"prefix":            true,
		"run":               true, // present because &run= supplied
		"router_started_at": true,
		"requests":          true,
		"total_usd":         true,
		"by_tier":           true,
		"by_ticket":         true,
		"by_model":          true,
		"unpriced":          true,
		"prices":            true,
	}

	for key := range response {
		if !expectedKeys[key] {
			t.Errorf("unexpected key in response: %s", key)
		}
		if key == "unmetered" {
			t.Error("response contains forbidden 'unmetered' key")
		}
	}

	for key := range expectedKeys {
		if key == "run" {
			// run is conditional, already checked in TestRunKeyOnlyWhenRequested
			continue
		}
		if _, ok := response[key]; !ok {
			t.Errorf("missing expected key: %s", key)
		}
	}

	// Explicitly verify no unmetered key anywhere
	jsonStr, _ := json.Marshal(response)
	if strings.Contains(string(jsonStr), "unmetered") {
		t.Error("'unmetered' key found in serialized response")
	}
}

func TestByModelIsRecomputable(t *testing.T) {
	meter := NewMeter()
	table := make(PriceTable)
	table["test-model"] = &Rates{
		Input:      1.0,
		Output:     2.0,
		CacheWrite: 0.5,
		CacheRead:  0.25,
	}
	handler := spendHandler(meter, table, "", "")

	// Record with known pricing
	tokens := Tokens{
		InputTokens:              1000000, // 1M = $1.00
		OutputTokens:             500000,  // 0.5M = $1.00
		CacheCreationInputTokens: 1000000, // 1M = $0.50
		CacheReadInputTokens:     1000000, // 1M = $0.25
	}
	meter.Record(Tags{Prefix: "TEST", Run: "run1", Ticket: "TEST-1"}, "test-model", string(Medium), tokens, 2.75, true)

	req := httptest.NewRequest("GET", "/spend?prefix=TEST&run=run1", nil)
	w := httptest.NewRecorder()
	handler(w, req)

	var response map[string]interface{}
	json.Unmarshal(w.Body.Bytes(), &response)

	byModel, ok := response["by_model"].([]interface{})
	if !ok || len(byModel) == 0 {
		t.Fatal("expected non-empty by_model array")
	}

	// Get first model entry
	modelEntry, ok := byModel[0].(map[string]interface{})
	if !ok {
		t.Fatal("expected by_model[0] to be object")
	}

	// Extract values for recomputation
	model, ok := modelEntry["model"].(string)
	if !ok || model != "test-model" {
		t.Fatalf("expected model='test-model', got %v", model)
	}

	tokensObj, ok := modelEntry["tokens"].(map[string]interface{})
	if !ok {
		t.Fatal("expected tokens object")
	}

	ratesObj, ok := modelEntry["rates_per_mtok"].(map[string]interface{})
	if !ok {
		t.Fatal("expected rates_per_mtok object")
	}

	inputTokens, _ := tokensObj["input_tokens"].(float64)
	outputTokens, _ := tokensObj["output_tokens"].(float64)
	cacheWriteTokens, _ := tokensObj["cache_creation_input_tokens"].(float64)
	cacheReadTokens, _ := tokensObj["cache_read_input_tokens"].(float64)

	inputRate, _ := ratesObj["input"].(float64)
	outputRate, _ := ratesObj["output"].(float64)
	writeRate, _ := ratesObj["cache_write"].(float64)
	readRate, _ := ratesObj["cache_read"].(float64)

	// Recompute USD
	recomputedUSD := (inputTokens/1e6)*inputRate +
		(outputTokens/1e6)*outputRate +
		(cacheWriteTokens/1e6)*writeRate +
		(cacheReadTokens/1e6)*readRate

	reportedUSD, ok := modelEntry["usd"].(float64)
	if !ok {
		t.Fatal("expected usd field in model entry")
	}

	const epsilon = 0.00001
	if diff := recomputedUSD - reportedUSD; diff < -epsilon || diff > epsilon {
		t.Errorf("recomputed USD (%.5f) != reported USD (%.5f), diff=%.5f", recomputedUSD, reportedUSD, diff)
	}
}

