package main

import (
	"net/http"
	"net/http/httptest"
	"testing"
)

// tagsTestRequest creates a test request with optional headers and path.
func tagsTestRequest(method, path string, headers map[string]string) *http.Request {
	req := httptest.NewRequest(method, "http://localhost"+path, nil)
	for k, v := range headers {
		req.Header.Set(k, v)
	}
	return req
}

// TestPrefixGrammarAccepts verifies that BILL, SOP, Q24P, QTwoFourP are all valid prefixes.
func TestPrefixGrammarAccepts(t *testing.T) {
	tests := []struct {
		ticket string
		want   string
	}{
		{"BILL-203", "BILL"},
		{"SOP-1", "SOP"},
		{"Q24P-999", "Q24P"},
		{"QTwoFourP-12", "QTwoFourP"},
	}

	for _, tt := range tests {
		t.Run(tt.ticket, func(t *testing.T) {
			req := tagsTestRequest("GET", "/", map[string]string{
				"X-Slopstop-Ticket": tt.ticket,
			})
			tags, _ := ParseTags(req)
			if tags.Prefix != tt.want {
				t.Errorf("ParseTags(%q).Prefix = %q, want %q", tt.ticket, tags.Prefix, tt.want)
			}
			if tags.Ticket != tt.ticket {
				t.Errorf("ParseTags(%q).Ticket = %q, want %q", tt.ticket, tags.Ticket, tt.ticket)
			}
		})
	}
}

// TestPrefixCaseSensitive verifies that Bill-1 → prefix Bill and that Bill != BILL.
func TestPrefixCaseSensitive(t *testing.T) {
	tests := []struct {
		ticket string
		want   string
	}{
		{"Bill-1", "Bill"},
		{"BILL-1", "BILL"},
		{"bill-1", "bill"},
	}

	for _, tt := range tests {
		t.Run(tt.ticket, func(t *testing.T) {
			req := tagsTestRequest("GET", "/", map[string]string{
				"X-Slopstop-Ticket": tt.ticket,
			})
			tags, _ := ParseTags(req)
			if tags.Prefix != tt.want {
				t.Errorf("ParseTags(%q).Prefix = %q, want %q", tt.ticket, tags.Prefix, tt.want)
			}
		})
	}

	// Verify that different cases produce different prefixes
	req1 := tagsTestRequest("GET", "/", map[string]string{"X-Slopstop-Ticket": "Bill-1"})
	req2 := tagsTestRequest("GET", "/", map[string]string{"X-Slopstop-Ticket": "BILL-1"})
	tags1, _ := ParseTags(req1)
	tags2, _ := ParseTags(req2)
	if tags1.Prefix == tags2.Prefix {
		t.Errorf("Bill != BILL, but both produced prefix %q", tags1.Prefix)
	}
}

// TestMalformedTicketUntagged verifies that 1BAD-2 (leading digit) and BILL207 (no dash) return untagged.
func TestMalformedTicketUntagged(t *testing.T) {
	tests := []struct {
		ticket string
		name   string
	}{
		{"1BAD-2", "leading digit"},
		{"BILL207", "no dash"},
		{"BILL-", "no number"},
		{"-1", "no prefix"},
		{"", "empty"},
		{"bill-abc", "non-numeric id"},
		{"Bill-1a", "id with letters"},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			req := tagsTestRequest("GET", "/", map[string]string{
				"X-Slopstop-Ticket": tt.ticket,
			})
			tags, _ := ParseTags(req)
			if tags.Ticket != "untagged" {
				t.Errorf("ParseTags(%q).Ticket = %q, want untagged", tt.ticket, tags.Ticket)
			}
			if tags.Prefix != "untagged" {
				t.Errorf("ParseTags(%q).Prefix = %q, want untagged", tt.ticket, tags.Prefix)
			}
		})
	}
}

// TestRunFromPathAndStrip verifies that /r/abc/v1/messages → run abc, path /v1/messages.
func TestRunFromPathAndStrip(t *testing.T) {
	tests := []struct {
		path     string
		wantRun  string
		wantPath string
	}{
		{"/r/abc/v1/messages", "abc", "/v1/messages"},
		{"/r/myrun/api/foo", "myrun", "/api/foo"},
		{"/r/xyz/", "xyz", "/"},
		{"/v1/messages", "untagged", "/v1/messages"},
		{"/r", "untagged", "/r"},
	}

	for _, tt := range tests {
		t.Run(tt.path, func(t *testing.T) {
			req := tagsTestRequest("GET", tt.path, nil)
			tags, path := ParseTags(req)
			if tags.Run != tt.wantRun {
				t.Errorf("ParseTags(%q).Run = %q, want %q", tt.path, tags.Run, tt.wantRun)
			}
			if path != tt.wantPath {
				t.Errorf("ParseTags(%q) path = %q, want %q", tt.path, path, tt.wantPath)
			}
		})
	}
}

// TestHeaderBeatsPath verifies that when both header and path prefix are present,
// the run-id comes from the header AND the returned path has /r/<run-id> stripped.
func TestHeaderBeatsPath(t *testing.T) {
	req := tagsTestRequest("GET", "/r/pathrun/v1/messages", map[string]string{
		"X-Slopstop-Run": "headerrun",
	})
	tags, path := ParseTags(req)

	// Run ID should come from header
	if tags.Run != "headerrun" {
		t.Errorf("ParseTags with both header and path.Run = %q, want headerrun", tags.Run)
	}

	// Path should still have /r/pathrun stripped
	if path != "/v1/messages" {
		t.Errorf("ParseTags with both header and path: path = %q, want /v1/messages", path)
	}

	// Verify that the path prefix was stripped despite the header winning
	if path != "/v1/messages" {
		t.Errorf("Path should still be stripped when header is present: got %q, want /v1/messages", path)
	}
}

// TestPathEdgeCases verifies edge cases: exactly /r/abc → run abc, path /; /r/ (empty id) → untagged, path unmodified.
func TestPathEdgeCases(t *testing.T) {
	tests := []struct {
		name     string
		path     string
		wantRun  string
		wantPath string
	}{
		{"exactly /r/abc", "/r/abc", "abc", "/"},
		{"empty run id /r/", "/r/", "untagged", "/r/"},
		{"/r/run with single slash", "/r/single", "single", "/"},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			req := tagsTestRequest("GET", tt.path, nil)
			tags, path := ParseTags(req)
			if tags.Run != tt.wantRun {
				t.Errorf("ParseTags(%q).Run = %q, want %q", tt.path, tags.Run, tt.wantRun)
			}
			if path != tt.wantPath {
				t.Errorf("ParseTags(%q) path = %q, want %q", tt.path, path, tt.wantPath)
			}
		})
	}
}

// TestNoTagsAllUntagged verifies that requests with no tags default to "untagged".
func TestNoTagsAllUntagged(t *testing.T) {
	req := tagsTestRequest("GET", "/v1/messages", nil)
	tags, path := ParseTags(req)

	if tags.Run != "untagged" {
		t.Errorf("ParseTags with no tags.Run = %q, want untagged", tags.Run)
	}
	if tags.Ticket != "untagged" {
		t.Errorf("ParseTags with no tags.Ticket = %q, want untagged", tags.Ticket)
	}
	if tags.Prefix != "untagged" {
		t.Errorf("ParseTags with no tags.Prefix = %q, want untagged", tags.Prefix)
	}
	if path != "/v1/messages" {
		t.Errorf("ParseTags with no tags path = %q, want /v1/messages", path)
	}
}
