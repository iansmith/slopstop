package main

import (
	"flag"
	"log"
	"net/http"
	"net/url"
	"os"
	"os/signal"
	"strconv"
	"syscall"
)

// listenAddr constructs the loopback listen address.
func listenAddr(port int) string {
	return "127.0.0.1:" + strconv.Itoa(port)
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
	proxy := createReverseProxy(upstreamURL)

	// Create HTTP handler mux for /spend and proxy
	mux := http.NewServeMux()
	mux.HandleFunc("/spend", spendHandler(meter, prices, *pricesDir, priceSHA, priceTime))
	mux.Handle("/", proxy)

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
