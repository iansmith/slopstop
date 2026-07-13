package main

import (
	"bytes"
	"io"
	"net/http"
	"net/url"
)

// routingProxy is the -route=true base proxy: it dispatches each request to the
// upstream determined by the request body's model, per the loaded manifest.
//
//   - A model present in the manifest forwards to that entry's EFFECTIVE url
//     (per-model url override else provider url) with the provider's auth mode
//     applied (passthrough vs. none).
//   - A model absent from the manifest (or an unreadable/model-less body) falls
//     back to -upstream with passthrough auth — the same single-upstream forward
//     the off-path does — and meters as unpriced downstream.
//
// It is a pure dispatcher: it forwards the request unchanged except for the
// per-target rewrite and auth handling done inside the chosen reverse proxy. It
// performs NO retry and NO failover — a transport failure at a routed target
// surfaces to the client as the reverse proxy's 502, exactly like today.
//
// Metering is unaffected: routingProxy is wrapped by meterHandler identically to
// the off-path, so the meter observes the delivered response the same way on
// both paths.
type routingProxy struct {
	routed   map[string]http.Handler // model → per-target proxy (built once at startup)
	fallback http.Handler            // createReverseProxy(-upstream): passthrough fallback
}

// newRoutingProxy builds the routing dispatcher over the loaded manifest, with
// upstreamURL as the fallback for unknown models. Per-target proxies are built
// eagerly here (the manifest is fixed at startup), so the resulting map is
// read-only and safe for concurrent request dispatch without locking. A model
// whose effective url is malformed is left out of the map, so it falls back to
// -upstream rather than dispatching to a bad target.
func newRoutingProxy(prices PriceTable, upstreamURL *url.URL) http.Handler {
	routed := make(map[string]http.Handler, len(prices))
	for model, rates := range prices {
		target, err := url.Parse(rates.EffectiveURL)
		if err != nil || target.Host == "" {
			continue
		}
		routed[model] = createRoutedProxy(target, rates.AuthMode)
	}
	return &routingProxy{
		routed:   routed,
		fallback: createReverseProxy(upstreamURL),
	}
}

func (p *routingProxy) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	// Read the body to determine the model, then restore it so the chosen proxy
	// can re-send it. meterHandler already reset r.Body to a NopCloser over the
	// buffered bytes before calling us, so this read is cheap and side-effect free.
	var body []byte
	if r.Body != nil {
		body, _ = io.ReadAll(r.Body)
	}
	r.Body = io.NopCloser(bytes.NewReader(body))

	if model, ok := ModelFromRequest(body); ok {
		if h, ok := p.routed[model]; ok {
			h.ServeHTTP(w, r)
			return
		}
	}

	// Unknown model (or unresolvable target) → fall back to -upstream.
	p.fallback.ServeHTTP(w, r)
}
