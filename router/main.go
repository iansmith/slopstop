package main

import (
	"flag"
	"fmt"
	"log"
	"net/http"
	"net/http/httputil"
	"net/url"
	"os"
	"os/signal"
	"syscall"
)

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

	// Verify prices file exists (but don't fail if it doesn't - it might be created later)
	if _, err := os.Stat(*pricesDir); err != nil && !os.IsNotExist(err) {
		log.Fatalf("Error accessing prices file %q: %v", *pricesDir, err)
	}

	// Create the reverse proxy
	proxy := httputil.NewSingleHostReverseProxy(upstreamURL)

	// Set FlushInterval for SSE streaming (incremental delivery)
	proxy.FlushInterval = -1 // Immediate flush

	// Create HTTP server listening on loopback only
	addr := fmt.Sprintf("127.0.0.1:%d", *port)
	server := &http.Server{
		Addr:    addr,
		Handler: proxy,
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
