package main

import (
	"net/http"
	"regexp"
	"strings"
)

// Tags holds the run ID, ticket ID, and prefix extracted from a request.
type Tags struct {
	Run    string
	Ticket string
	Prefix string
}

// ParseTags extracts run ID, ticket, and prefix from an HTTP request.
// It returns the Tags struct and the rewritten upstream path with any /r/<run-id>
// prefix stripped.
//
// Run-id resolution (in order):
// 1. X-Slopstop-Run header value
// 2. /r/<run-id> path prefix (always stripped from returned path)
// 3. "untagged" if neither is present
//
// Ticket resolution:
// Matches regex ^[A-Za-z][A-Za-z0-9]*-\d+$
// "untagged" if absent or malformed
//
// Prefix is the first capture group of the ticket regex.
//
// Important: The /r/<run-id> prefix is ALWAYS stripped from the path,
// regardless of which source wins the run-id. When both header and path
// prefix are present, the run-id comes from the header but the path is
// still stripped.
func ParseTags(r *http.Request) (Tags, string) {
	tags := Tags{
		Run:    "untagged",
		Ticket: "untagged",
		Prefix: "untagged",
	}

	path := r.URL.Path

	// Extract run ID from header (takes precedence over path prefix)
	if headerRun := r.Header.Get("X-Slopstop-Run"); headerRun != "" {
		tags.Run = headerRun
		// Even though header wins, we still strip /r/<run-id> from path if present
		_, path = extractRunFromPath(path)
	} else {
		// Try to extract run ID from path prefix /r/<run-id>
		tags.Run, path = extractRunFromPath(path)
	}

	// Extract ticket and prefix from header
	if headerTicket := r.Header.Get("X-Slopstop-Ticket"); headerTicket != "" {
		ticket, prefix := parseTicket(headerTicket)
		tags.Ticket = ticket
		tags.Prefix = prefix
	}

	return tags, path
}

// extractRunFromPath extracts a run ID from a /r/<run-id> path prefix.
// Returns the run ID and the rewritten path with the prefix stripped.
// Edge cases:
// - /r/abc → run "abc", path "/"
// - /r/ (empty id) → run "untagged", path unmodified (/r/)
// - /r/abc/v1/messages → run "abc", path "/v1/messages"
func extractRunFromPath(path string) (string, string) {
	if !strings.HasPrefix(path, "/r/") {
		return "untagged", path
	}

	// Remove /r/ prefix
	rest := path[3:]

	// If nothing follows /r/, it's /r/ (empty id)
	if rest == "" {
		return "untagged", path
	}

	// Find the next slash to extract the run ID
	nextSlash := strings.Index(rest, "/")
	if nextSlash == -1 {
		// Path is exactly /r/<id> (no trailing path)
		return rest, "/"
	}

	// Path is /r/<id>/<rest>
	runID := rest[:nextSlash]
	remainingPath := rest[nextSlash:]

	return runID, remainingPath
}

// parseTicket extracts the ticket ID and prefix from a ticket string.
// Ticket regex: ^[A-Za-z][A-Za-z0-9]*-\d+$
// Prefix is the first capture group: [A-Za-z][A-Za-z0-9]*
func parseTicket(ticketStr string) (ticket, prefix string) {
	ticketRegex := regexp.MustCompile(`^([A-Za-z][A-Za-z0-9]*)-(\d+)$`)
	matches := ticketRegex.FindStringSubmatch(ticketStr)
	if matches == nil {
		return "untagged", "untagged"
	}
	return ticketStr, matches[1]
}

// ResolveTags extends ParseTags with TagMap consultation.
// Attribution precedence: X-Slopstop-Ticket header → map entry → untagged
// If no X-Slopstop-Ticket header is present, consults the TagMap for the run ID.
func ResolveTags(r *http.Request, tm *TagMap) (Tags, string) {
	tags, path := ParseTags(r)

	if r.Header.Get("X-Slopstop-Ticket") != "" {
		return tags, path
	}

	if mappedTicket, ok := tm.Get(tags.Run); ok && mappedTicket != "" {
		ticket, prefix := parseTicket(mappedTicket)
		tags.Ticket = ticket
		tags.Prefix = prefix
	}

	return tags, path
}
