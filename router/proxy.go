package main

import (
	"net/http"
	"net/http/httputil"
	"net/url"
)

// createReverseProxy creates an HTTP handler that forwards all requests to the upstream URL.
// It preserves all request headers (including auth headers) and returns upstream responses
// unmodified. For streaming responses (SSE), it uses FlushInterval to ensure incremental delivery.
// It also strips /r/<run-id> path prefixes before forwarding to upstream.
func createReverseProxy(upstreamURL *url.URL) http.Handler {
	proxy := &httputil.ReverseProxy{
		Rewrite: func(r *httputil.ProxyRequest) {
			// Strip /r/<run-id> path prefix if present
			incomingPath := r.In.URL.Path
			_, strippedPath := extractRunFromPath(incomingPath)

			// Build the upstream URL with stripped path
			r.Out.URL = &url.URL{
				Scheme:   upstreamURL.Scheme,
				User:     upstreamURL.User,
				Host:     upstreamURL.Host,
				Path:     strippedPath,
				RawPath:  "", // Let it be computed from Path
				RawQuery: r.In.URL.RawQuery,
				Fragment: r.In.URL.Fragment,
			}

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
