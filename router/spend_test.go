package main

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"
)

func TestMissingPrefixReturns400(t *testing.T) {
	meter := NewMeter()
	table := make(PriceTable)
	handler := spendHandler(meter, table, "", "", time.Now())

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
	if !strings.Contains(body, "prefix") {
		t.Errorf("expected body to name the required parameter 'prefix', got: %s", body)
	}
}

func TestUnknownPrefixReturns200Zeros(t *testing.T) {
	meter := NewMeter()
	table := make(PriceTable)
	handler := spendHandler(meter, table, "", "", time.Now())

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
	handler := spendHandler(meter, table, "", "", time.Now())

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
	handler := spendHandler(meter, table, "", "", time.Now())

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
	handler := spendHandler(meter, table, "", "", time.Now())

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
	handler := spendHandler(meter, table, "", "", time.Now())

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

func TestPricesLoadedAtIsStable(t *testing.T) {
	meter := NewMeter()
	table := make(PriceTable)
	fixedLoadedAt := time.Date(2026, 7, 1, 12, 0, 0, 0, time.UTC)
	handler := spendHandler(meter, table, "test.toml", "abc123", fixedLoadedAt)

	// Issue two requests
	req1 := httptest.NewRequest("GET", "/spend?prefix=TEST", nil)
	w1 := httptest.NewRecorder()
	handler(w1, req1)

	var resp1 map[string]interface{}
	json.Unmarshal(w1.Body.Bytes(), &resp1)

	req2 := httptest.NewRequest("GET", "/spend?prefix=TEST", nil)
	w2 := httptest.NewRecorder()
	handler(w2, req2)

	var resp2 map[string]interface{}
	json.Unmarshal(w2.Body.Bytes(), &resp2)

	// Extract prices.loaded_at from both responses
	prices1, ok := resp1["prices"].(map[string]interface{})
	if !ok {
		t.Fatal("expected prices object in resp1")
	}
	loaded1, ok := prices1["loaded_at"].(string)
	if !ok {
		t.Fatal("expected loaded_at string in resp1")
	}

	prices2, ok := resp2["prices"].(map[string]interface{})
	if !ok {
		t.Fatal("expected prices object in resp2")
	}
	loaded2, ok := prices2["loaded_at"].(string)
	if !ok {
		t.Fatal("expected loaded_at string in resp2")
	}

	// Both should equal the fixed time
	expectedStr := fixedLoadedAt.Format(time.RFC3339)
	if loaded1 != expectedStr {
		t.Errorf("request 1: expected loaded_at=%s, got %s", expectedStr, loaded1)
	}
	if loaded2 != expectedStr {
		t.Errorf("request 2: expected loaded_at=%s, got %s", expectedStr, loaded2)
	}

	// Both responses should have identical loaded_at values
	if loaded1 != loaded2 {
		t.Errorf("loaded_at should be stable: request1=%s, request2=%s", loaded1, loaded2)
	}
}

func TestSpendContractGolden(t *testing.T) {
	// Golden test: validates the frozen /spend contract with full nested-structure assertions.
	// Fails if any field is missing or renamed at any level.
	meter := NewMeter()
	table := make(PriceTable)

	table["model-a"] = &Rates{
		Input:      1.0,
		Output:     2.0,
		CacheWrite: 0.5,
		CacheRead:  0.25,
	}
	table["model-b"] = &Rates{
		Input:      0.5,
		Output:     1.0,
		CacheWrite: 0.25,
		CacheRead:  0.125,
	}

	handler := spendHandler(meter, table, "prices.toml", "sha256hash", time.Now())

	meter.Record(Tags{Prefix: "TEST", Run: "run1", Ticket: "PROJ-1"}, "model-a", string(Big), Tokens{InputTokens: 1000000, OutputTokens: 500000, CacheCreationInputTokens: 100000, CacheReadInputTokens: 50000}, 1.775, true)
	meter.Record(Tags{Prefix: "TEST", Run: "run1", Ticket: "PROJ-1"}, "model-b", string(Medium), Tokens{InputTokens: 500000, OutputTokens: 250000, CacheCreationInputTokens: 50000, CacheReadInputTokens: 25000}, 0.75, true)
	meter.Record(Tags{Prefix: "TEST", Run: "run1", Ticket: "PROJ-2"}, "model-a", string(Small), Tokens{InputTokens: 200000, OutputTokens: 100000, CacheCreationInputTokens: 20000, CacheReadInputTokens: 10000}, 0.33, true)
	meter.Record(Tags{Prefix: "TEST", Run: "run1"}, "unknown-model", string(Medium), Tokens{InputTokens: 100000, OutputTokens: 50000, CacheCreationInputTokens: 10000, CacheReadInputTokens: 5000}, 0.0, false)

	req := httptest.NewRequest("GET", "/spend?prefix=TEST&run=run1", nil)
	w := httptest.NewRecorder()
	handler(w, req)

	var response map[string]interface{}
	if err := json.Unmarshal(w.Body.Bytes(), &response); err != nil {
		t.Fatalf("failed to unmarshal response: %v", err)
	}

	requiredTopLevel := []string{"prefix", "run", "router_started_at", "requests", "total_usd", "by_tier", "by_ticket", "by_model", "unpriced", "prices"}
	for _, key := range requiredTopLevel {
		if _, ok := response[key]; !ok {
			t.Errorf("missing top-level key: %s", key)
		}
	}

	byTier, ok := response["by_tier"].(map[string]interface{})
	if !ok {
		t.Fatal("by_tier is not an object")
	}
	for tierName, tierVal := range byTier {
		tier, ok := tierVal.(map[string]interface{})
		if !ok {
			t.Fatalf("by_tier[%s] is not an object", tierName)
		}
		if _, ok := tier["requests"]; !ok {
			t.Errorf("by_tier[%s] missing 'requests'", tierName)
		}
		if _, ok := tier["usd"]; !ok {
			t.Errorf("by_tier[%s] missing 'usd'", tierName)
		}
		tokensObj, ok := tier["tokens"].(map[string]interface{})
		if !ok {
			t.Fatalf("by_tier[%s].tokens is not an object", tierName)
		}
		tokenKeys := []string{"input_tokens", "output_tokens", "cache_creation_input_tokens", "cache_read_input_tokens"}
		for _, key := range tokenKeys {
			if _, ok := tokensObj[key]; !ok {
				t.Errorf("by_tier[%s].tokens missing '%s'", tierName, key)
			}
		}
	}

	byTicket, ok := response["by_ticket"].(map[string]interface{})
	if !ok {
		t.Fatal("by_ticket is not an object")
	}
	for ticketName, ticketVal := range byTicket {
		ticket, ok := ticketVal.(map[string]interface{})
		if !ok {
			t.Fatalf("by_ticket[%s] is not an object", ticketName)
		}
		if _, ok := ticket["requests"]; !ok {
			t.Errorf("by_ticket[%s] missing 'requests'", ticketName)
		}
		if _, ok := ticket["usd"]; !ok {
			t.Errorf("by_ticket[%s] missing 'usd'", ticketName)
		}
		tokensObj, ok := ticket["tokens"].(map[string]interface{})
		if !ok {
			t.Fatalf("by_ticket[%s].tokens is not an object", ticketName)
		}
		tokenKeys := []string{"input_tokens", "output_tokens", "cache_creation_input_tokens", "cache_read_input_tokens"}
		for _, key := range tokenKeys {
			if _, ok := tokensObj[key]; !ok {
				t.Errorf("by_ticket[%s].tokens missing '%s'", ticketName, key)
			}
		}
	}

	byModel, ok := response["by_model"].([]interface{})
	if !ok {
		t.Fatal("by_model is not an array")
	}
	if len(byModel) < 2 {
		t.Fatalf("expected at least 2 models, got %d", len(byModel))
	}
	for i, modelVal := range byModel {
		model, ok := modelVal.(map[string]interface{})
		if !ok {
			t.Fatalf("by_model[%d] is not an object", i)
		}
		requiredModelFields := []string{"model", "tier", "tokens", "rates_per_mtok", "usd"}
		for _, field := range requiredModelFields {
			if _, ok := model[field]; !ok {
				t.Errorf("by_model[%d] missing '%s'", i, field)
			}
		}
		tokensObj, ok := model["tokens"].(map[string]interface{})
		if !ok {
			t.Fatalf("by_model[%d].tokens is not an object", i)
		}
		tokenKeys := []string{"input_tokens", "output_tokens", "cache_creation_input_tokens", "cache_read_input_tokens"}
		for _, key := range tokenKeys {
			if _, ok := tokensObj[key]; !ok {
				t.Errorf("by_model[%d].tokens missing '%s'", i, key)
			}
		}
		// rates_per_mtok is an object but may be empty for unpriced models
		ratesObj, ok := model["rates_per_mtok"].(map[string]interface{})
		if !ok {
			t.Fatalf("by_model[%d].rates_per_mtok is not an object", i)
		}
		// For priced models (in the price table), check all rate keys exist
		modelName, _ := model["model"].(string)
		if modelName != "unknown-model" {
			rateKeys := []string{"input", "output", "cache_write", "cache_read"}
			for _, key := range rateKeys {
				if _, ok := ratesObj[key]; !ok {
					t.Errorf("by_model[%d].rates_per_mtok missing '%s'", i, key)
				}
			}
		}
	}

	unpriced, ok := response["unpriced"].(map[string]interface{})
	if !ok {
		t.Fatal("unpriced is not an object")
	}
	if _, ok := unpriced["requests"]; !ok {
		t.Error("unpriced missing 'requests'")
	}
	tokensObj, ok := unpriced["tokens"].(map[string]interface{})
	if !ok {
		t.Fatal("unpriced.tokens is not an object")
	}
	tokenKeys := []string{"input_tokens", "output_tokens", "cache_creation_input_tokens", "cache_read_input_tokens"}
	for _, key := range tokenKeys {
		if _, ok := tokensObj[key]; !ok {
			t.Errorf("unpriced.tokens missing '%s'", key)
		}
	}
	modelsObj, ok := unpriced["models"].(map[string]interface{})
	if !ok {
		t.Fatal("unpriced.models is not an object")
	}
	if len(modelsObj) == 0 {
		t.Error("unpriced.models should contain at least one model")
	}

	jsonStr, _ := json.Marshal(response)
	if strings.Contains(string(jsonStr), "unmetered") {
		t.Error("response contains forbidden 'unmetered' key")
	}
}

func TestByModelDeterministicOrder(t *testing.T) {
	// Ensures by_model array order is deterministic (sorted by model, then tier).
	// Removing the sort makes this test flaky/fail.
	meter := NewMeter()
	table := make(PriceTable)

	table["zebra-model"] = &Rates{Input: 1.0, Output: 2.0, CacheWrite: 0.5, CacheRead: 0.25}
	table["alpha-model"] = &Rates{Input: 0.5, Output: 1.0, CacheWrite: 0.25, CacheRead: 0.125}

	handler := spendHandler(meter, table, "prices.toml", "sha256hash", time.Now())

	meter.Record(Tags{Prefix: "TEST", Run: "run1"}, "zebra-model", string(Big), Tokens{InputTokens: 1000000}, 0.0, true)
	meter.Record(Tags{Prefix: "TEST", Run: "run1"}, "alpha-model", string(Big), Tokens{InputTokens: 500000}, 0.0, true)
	meter.Record(Tags{Prefix: "TEST", Run: "run1"}, "zebra-model", string(Small), Tokens{InputTokens: 200000}, 0.0, true)

	var order1 []string
	var order2 []string

	for call := 0; call < 2; call++ {
		req := httptest.NewRequest("GET", "/spend?prefix=TEST&run=run1", nil)
		w := httptest.NewRecorder()
		handler(w, req)

		var response map[string]interface{}
		json.Unmarshal(w.Body.Bytes(), &response)

		byModel, ok := response["by_model"].([]interface{})
		if !ok {
			t.Fatal("by_model is not an array")
		}

		var order []string
		for _, modelVal := range byModel {
			model := modelVal.(map[string]interface{})
			modelName := model["model"].(string)
			tier := model["tier"].(string)
			order = append(order, modelName+":"+tier)
		}

		if call == 0 {
			order1 = order
		} else {
			order2 = order
		}
	}

	if len(order1) != len(order2) {
		t.Errorf("by_model array length differs: %d vs %d", len(order1), len(order2))
	}
	for i := range order1 {
		if order1[i] != order2[i] {
			t.Errorf("by_model order differs at index %d: %s vs %s", i, order1[i], order2[i])
		}
	}

	expectedOrder := []string{"alpha-model:big", "zebra-model:big", "zebra-model:small"}
	if len(order1) != len(expectedOrder) {
		t.Errorf("expected %d models, got %d", len(expectedOrder), len(order1))
	}
	for i, expected := range expectedOrder {
		if i < len(order1) && order1[i] != expected {
			t.Errorf("order[%d]: expected %s, got %s", i, expected, order1[i])
		}
	}
}
