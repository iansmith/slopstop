package main

import (
	"net/http"
	"net/http/httputil"
	"net/url"
)

// createReverseProxy creates an HTTP handler that forwards all requests to the upstream URL.
// It preserves all request headers (including auth headers) and returns upstream responses
// unmodified. For streaming responses (SSE), it uses FlushInterval to ensure incremental delivery.
func createReverseProxy(upstreamURL string) http.Handler {
	upstream, err := url.Parse(upstreamURL)
	if err != nil {
		panic("Invalid upstream URL: " + err.Error())
	}

	proxy := httputil.NewSingleHostReverseProxy(upstream)

	// Set FlushInterval to -1 for immediate flushing (required for SSE streaming).
	// This ensures the client receives events as they are sent by the upstream,
	// rather than waiting for buffering.
	proxy.FlushInterval = -1

	// The default Director and response handlers already preserve all headers
	// and return upstream status/body unmodified, which satisfies the transparent
	// proxy requirements.

	return proxy
}
