package main

import (
	"net/http"
	"net/http/httputil"
	"net/url"
)

// createReverseProxy creates an HTTP handler that forwards all requests to the upstream URL.
// It preserves all request headers (including auth headers) and returns upstream responses
// unmodified. For streaming responses (SSE), it uses FlushInterval to ensure incremental delivery.
func createReverseProxy(upstreamURL *url.URL) http.Handler {
	proxy := &httputil.ReverseProxy{
		Rewrite: func(r *httputil.ProxyRequest) {
			// Set the outbound request URL to the upstream URL with the inbound path/query.
			r.SetURL(upstreamURL)
			// Retarget Host header to upstream host (transparent proxy requirement).
			r.Out.Host = upstreamURL.Host
			// Preserve X-Forwarded-For header from incoming request verbatim (transparent proxy requirement).
			if xff := r.In.Header.Get("X-Forwarded-For"); xff != "" {
				r.Out.Header.Set("X-Forwarded-For", xff)
			}
		},
		// Set FlushInterval to -1 for immediate flushing (required for SSE streaming).
		FlushInterval: -1,
	}

	return proxy
}
