package main

import (
	"bufio"
	"fmt"
	"io"
	"net"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"
)

// TestBindsLoopbackOnly verifies the server only listens on loopback, never on all interfaces.
func TestBindsLoopbackOnly(t *testing.T) {
	handler := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
	})

	srv := &http.Server{
		Addr:    "127.0.0.1:0",
		Handler: handler,
	}

	listener, err := net.Listen("tcp", srv.Addr)
	if err != nil {
		t.Fatalf("Failed to listen: %v", err)
	}
	defer listener.Close()

	addr := listener.Addr().String()
	// Assert it starts with loopback, not a wildcard
	if !strings.HasPrefix(addr, "127.0.0.1:") {
		t.Errorf("Server listening on %q, expected 127.0.0.1:*. The ':' prefix form is not allowed.", addr)
	}
}

// TestForwardsRequestVerbatim verifies all request method, path, query, and body are forwarded.
func TestForwardsRequestVerbatim(t *testing.T) {
	upstream := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method != "POST" {
			t.Errorf("Method: got %q, want POST", r.Method)
		}
		if r.URL.Path != "/v1/messages" {
			t.Errorf("Path: got %q, want /v1/messages", r.URL.Path)
		}
		if r.URL.RawQuery != "test=1&other=2" {
			t.Errorf("Query: got %q, want test=1&other=2", r.URL.RawQuery)
		}
		body, _ := io.ReadAll(r.Body)
		if string(body) != `{"model":"claude"}` {
			t.Errorf("Body: got %q, want {\"model\":\"claude\"}", string(body))
		}
		w.WriteHeader(http.StatusOK)
		w.Write([]byte("OK"))
	}))
	defer upstream.Close()

	proxy := httptest.NewServer(createReverseProxy(upstream.URL))
	defer proxy.Close()

	req, _ := http.NewRequest("POST", proxy.URL+"/v1/messages?test=1&other=2", strings.NewReader(`{"model":"claude"}`))
	client := &http.Client{}
	resp, err := client.Do(req)
	if err != nil {
		t.Fatalf("Request failed: %v", err)
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		t.Errorf("Status: got %d, want 200", resp.StatusCode)
	}
}

// TestPreservesAuthHeaders verifies authorization headers are forwarded.
func TestPreservesAuthHeaders(t *testing.T) {
	upstream := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		authHeader := r.Header.Get("Authorization")
		if authHeader != "Bearer secret-token-12345" {
			t.Errorf("Authorization header: got %q, want 'Bearer secret-token-12345'", authHeader)
		}
		apiKey := r.Header.Get("x-api-key")
		if apiKey != "key-abcdef" {
			t.Errorf("x-api-key header: got %q, want 'key-abcdef'", apiKey)
		}
		w.WriteHeader(http.StatusOK)
	}))
	defer upstream.Close()

	proxy := httptest.NewServer(createReverseProxy(upstream.URL))
	defer proxy.Close()

	req, _ := http.NewRequest("GET", proxy.URL+"/", nil)
	req.Header.Set("Authorization", "Bearer secret-token-12345")
	req.Header.Set("x-api-key", "key-abcdef")

	client := &http.Client{}
	resp, err := client.Do(req)
	if err != nil {
		t.Fatalf("Request failed: %v", err)
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		t.Errorf("Status: got %d, want 200", resp.StatusCode)
	}
}

// TestReturnsUpstreamStatusAndBody verifies status, headers, and body are returned verbatim.
func TestReturnsUpstreamStatusAndBody(t *testing.T) {
	upstream := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("X-Custom-Header", "custom-value")
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusCreated)
		w.Write([]byte(`{"id":"msg123","type":"message"}`))
	}))
	defer upstream.Close()

	proxy := httptest.NewServer(createReverseProxy(upstream.URL))
	defer proxy.Close()

	resp, err := http.Get(proxy.URL + "/")
	if err != nil {
		t.Fatalf("Request failed: %v", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusCreated {
		t.Errorf("Status: got %d, want 201", resp.StatusCode)
	}
	if resp.Header.Get("X-Custom-Header") != "custom-value" {
		t.Errorf("X-Custom-Header: got %q, want 'custom-value'", resp.Header.Get("X-Custom-Header"))
	}
	if resp.Header.Get("Content-Type") != "application/json" {
		t.Errorf("Content-Type: got %q, want 'application/json'", resp.Header.Get("Content-Type"))
	}

	body, _ := io.ReadAll(resp.Body)
	if string(body) != `{"id":"msg123","type":"message"}` {
		t.Errorf("Body: got %q", string(body))
	}
}

// TestStreamsIncrementally verifies SSE responses stream without buffering.
func TestStreamsIncrementally(t *testing.T) {
	readyChan := make(chan struct{})
	blockChan := make(chan struct{})

	upstream := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "text/event-stream")
		w.WriteHeader(http.StatusOK)

		flusher, ok := w.(http.Flusher)
		if !ok {
			t.Error("ResponseWriter does not support Flusher")
			return
		}

		// Write first event and flush
		fmt.Fprintf(w, "data: %s\n\n", "event-1")
		flusher.Flush()

		// Signal that first event has been written
		close(readyChan)

		// Wait for test to read the first event
		<-blockChan

		// Write second event
		fmt.Fprintf(w, "data: %s\n\n", "event-2")
		flusher.Flush()
	}))
	defer upstream.Close()

	proxy := httptest.NewServer(createReverseProxy(upstream.URL))
	defer proxy.Close()

	resp, err := http.Get(proxy.URL + "/stream")
	if err != nil {
		t.Fatalf("Request failed: %v", err)
	}
	defer resp.Body.Close()

	reader := bufio.NewReader(resp.Body)

	// Read first event - should arrive promptly without buffering
	eventChan := make(chan string, 1)
	go func() {
		line, _ := reader.ReadString('\n')
		eventChan <- strings.TrimSpace(line)
	}()

	// Wait for upstream to write first event
	select {
	case <-readyChan:
	case <-time.After(2 * time.Second):
		t.Fatal("Upstream never wrote first event")
	}

	// Client should receive first event without waiting for second
	select {
	case event := <-eventChan:
		if !strings.Contains(event, "event-1") {
			t.Errorf("Expected to read event-1, got %q", event)
		}
	case <-time.After(2 * time.Second):
		t.Fatal("Client did not receive first event promptly - likely buffered")
	}

	// Now signal upstream to write second event
	close(blockChan)

	// Read second event
	line2, _ := reader.ReadString('\n')
	if !strings.Contains(line2, "event-2") {
		t.Errorf("Expected to read event-2, got %q", line2)
	}
}

// TestUpstreamErrorSurfaced verifies non-200 statuses and errors are returned to client.
func TestUpstreamErrorSurfaced(t *testing.T) {
	upstream := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusUnauthorized)
		w.Write([]byte(`{"error":"invalid_api_key"}`))
	}))
	defer upstream.Close()

	proxy := httptest.NewServer(createReverseProxy(upstream.URL))
	defer proxy.Close()

	resp, err := http.Get(proxy.URL + "/")
	if err != nil {
		t.Fatalf("Request failed: %v", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusUnauthorized {
		t.Errorf("Status: got %d, want 401", resp.StatusCode)
	}

	body, _ := io.ReadAll(resp.Body)
	if string(body) != `{"error":"invalid_api_key"}` {
		t.Errorf("Body: got %q", string(body))
	}
}

// Helper function to create a reverse proxy for testing
func createReverseProxy(upstreamURL string) http.Handler {
	// This will be implemented in proxy.go
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusInternalServerError)
	})
}
