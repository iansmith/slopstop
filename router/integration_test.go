package main

import (
	"bufio"
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"log"
	"math"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"
)

// testPricesTable creates a temporary TOML file with test rate data.
// The TOML is written as an inline string to t.TempDir() and returns the path.
func testPricesTable(t *testing.T) string {
	tomlContent := `# Test pricing table with actual model names

	["claude-opus-4-8"]
	tier = "medium"
	input = 3.00
	output = 15.00
	cache_write = 22.50
	cache_read = 3.00

	["claude-sonnet-4"]
	tier = "medium"
	input = 1.00
	output = 5.00
	cache_write = 7.50
	cache_read = 1.00

["small"]
tier = "small"
input = 0.15
output = 0.60
cache_write = 1.50
cache_read = 0.30

["medium"]
tier = "medium"
input = 1.00
output = 5.00
cache_write = 7.50
cache_read = 1.00

["large"]
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

// TestMeteredNonStreamingEndToEnd verifies that a non-streaming POST request
// is metered correctly and appears in /spend response with the right model,
// tags, and cost.
func TestMeteredNonStreamingEndToEnd(t *testing.T) {
	// Load test fixtures
	reqBody, err := os.ReadFile(filepath.Join("testdata", "request_messages.json"))
	if err != nil {
		t.Fatalf("Failed to load request fixture: %v", err)
	}
	respBody, err := os.ReadFile(filepath.Join("testdata", "response_nonstreaming.json"))
	if err != nil {
		t.Fatalf("Failed to load response fixture: %v", err)
	}

	// Create fake upstream that echoes back the response
	upstream := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		// Verify path is stripped of /r/<run-id> prefix
		if r.URL.Path != "/v1/messages" {
			t.Errorf("Upstream path: got %q, want /v1/messages", r.URL.Path)
		}
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusOK)
		w.Write(respBody)
	}))
	defer upstream.Close()

	// Create meter and load prices
	meter := NewMeter()
	pricesPath := testPricesTable(t)
	prices, priceSHA, priceTime, err := LoadPrices(pricesPath)
	if err != nil {
		t.Fatalf("Failed to load prices: %v", err)
	}

	// Create a server with /spend and metered proxy
	baseProxy := createReverseProxy(parseURL(upstream.URL))
	meteredProxy := meterHandler(meter, prices, baseProxy)
	mux := http.NewServeMux()
	mux.HandleFunc("/spend", spendHandler(meter, prices, pricesPath, priceSHA, priceTime))
	mux.Handle("/", meteredProxy)

	server := httptest.NewServer(mux)
	defer server.Close()

	// Make a metered request with tags
	req, _ := http.NewRequest("POST", server.URL+"/v1/messages", bytes.NewReader(reqBody))
	req.Header.Set("X-Slopstop-Run", "run-test-001")
	req.Header.Set("X-Slopstop-Ticket", "BILL-208")
	req.Header.Set("Content-Type", "application/json")

	client := &http.Client{}
	resp, err := client.Do(req)
	if err != nil {
		t.Fatalf("Request failed: %v", err)
	}
	defer resp.Body.Close()

	// Verify response is forwarded
	if resp.StatusCode != http.StatusOK {
		t.Errorf("Status: got %d, want 200", resp.StatusCode)
	}

	body, _ := io.ReadAll(resp.Body)
	if !bytes.Equal(body, respBody) {
		t.Errorf("Response body mismatch")
	}

	// Check /spend endpoint
	spendResp, err := http.Get(server.URL + "/spend?prefix=BILL")
	if err != nil {
		t.Fatalf("Failed to get /spend: %v", err)
	}
	defer spendResp.Body.Close()

	var spend SpendResponse
	json.NewDecoder(spendResp.Body).Decode(&spend)

	if spend.Requests != 1 {
		t.Errorf("Spend requests: got %d, want 1", spend.Requests)
	}

	// Verify correct model, tags, and cost
	// Expected cost from fixture: claude-opus-4-8 with tokens [100, 120, 50, 10]
	// Rates: input=3.00, output=15.00, cache_write=22.50, cache_read=3.00 per million
	// Cost = (100/1e6)*3.00 + (120/1e6)*15.00 + (50/1e6)*22.50 + (10/1e6)*3.00
	expectedUSD := (100.0/1e6)*3.00 + (120.0/1e6)*15.00 + (50.0/1e6)*22.50 + (10.0/1e6)*3.00
	const epsilon = 1e-9
	if math.Abs(spend.TotalUSD-expectedUSD) > epsilon {
		t.Errorf("total_usd: got %f, want %f", spend.TotalUSD, expectedUSD)
	}

	// Verify by_model entry details
	if len(spend.ByModel) != 1 {
		t.Errorf("ByModel entries: got %d, want 1", len(spend.ByModel))
	} else {
		model := spend.ByModel[0]
		if model.Model != "claude-opus-4-8" {
			t.Errorf("Model: got %q, want claude-opus-4-8", model.Model)
		}
		if model.Tier != "medium" {
			t.Errorf("Tier: got %q, want medium", model.Tier)
		}
		if math.Abs(model.USD-expectedUSD) > epsilon {
			t.Errorf("Model USD: got %f, want %f", model.USD, expectedUSD)
		}
	}
}

// TestMeteredStreamingEqualsNonStreaming verifies that streaming and non-streaming
// requests for the same model produce identical spend.
func TestMeteredStreamingEqualsNonStreaming(t *testing.T) {
	reqBody, err := os.ReadFile(filepath.Join("testdata", "request_messages.json"))
	if err != nil {
		t.Fatalf("Failed to load request fixture: %v", err)
	}
	respBody, err := os.ReadFile(filepath.Join("testdata", "response_nonstreaming.json"))
	if err != nil {
		t.Fatalf("Failed to load response fixture: %v", err)
	}
	respSSE, err := os.ReadFile(filepath.Join("testdata", "response_stream.sse"))
	if err != nil {
		t.Fatalf("Failed to load SSE fixture: %v", err)
	}

	// Create two fake upstreams: one for non-streaming, one for streaming
	upstreamNonStream := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusOK)
		w.Write(respBody)
	}))
	defer upstreamNonStream.Close()

	upstreamStream := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "text/event-stream")
		w.WriteHeader(http.StatusOK)
		w.Write(respSSE)
	}))
	defer upstreamStream.Close()

	// Create meter and prices
	meter := NewMeter()
	pricesPath := testPricesTable(t)
	prices, priceSHA, priceTime, err := LoadPrices(pricesPath)
	if err != nil {
		t.Fatalf("Failed to load prices: %v", err)
	}

	// Create server with both proxies and /spend
	baseProxyNonStream := http.StripPrefix("/non-stream", createReverseProxy(parseURL(upstreamNonStream.URL)))
	baseProxyStream := http.StripPrefix("/stream", createReverseProxy(parseURL(upstreamStream.URL)))
	mux := http.NewServeMux()
	mux.HandleFunc("/spend", spendHandler(meter, prices, pricesPath, priceSHA, priceTime))
	mux.Handle("/non-stream/", meterHandler(meter, prices, baseProxyNonStream))
	mux.Handle("/stream/", meterHandler(meter, prices, baseProxyStream))

	server := httptest.NewServer(mux)
	defer server.Close()

	// Send non-streaming request
	req1, _ := http.NewRequest("POST", server.URL+"/non-stream/v1/messages", bytes.NewReader(reqBody))
	req1.Header.Set("X-Slopstop-Run", "run-test-002")
	req1.Header.Set("X-Slopstop-Ticket", "BILL-208")
	client := &http.Client{}
	resp1, _ := client.Do(req1)
	resp1.Body.Close()

	spend1, _ := http.Get(server.URL + "/spend?prefix=BILL&run=run-test-002")
	var s1 SpendResponse
	json.NewDecoder(spend1.Body).Decode(&s1)
	spend1.Body.Close()

	// Send streaming request
	req2, _ := http.NewRequest("POST", server.URL+"/stream/v1/messages", bytes.NewReader(reqBody))
	req2.Header.Set("X-Slopstop-Run", "run-test-003")
	req2.Header.Set("X-Slopstop-Ticket", "BILL-208")
	resp2, _ := client.Do(req2)
	resp2.Body.Close()

	spend2, _ := http.Get(server.URL + "/spend?prefix=BILL&run=run-test-003")
	var s2 SpendResponse
	json.NewDecoder(spend2.Body).Decode(&s2)
	spend2.Body.Close()

	// Verify identical cost
	if s1.TotalUSD != s2.TotalUSD {
		t.Errorf("Streaming vs non-streaming cost mismatch: got %f vs %f", s2.TotalUSD, s1.TotalUSD)
	}

	// Verify both equal hand-computed value (same fixture as non-streaming test)
	expectedUSD := (100.0/1e6)*3.00 + (120.0/1e6)*15.00 + (50.0/1e6)*22.50 + (10.0/1e6)*3.00
	const epsilon = 1e-9
	if math.Abs(s1.TotalUSD-expectedUSD) > epsilon {
		t.Errorf("Non-streaming total_usd: got %f, want %f", s1.TotalUSD, expectedUSD)
	}
	if math.Abs(s2.TotalUSD-expectedUSD) > epsilon {
		t.Errorf("Streaming total_usd: got %f, want %f", s2.TotalUSD, expectedUSD)
	}
}

// TestStreamingStillIncremental verifies that the client receives SSE events
// incrementally even with metering tee-ing the stream.
func TestStreamingStillIncremental(t *testing.T) {
	readyChan := make(chan struct{})
	blockChan := make(chan struct{})

	upstream := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "text/event-stream")
		w.WriteHeader(http.StatusOK)

		flusher, ok := w.(http.Flusher)
		if !ok {
			return
		}

		fmt.Fprintf(w, "data: event-1\n\n")
		flusher.Flush()
		close(readyChan)

		<-blockChan

		fmt.Fprintf(w, "data: event-2\n\n")
		flusher.Flush()
	}))
	defer upstream.Close()

	meter := NewMeter()
	pricesPath := testPricesTable(t)
	prices, priceSHA, priceTime, _ := LoadPrices(pricesPath)

	baseProxy := createReverseProxy(parseURL(upstream.URL))
	meteredProxy := meterHandler(meter, prices, baseProxy)
	mux := http.NewServeMux()
	mux.HandleFunc("/spend", spendHandler(meter, prices, pricesPath, priceSHA, priceTime))
	mux.Handle("/", meteredProxy)

	server := httptest.NewServer(mux)
	defer server.Close()

	req, _ := http.NewRequest("GET", server.URL+"/stream", nil)
	client := &http.Client{}
	resp, err := client.Do(req)
	if err != nil {
		t.Fatalf("Request failed: %v", err)
	}
	defer resp.Body.Close()

	reader := bufio.NewReader(resp.Body)
	eventChan := make(chan string, 1)

	go func() {
		for {
			line, _ := reader.ReadString('\n')
			if strings.HasPrefix(strings.TrimSpace(line), "data:") {
				eventChan <- line
				break
			}
		}
	}()

	select {
	case <-readyChan:
	case <-time.After(2 * time.Second):
		t.Fatal("Upstream never wrote first event")
	}

	select {
	case event := <-eventChan:
		if !strings.Contains(event, "event-1") {
			t.Errorf("Expected event-1, got %q", event)
		}
	case <-time.After(2 * time.Second):
		t.Fatal("Client did not receive event-1 incrementally")
	}

	close(blockChan)

	event2Chan := make(chan string, 1)
	go func() {
		for {
			line, _ := reader.ReadString('\n')
			if strings.HasPrefix(strings.TrimSpace(line), "data:") {
				event2Chan <- line
				break
			}
		}
	}()

	select {
	case event := <-event2Chan:
		if !strings.Contains(event, "event-2") {
			t.Errorf("Expected event-2, got %q", event)
		}
	case <-time.After(2 * time.Second):
		t.Fatal("Client did not receive event-2")
	}
}

// TestRunIdFromPathStrippedAndMetered verifies that /r/<run-id> paths are
// stripped before reaching upstream but metering is recorded under that run-id.
func TestRunIdFromPathStrippedAndMetered(t *testing.T) {
	reqBody, _ := os.ReadFile(filepath.Join("testdata", "request_messages.json"))
	respBody, _ := os.ReadFile(filepath.Join("testdata", "response_nonstreaming.json"))

	pathCapture := ""
	upstream := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		pathCapture = r.URL.Path
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusOK)
		w.Write(respBody)
	}))
	defer upstream.Close()

	meter := NewMeter()
	pricesPath := testPricesTable(t)
	prices, priceSHA, priceTime, _ := LoadPrices(pricesPath)

	baseProxy := createReverseProxy(parseURL(upstream.URL))
	meteredProxy := meterHandler(meter, prices, baseProxy)
	mux := http.NewServeMux()
	mux.HandleFunc("/spend", spendHandler(meter, prices, pricesPath, priceSHA, priceTime))
	mux.Handle("/", meteredProxy)

	server := httptest.NewServer(mux)
	defer server.Close()

	// Send request to /r/run-xyz/v1/messages
	req, _ := http.NewRequest("POST", server.URL+"/r/run-xyz/v1/messages", bytes.NewReader(reqBody))
	req.Header.Set("Content-Type", "application/json")

	client := &http.Client{}
	resp, _ := client.Do(req)
	resp.Body.Close()

	// Verify upstream received stripped path
	if pathCapture != "/v1/messages" {
		t.Errorf("Upstream path: got %q, want /v1/messages", pathCapture)
	}

	// Verify /spend shows the run-id from path (prefix is "untagged" since no X-Slopstop-Ticket was set)
	spendResp, _ := http.Get(server.URL + "/spend?prefix=untagged&run=run-xyz")
	var spend SpendResponse
	json.NewDecoder(spendResp.Body).Decode(&spend)
	spendResp.Body.Close()

	if spend.Requests != 1 {
		t.Errorf("Expected 1 request metered for run-xyz, got %d", spend.Requests)
	}
}

// TestMeteringPanicDoesNotBreakProxy verifies that if metering panics,
// the proxied response still reaches the client intact and unpriced.requests is incremented.
func TestMeteringPanicDoesNotBreakProxy(t *testing.T) {
	reqBody, _ := os.ReadFile(filepath.Join("testdata", "request_messages.json"))
	respBody, _ := os.ReadFile(filepath.Join("testdata", "response_nonstreaming.json"))

	upstream := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusOK)
		w.Write(respBody)
	}))
	defer upstream.Close()

	meter := NewMeter()
	pricesPath := testPricesTable(t)
	prices, priceSHA, priceTime, _ := LoadPrices(pricesPath)

	// Create a server with metering handler
	baseProxy := createReverseProxy(parseURL(upstream.URL))
	meteredProxy := meterHandler(meter, prices, baseProxy)
	mux := http.NewServeMux()
	mux.HandleFunc("/spend", spendHandler(meter, prices, pricesPath, priceSHA, priceTime))
	mux.Handle("/", meteredProxy)

	server := httptest.NewServer(mux)
	defer server.Close()

	// Inject panic via test hook
	oldHook := meterFaultHook
	meterFaultHook = func() { panic("injected metering fault") }
	defer func() { meterFaultHook = oldHook }()

	// Send request (panic will be caught and recovery recorded)
	req, _ := http.NewRequest("POST", server.URL+"/v1/messages", bytes.NewReader(reqBody))
	req.Header.Set("Content-Type", "application/json")

	client := &http.Client{}
	resp, err := client.Do(req)
	if err != nil {
		t.Fatalf("Request failed: %v", err)
	}
	defer resp.Body.Close()

	// Verify response reaches client intact (panic was recovered)
	if resp.StatusCode != http.StatusOK {
		t.Errorf("Response status: got %d, want 200", resp.StatusCode)
	}

	body, _ := io.ReadAll(resp.Body)
	if !bytes.Equal(body, respBody) {
		t.Errorf("Response body mismatch despite metering panic")
	}

	// Verify unpriced.requests is incremented (panic was recorded as unpriced)
	spendResp, _ := http.Get(server.URL + "/spend?prefix=untagged")
	var spend SpendResponse
	json.NewDecoder(spendResp.Body).Decode(&spend)
	spendResp.Body.Close()

	if spend.Unpriced.Requests != 1 {
		t.Errorf("Unpriced requests: got %d, want 1", spend.Unpriced.Requests)
	}
}

// TestNoSecretsOrBodiesInLogs verifies that request/response bodies
// and auth headers are not logged.
func TestNoSecretsOrBodiesInLogs(t *testing.T) {
	reqBody, _ := os.ReadFile(filepath.Join("testdata", "request_messages.json"))
	respBody, _ := os.ReadFile(filepath.Join("testdata", "response_nonstreaming.json"))

	upstream := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusOK)
		w.Write(respBody)
	}))
	defer upstream.Close()

	meter := NewMeter()
	pricesPath := testPricesTable(t)
	prices, priceSHA, priceTime, _ := LoadPrices(pricesPath)

	baseProxy := createReverseProxy(parseURL(upstream.URL))
	meteredProxy := meterHandler(meter, prices, baseProxy)
	mux := http.NewServeMux()
	mux.HandleFunc("/spend", spendHandler(meter, prices, pricesPath, priceSHA, priceTime))
	mux.Handle("/", meteredProxy)

	server := httptest.NewServer(mux)
	defer server.Close()

	// Capture log output
	logBuf := new(bytes.Buffer)
	oldOutput := log.Writer()
	log.SetOutput(logBuf)
	defer log.SetOutput(oldOutput)

	// Send request with secret auth header
	req, _ := http.NewRequest("POST", server.URL+"/v1/messages", bytes.NewReader(reqBody))
	req.Header.Set("Authorization", "Bearer secret-token-12345")
	req.Header.Set("Content-Type", "application/json")

	client := &http.Client{}
	resp, _ := client.Do(req)
	resp.Body.Close()

	// Verify logs don't contain auth header or body content
	logs := logBuf.String()

	if strings.Contains(logs, "secret-token-12345") {
		t.Error("Log contains auth header value")
	}

	if strings.Contains(logs, "test request") {
		t.Error("Log contains request body content")
	}

	if strings.Contains(logs, "test response") {
		t.Error("Log contains response body content")
	}
}

// TestUnknownModelUnpriced verifies that a request naming an unknown model
// (not in prices.toml) with parseable usage is recorded as unpriced, not priced.
func TestUnknownModelUnpriced(t *testing.T) {
	// Request body with an unknown model
	reqBody := []byte(`{"model": "unknown-model-xyz"}`)

	// Response with parseable usage
	respBody := []byte(`{
		"usage": {
			"input_tokens": 100,
			"output_tokens": 50,
			"cache_creation_input_tokens": 20,
			"cache_read_input_tokens": 5
		}
	}`)

	upstream := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusOK)
		w.Write(respBody)
	}))
	defer upstream.Close()

	meter := NewMeter()
	pricesPath := testPricesTable(t)
	prices, priceSHA, priceTime, _ := LoadPrices(pricesPath)

	baseProxy := createReverseProxy(parseURL(upstream.URL))
	meteredProxy := meterHandler(meter, prices, baseProxy)
	mux := http.NewServeMux()
	mux.HandleFunc("/spend", spendHandler(meter, prices, pricesPath, priceSHA, priceTime))
	mux.Handle("/", meteredProxy)

	server := httptest.NewServer(mux)
	defer server.Close()

	// Send request with unknown model
	req, _ := http.NewRequest("POST", server.URL+"/v1/messages", bytes.NewReader(reqBody))
	req.Header.Set("X-Slopstop-Run", "run-test-unknown")
	req.Header.Set("X-Slopstop-Ticket", "BILL-230")
	req.Header.Set("Content-Type", "application/json")

	client := &http.Client{}
	resp, _ := client.Do(req)
	resp.Body.Close()

	// Check /spend endpoint
	spendResp, _ := http.Get(server.URL + "/spend?prefix=BILL")
	var spend SpendResponse
	json.NewDecoder(spendResp.Body).Decode(&spend)
	spendResp.Body.Close()

	// Verify the request is in unpriced, not in any priced bucket
	if spend.Unpriced.Requests != 1 {
		t.Errorf("Unpriced requests: got %d, want 1", spend.Unpriced.Requests)
	}

	// Verify model is listed in unpriced models
	if !spend.Unpriced.Models["unknown-model-xyz"] {
		t.Errorf("Unknown model not found in unpriced.models")
	}
}

// TestTierDerivedFromTable verifies that tier is derived from prices.toml entry,
// not from a request header. A known model without X-Slopstop-Tier header
// should show its correct tier in /spend by_tier.
func TestTierDerivedFromTable(t *testing.T) {
	// Request with claude-haiku-4-5 (tier=small in the test prices)
	// Add claude-haiku-4-5 to test prices with tier=small
	tmpDir := t.TempDir()
	tomlPath := filepath.Join(tmpDir, "prices.toml")
	tomlContent := `["claude-haiku-4-5"]
tier = "small"
input = 0.15
output = 0.60
cache_write = 1.50
cache_read = 0.30
`
	if err := os.WriteFile(tomlPath, []byte(tomlContent), 0644); err != nil {
		t.Fatalf("failed to write test TOML: %v", err)
	}

	prices, priceSHA, priceTime, _ := LoadPrices(tomlPath)

	reqBody := []byte(`{"model": "claude-haiku-4-5"}`)
	respBody := []byte(`{
		"usage": {
			"input_tokens": 10,
			"output_tokens": 10,
			"cache_creation_input_tokens": 0,
			"cache_read_input_tokens": 0
		}
	}`)

	upstream := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusOK)
		w.Write(respBody)
	}))
	defer upstream.Close()

	meter := NewMeter()
	baseProxy := createReverseProxy(parseURL(upstream.URL))
	meteredProxy := meterHandler(meter, prices, baseProxy)
	mux := http.NewServeMux()
	mux.HandleFunc("/spend", spendHandler(meter, prices, tomlPath, priceSHA, priceTime))
	mux.Handle("/", meteredProxy)

	server := httptest.NewServer(mux)
	defer server.Close()

	// Send request WITHOUT X-Slopstop-Tier header
	// Tier should be derived from prices table (small)
	req, _ := http.NewRequest("POST", server.URL+"/v1/messages", bytes.NewReader(reqBody))
	req.Header.Set("X-Slopstop-Run", "run-test-tier")
	req.Header.Set("X-Slopstop-Ticket", "BILL-230")
	req.Header.Set("Content-Type", "application/json")

	client := &http.Client{}
	resp, _ := client.Do(req)
	resp.Body.Close()

	// Check /spend endpoint
	spendResp, _ := http.Get(server.URL + "/spend?prefix=BILL")
	var spend SpendResponse
	json.NewDecoder(spendResp.Body).Decode(&spend)
	spendResp.Body.Close()

	// Verify by_tier has "small" entry with at least 1 request
	if spend.ByTier == nil {
		t.Errorf("ByTier is nil")
	} else {
		smallTier, ok := spend.ByTier["small"]
		if !ok {
			t.Errorf("by_tier[\"small\"] not found")
		} else if smallTier.Requests < 1 {
			t.Errorf("by_tier[\"small\"].requests: got %d, want >= 1", smallTier.Requests)
		}
	}
}

// TestUnparseableResponseUnpriced verifies that an unparseable/garbage response
// increments unpriced.requests by 1 with zero tokens.
func TestUnparseableResponseUnpriced(t *testing.T) {
	reqBody := []byte(`{"model": "claude-opus-4-8"}`)
	respBody := []byte(`garbage response that's not JSON or SSE`)

	upstream := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusOK)
		w.Write(respBody)
	}))
	defer upstream.Close()

	meter := NewMeter()
	pricesPath := testPricesTable(t)
	prices, priceSHA, priceTime, _ := LoadPrices(pricesPath)

	baseProxy := createReverseProxy(parseURL(upstream.URL))
	meteredProxy := meterHandler(meter, prices, baseProxy)
	mux := http.NewServeMux()
	mux.HandleFunc("/spend", spendHandler(meter, prices, pricesPath, priceSHA, priceTime))
	mux.Handle("/", meteredProxy)

	server := httptest.NewServer(mux)
	defer server.Close()

	req, _ := http.NewRequest("POST", server.URL+"/v1/messages", bytes.NewReader(reqBody))
	req.Header.Set("X-Slopstop-Run", "run-test-unparseable")
	req.Header.Set("X-Slopstop-Ticket", "BILL-230")
	req.Header.Set("Content-Type", "application/json")

	client := &http.Client{}
	resp, _ := client.Do(req)
	resp.Body.Close()

	// Check /spend endpoint
	spendResp, _ := http.Get(server.URL + "/spend?prefix=BILL")
	var spend SpendResponse
	json.NewDecoder(spendResp.Body).Decode(&spend)
	spendResp.Body.Close()

	// Verify unpriced.requests incremented by 1
	if spend.Unpriced.Requests != 1 {
		t.Errorf("Unpriced requests: got %d, want 1", spend.Unpriced.Requests)
	}

	// Verify zero tokens
	totalTokens := spend.Unpriced.Tokens.InputTokens +
		spend.Unpriced.Tokens.OutputTokens +
		spend.Unpriced.Tokens.CacheCreationInputTokens +
		spend.Unpriced.Tokens.CacheReadInputTokens
	if totalTokens != 0 {
		t.Errorf("Unpriced total tokens: got %d, want 0", totalTokens)
	}
}
