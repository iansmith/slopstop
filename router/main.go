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

// meterFaultHook is a test-only injection point for fault injection. It fires after
// the response is forwarded, so a panic it raises exercises the recover's
// unpriced-recording path without ever affecting the client (charter rule 4).
// Nil in production.
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
		// Charter rule 4: the meter never breaks the proxy. The forward is the
		// unconditional trunk; all metering reads its inputs from the saved request
		// body and the captured response *after* the forward, so a panic anywhere in
		// the metering work is recovered and recorded as unpriced — the client's
		// response has already flowed by then.
		defer func() {
			if err := recover(); err != nil {
				meter.Record(Tags{Run: "untagged", Ticket: "untagged", Prefix: "untagged"}, "", "untagged", Tokens{}, 0, false)
			}
		}()

		// Read the request body once: the proxy re-sends it and metering reads the
		// model from it. On a read error, forward what we have and record unpriced.
		var reqBody []byte
		if r.Body != nil {
			var err error
			reqBody, err = io.ReadAll(r.Body)
			if err != nil {
				r.Body = io.NopCloser(bytes.NewReader(reqBody))
				baseProxy.ServeHTTP(w, r)
				meter.Record(Tags{Run: "untagged", Ticket: "untagged", Prefix: "untagged"}, "", "untagged", Tokens{}, 0, false)
				return
			}
		}
		r.Body = io.NopCloser(bytes.NewReader(reqBody))

		// Forward first — the response always reaches the client. The response body
		// is captured for post-forward token extraction.
		wrapped := &responseWrapper{ResponseWriter: w}
		baseProxy.ServeHTTP(wrapped, r)

		// Test hook: inject a metering fault after the response is sent.
		if meterFaultHook != nil {
			meterFaultHook()
		}

		// Meter the delivered response. Everything below is a pure side-observer of
		// an already-sent response; a panic here hits the recover above → unpriced.
		model, _ := ModelFromRequest(reqBody)
		tags, _ := ParseTags(r) // path stripping is handled by the proxy's Rewrite
		tier := "untagged"
		if rt, ok := prices[model]; ok {
			tier = rt.Tier
		}

		respContentType := wrapped.Header().Get("Content-Type")
		respBody := wrapped.body.Bytes()
		var tokens Tokens
		if strings.Contains(respContentType, "text/event-stream") {
			tokens, _ = UsageFromSSE(respBody)
		} else if strings.Contains(respContentType, "application/json") {
			tokens, _ = UsageFromJSON(respBody)
		}

		cost, priceKnown := prices.Cost(model, tokens)
		meter.Record(tags, model, tier, tokens, cost, priceKnown)
	})
}

// responseWrapper captures the response body while forwarding it to the client.
type responseWrapper struct {
	http.ResponseWriter
	body bytes.Buffer
}

func (w *responseWrapper) Write(b []byte) (int, error) {
	// Capture body
	w.body.Write(b)
	// Forward to client
	return w.ResponseWriter.Write(b)
}

func (w *responseWrapper) WriteHeader(statusCode int) {
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
