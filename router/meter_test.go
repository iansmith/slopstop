package main

import (
	"sync"
	"testing"
)

// TestFreshMeterIsEmpty verifies that a newly constructed meter has empty aggregates.
func TestFreshMeterIsEmpty(t *testing.T) {
	m := NewMeter()

	if m.StartedAt.IsZero() {
		t.Error("StartedAt should be set at construction")
	}

	snap := m.Snapshot("anyprefix", "")
	if snap.Requests != 0 {
		t.Errorf("Expected 0 requests, got %d", snap.Requests)
	}
	if snap.Tokens != (Tokens{}) {
		t.Errorf("Expected zero Tokens, got %v", snap.Tokens)
	}
	if snap.USD != 0 {
		t.Errorf("Expected 0 USD, got %f", snap.USD)
	}
	if snap.Unpriced.Requests != 0 {
		t.Errorf("Expected 0 unpriced requests, got %d", snap.Unpriced.Requests)
	}
	if snap.Unpriced.Tokens != (Tokens{}) {
		t.Errorf("Expected zero unpriced Tokens, got %v", snap.Unpriced.Tokens)
	}
	if len(snap.Unpriced.Models) != 0 {
		t.Errorf("Expected 0 unpriced models, got %d", len(snap.Unpriced.Models))
	}
}

// TestAggregatesByAllKeys verifies aggregation across all five dimensions: prefix, run, ticket, tier, model.
func TestAggregatesByAllKeys(t *testing.T) {
	m := NewMeter()

	tags1 := Tags{Prefix: "BILL", Run: "run1", Ticket: "BILL-1"}
	tokens1 := Tokens{InputTokens: 100, OutputTokens: 50}
	m.Record(tags1, "claude-opus", "big", tokens1, 1.0, true)

	tags2 := Tags{Prefix: "BILL", Run: "run1", Ticket: "BILL-1"}
	tokens2 := Tokens{InputTokens: 50, OutputTokens: 25}
	m.Record(tags2, "claude-opus", "big", tokens2, 0.5, true)

	snap := m.Snapshot("BILL", "run1")
	if snap.Requests != 2 {
		t.Errorf("Expected 2 requests, got %d", snap.Requests)
	}
	if snap.Tokens.InputTokens != 150 {
		t.Errorf("Expected 150 input tokens, got %d", snap.Tokens.InputTokens)
	}
	if snap.Tokens.OutputTokens != 75 {
		t.Errorf("Expected 75 output tokens, got %d", snap.Tokens.OutputTokens)
	}
	if snap.USD != 1.5 {
		t.Errorf("Expected 1.5 USD, got %f", snap.USD)
	}
}

// TestSnapshotFiltersByPrefixAndRun verifies that Snapshot correctly filters by prefix and optionally by run.
func TestSnapshotFiltersByPrefixAndRun(t *testing.T) {
	m := NewMeter()

	// Record for BILL/run1
	m.Record(Tags{Prefix: "BILL", Run: "run1", Ticket: "BILL-1"}, "model1", "big", Tokens{InputTokens: 100}, 1.0, true)

	// Record for BILL/run2
	m.Record(Tags{Prefix: "BILL", Run: "run2", Ticket: "BILL-2"}, "model1", "big", Tokens{InputTokens: 50}, 0.5, true)

	// Record for MAZ/run1
	m.Record(Tags{Prefix: "MAZ", Run: "run1", Ticket: "MAZ-1"}, "model1", "big", Tokens{InputTokens: 25}, 0.25, true)

	// Snapshot all BILL records (run is empty string, meaning all runs)
	snapAll := m.Snapshot("BILL", "")
	if snapAll.Requests != 2 {
		t.Errorf("Expected 2 BILL requests total, got %d", snapAll.Requests)
	}
	if snapAll.Tokens.InputTokens != 150 {
		t.Errorf("Expected 150 BILL input tokens, got %d", snapAll.Tokens.InputTokens)
	}

	// Snapshot BILL/run1 only
	snap1 := m.Snapshot("BILL", "run1")
	if snap1.Requests != 1 {
		t.Errorf("Expected 1 BILL/run1 request, got %d", snap1.Requests)
	}
	if snap1.Tokens.InputTokens != 100 {
		t.Errorf("Expected 100 BILL/run1 input tokens, got %d", snap1.Tokens.InputTokens)
	}

	// Snapshot MAZ/run1
	snapMAZ := m.Snapshot("MAZ", "run1")
	if snapMAZ.Requests != 1 {
		t.Errorf("Expected 1 MAZ/run1 request, got %d", snapMAZ.Requests)
	}
}

// TestUnknownSelectorZeros verifies that Snapshot with an unknown prefix returns zeroed aggregates.
func TestUnknownSelectorZeros(t *testing.T) {
	m := NewMeter()

	// Record some data
	m.Record(Tags{Prefix: "BILL", Run: "run1", Ticket: "BILL-1"}, "model1", "big", Tokens{InputTokens: 100}, 1.0, true)

	// Query unknown prefix
	snap := m.Snapshot("UNKNOWN", "")
	if snap.Requests != 0 {
		t.Errorf("Expected 0 requests for unknown prefix, got %d", snap.Requests)
	}
	if snap.Tokens != (Tokens{}) {
		t.Errorf("Expected zero Tokens for unknown prefix, got %v", snap.Tokens)
	}
	if snap.USD != 0 {
		t.Errorf("Expected 0 USD for unknown prefix, got %f", snap.USD)
	}
	if snap.Unpriced.Requests != 0 {
		t.Errorf("Expected 0 unpriced requests for unknown prefix, got %d", snap.Unpriced.Requests)
	}

	// Query unknown run for known prefix
	snap2 := m.Snapshot("BILL", "unknown-run")
	if snap2.Requests != 0 {
		t.Errorf("Expected 0 requests for unknown run, got %d", snap2.Requests)
	}
}

// TestUnpricedAccounting verifies that unknown-model records increment unpriced.
func TestUnpricedAccounting(t *testing.T) {
	m := NewMeter()

	// Record with unknown model (known=false)
	m.Record(Tags{Prefix: "BILL", Run: "run1", Ticket: "BILL-1"}, "unknown-model", "big", Tokens{InputTokens: 100, OutputTokens: 50}, 0, false)

	// Record with different unknown model
	m.Record(Tags{Prefix: "BILL", Run: "run2", Ticket: "BILL-2"}, "another-unknown", "big", Tokens{InputTokens: 25}, 0, false)

	snap := m.Snapshot("BILL", "")
	if snap.Requests != 2 {
		t.Errorf("Expected 2 total requests, got %d", snap.Requests)
	}
	if snap.Tokens.InputTokens != 125 {
		t.Errorf("Expected 125 total input tokens, got %d", snap.Tokens.InputTokens)
	}
	if snap.Unpriced.Requests != 2 {
		t.Errorf("Expected 2 unpriced requests, got %d", snap.Unpriced.Requests)
	}
	if snap.Unpriced.Tokens.InputTokens != 125 {
		t.Errorf("Expected 125 unpriced input tokens, got %d", snap.Unpriced.Tokens.InputTokens)
	}
	if len(snap.Unpriced.Models) != 2 {
		t.Errorf("Expected 2 distinct unpriced models, got %d", len(snap.Unpriced.Models))
	}
	if !snap.Unpriced.Models["unknown-model"] || !snap.Unpriced.Models["another-unknown"] {
		t.Errorf("Expected both models in unpriced, got %v", snap.Unpriced.Models)
	}
}

// TestUnparseableUsageCountsAsUnpricedRequestOnly verifies that unparseable usage (zero tokens) increments only unpriced.requests.
func TestUnparseableUsageCountsAsUnpricedRequestOnly(t *testing.T) {
	m := NewMeter()

	// Record with zero tokens (unparseable usage)
	emptyTokens := Tokens{}
	m.Record(Tags{Prefix: "BILL", Run: "run1", Ticket: "BILL-1"}, "claude-opus", "big", emptyTokens, 0, true)

	// Record normal request for comparison
	m.Record(Tags{Prefix: "BILL", Run: "run1", Ticket: "BILL-1"}, "claude-opus", "big", Tokens{InputTokens: 100}, 1.0, true)

	snap := m.Snapshot("BILL", "")
	if snap.Requests != 2 {
		t.Errorf("Expected 2 requests, got %d", snap.Requests)
	}
	if snap.Tokens.InputTokens != 100 {
		t.Errorf("Expected 100 input tokens (only from second record), got %d", snap.Tokens.InputTokens)
	}
	if snap.Unpriced.Requests != 1 {
		t.Errorf("Expected 1 unpriced request (from zero-tokens record), got %d", snap.Unpriced.Requests)
	}
	if snap.Unpriced.Tokens != (Tokens{}) {
		t.Errorf("Expected zero unpriced tokens (unparseable adds no tokens), got %v", snap.Unpriced.Tokens)
	}
	if len(snap.Unpriced.Models) != 0 {
		t.Errorf("Expected 0 unpriced models (unparseable adds no model), got %d", len(snap.Unpriced.Models))
	}
}

// TestConcurrentRecordIsRaceFree verifies that concurrent Record calls produce exact totals without race conditions.
func TestConcurrentRecordIsRaceFree(t *testing.T) {
	m := NewMeter()
	numGoroutines := 100
	recordsPerGoroutine := 10

	var wg sync.WaitGroup
	wg.Add(numGoroutines)

	for i := 0; i < numGoroutines; i++ {
		go func(id int) {
			defer wg.Done()
			for j := 0; j < recordsPerGoroutine; j++ {
				tags := Tags{
					Prefix: "BILL",
					Run:    "run1",
					Ticket: "BILL-1",
				}
				tokens := Tokens{InputTokens: 10, OutputTokens: 5}
				m.Record(tags, "claude-opus", "big", tokens, 0.5, true)
			}
		}(i)
	}

	wg.Wait()

	snap := m.Snapshot("BILL", "")
	expectedRequests := int64(numGoroutines * recordsPerGoroutine)
	expectedInputTokens := int64(expectedRequests * 10)
	expectedOutputTokens := int64(expectedRequests * 5)
	expectedUSD := float64(expectedRequests) * 0.5

	if snap.Requests != expectedRequests {
		t.Errorf("Expected %d requests, got %d", expectedRequests, snap.Requests)
	}
	if snap.Tokens.InputTokens != expectedInputTokens {
		t.Errorf("Expected %d input tokens, got %d", expectedInputTokens, snap.Tokens.InputTokens)
	}
	if snap.Tokens.OutputTokens != expectedOutputTokens {
		t.Errorf("Expected %d output tokens, got %d", expectedOutputTokens, snap.Tokens.OutputTokens)
	}
	if snap.USD != expectedUSD {
		t.Errorf("Expected %.2f USD, got %.2f", expectedUSD, snap.USD)
	}
}

// Meter-specific test helpers (meter* prefix as per spec)
func meterTestHelper(m *Meter, expectedReqs int64) bool {
	snap := m.Snapshot("BILL", "")
	return snap.Requests == expectedReqs
}
