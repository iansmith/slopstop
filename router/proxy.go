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
//
// This is the OFF-PATH proxy (-route=false): it never touches auth headers. Its
// behavior is byte-for-byte today's single-upstream forwarding.
func createReverseProxy(upstreamURL *url.URL) http.Handler {
	proxy := &httputil.ReverseProxy{
		Rewrite: func(r *httputil.ProxyRequest) {
			rewriteToTarget(r, upstreamURL)
		},
		// Set FlushInterval to -1 for immediate flushing (required for SSE streaming).
		FlushInterval: -1,
	}

	return proxy
}

// createRoutedProxy builds a per-target reverse proxy for the routed path
// (-route=true). It forwards to the given effective target and applies the
// provider's auth mode: "none" strips BOTH Authorization and X-Api-Key so an
// Anthropic credential is never leaked to a non-passthrough endpoint;
// "passthrough" (and any other value) forwards the client's headers unchanged.
// Path stripping, host retargeting, XFF preservation, and SSE flushing are
// identical to createReverseProxy — only the target and the auth handling differ.
func createRoutedProxy(target *url.URL, authMode string) http.Handler {
	proxy := &httputil.ReverseProxy{
		Rewrite: func(r *httputil.ProxyRequest) {
			rewriteToTarget(r, target)
			if authMode == "none" {
				// Strip before forwarding. Header.Del is canonical-case, so it
				// removes any incoming casing (x-api-key, X-Api-Key, …).
				r.Out.Header.Del("Authorization")
				r.Out.Header.Del("X-Api-Key")
			}
		},
		FlushInterval: -1,
	}

	return proxy
}

// rewriteToTarget rewrites an outbound proxy request onto target: it strips the
// /r/<run-id> path prefix, points scheme/host at target, retargets the Host
// header, and preserves an incoming X-Forwarded-For verbatim. It does NOT touch
// auth headers — auth handling is layered on top by the caller.
func rewriteToTarget(r *httputil.ProxyRequest, target *url.URL) {
	// Strip /r/<run-id> path prefix if present
	incomingPath := r.In.URL.Path
	_, strippedPath := extractRunFromPath(incomingPath)

	// Build the target URL with stripped path
	r.Out.URL = &url.URL{
		Scheme:   target.Scheme,
		User:     target.User,
		Host:     target.Host,
		Path:     strippedPath,
		RawPath:  "", // Let it be computed from Path
		RawQuery: r.In.URL.RawQuery,
		Fragment: r.In.URL.Fragment,
	}

	// Retarget Host header to target host (transparent proxy requirement).
	r.Out.Host = target.Host
	// Preserve X-Forwarded-For header from incoming request verbatim (transparent proxy requirement).
	if xff := r.In.Header.Get("X-Forwarded-For"); xff != "" {
		r.Out.Header.Set("X-Forwarded-For", xff)
	}
}
