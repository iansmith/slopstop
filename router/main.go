package main

import (
	"bytes"
	"flag"
	"io"
	"log"
	"net/http"
	"net/url"
	"os"
	"os/signal"
	"strconv"
	"strings"
	"syscall"
)

// meterFaultHook is a test-only injection point for fault injection.
// Nil in production; test code can set it to panic for recovery testing.
var meterFaultHook func()

// listenAddr constructs the loopback listen address.
func listenAddr(port int) string {
	return "127.0.0.1:" + strconv.Itoa(port)
}

// meterHandler wraps a proxy handler to meter requests and responses.
// It extracts model/tags from the request, forwards it with path rewriting,
// intercepts the response to extract tokens, and records a meter entry.
// If metering fails (panic or error), the response is still forwarded intact
// and recorded as unpriced.requests +1 with zero tokens.
func meterHandler(meter *Meter, prices PriceTable, baseProxy http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		// Defer recover to catch panics in metering logic
		defer func() {
			if err := recover(); err != nil {
				// Panic in metering — increment unpriced but let response through
				meter.Record(Tags{Run: "untagged", Ticket: "untagged", Prefix: "untagged"}, "", "untagged", Tokens{}, 0, false)
			}
		}()

		// Read request body to extract model (body will be consumed)
		var reqBody []byte
		if r.Body != nil {
			var err error
			reqBody, err = io.ReadAll(r.Body)
			if err != nil {
				// Error reading body — record as unpriced
				meter.Record(Tags{Run: "untagged", Ticket: "untagged", Prefix: "untagged"}, "", "untagged", Tokens{}, 0, false)
				// Restore body and forward
				r.Body = io.NopCloser(bytes.NewReader(reqBody))
				baseProxy.ServeHTTP(w, r)
				return
			}
		}

		// Extract model from request body
		model, _ := ModelFromRequest(reqBody)

		// Extract tags (path stripping is handled by proxy's Rewrite function)
		tags, _ := ParseTags(r)

		// Extract tier from header (defaults to empty string)
		tier := r.Header.Get("X-Slopstop-Tier")
		if tier == "" {
			tier = "untagged"
		}

		// Restore request body for proxy
		r.Body = io.NopCloser(bytes.NewReader(reqBody))

		// Intercept response to extract tokens and meter it
		var respBody []byte
		var respContentType string
		var tokens Tokens
		var known bool

		// Use a custom response writer to capture response
		wrapped := &responseWrapper{ResponseWriter: w}

		// Handle response streaming/buffering based on Content-Type
		baseProxy.ServeHTTP(wrapped, r)

		// Test hook: allow injection of metering faults (after response is sent)
		if meterFaultHook != nil {
			meterFaultHook()
		}

		// Extract tokens from captured response
		respContentType = wrapped.Header().Get("Content-Type")
		respBody = wrapped.body.Bytes()

		if strings.Contains(respContentType, "text/event-stream") {
			tokens, known = UsageFromSSE(respBody)
		} else if strings.Contains(respContentType, "application/json") {
			tokens, known = UsageFromJSON(respBody)
		}

		// Calculate cost
		cost, _ := prices.Cost(model, tokens)

		// Record meter entry
		meter.Record(tags, model, tier, tokens, cost, known)
	})
}

// responseWrapper captures the response body while forwarding it to the client.
type responseWrapper struct {
	http.ResponseWriter
	body   bytes.Buffer
	status int
	wrote  bool
}

func (w *responseWrapper) Write(b []byte) (int, error) {
	// Capture body
	w.body.Write(b)
	// Forward to client
	return w.ResponseWriter.Write(b)
}

func (w *responseWrapper) WriteHeader(statusCode int) {
	w.status = statusCode
	w.wrote = true
	w.ResponseWriter.WriteHeader(statusCode)
}

func (w *responseWrapper) Flush() {
	if f, ok := w.ResponseWriter.(http.Flusher); ok {
		f.Flush()
	}
}

func main() {
	var (
		port      = flag.Int("port", 8484, "port to listen on (default 8484)")
		upstream  = flag.String("upstream", "https://api.anthropic.com", "upstream URL to proxy to (default https://api.anthropic.com)")
		pricesDir = flag.String("prices", "prices.toml", "path to prices.toml file (default prices.toml)")
	)
	flag.Parse()

	// Parse upstream URL
	upstreamURL, err := url.Parse(*upstream)
	if err != nil {
		log.Fatalf("Invalid upstream URL %q: %v", *upstream, err)
	}

	// Load prices at startup
	prices, priceSHA, priceTime, err := LoadPrices(*pricesDir)
	if err != nil {
		log.Fatalf("Failed to load prices from %q: %v", *pricesDir, err)
	}

	// Create meter
	meter := NewMeter()

	// Create the reverse proxy
	baseProxy := createReverseProxy(upstreamURL)

	// Wrap proxy with metering handler
	meteredProxy := meterHandler(meter, prices, baseProxy)

	// Create HTTP handler mux for /spend and metered proxy
	mux := http.NewServeMux()
	mux.HandleFunc("/spend", spendHandler(meter, prices, *pricesDir, priceSHA, priceTime))
	mux.Handle("/", meteredProxy)

	// Create HTTP server listening on loopback only
	addr := listenAddr(*port)
	server := &http.Server{
		Addr:    addr,
		Handler: mux,
	}

	// Handle graceful shutdown
	sigChan := make(chan os.Signal, 1)
	signal.Notify(sigChan, syscall.SIGINT, syscall.SIGTERM)

	go func() {
		sig := <-sigChan
		log.Printf("Received signal %v, shutting down", sig)
		server.Close()
	}()

	// Start server
	log.Printf("Router proxy listening on %s, forwarding to %s", addr, upstreamURL.String())
	if err := server.ListenAndServe(); err != nil && err != http.ErrServerClosed {
		log.Fatalf("Server error: %v", err)
	}
}
