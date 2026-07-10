package main

import (
	"sync"
	"time"
)

// Meter aggregates request counts, token usage, and costs by prefix, run, ticket, tier, and model.
// It is concurrency-safe and does not persist any data.
type Meter struct {
	mu       sync.RWMutex
	StartedAt time.Time

	// data[prefix][run][ticket][tier][model] = aggregate
	data map[string]map[string]map[string]map[string]map[string]*aggregate

	// unpriced tracks unknown-model and unparseable records
	unpriced *unpriced
}

// aggregate holds summed counts and totals for a (prefix, run, ticket, tier, model) tuple.
type aggregate struct {
	Requests int64
	Tokens   Tokens
	USD      float64
}

// unpriced tracks unknown-model and unparseable records separately.
type unpriced struct {
	Requests int64
	Tokens   Tokens
	Models   map[string]bool // set of distinct model names
}

// Snapshot represents a filtered view of the meter's aggregates.
type Snapshot struct {
	Requests int64
	Tokens   Tokens
	USD      float64
	Unpriced UnpricedSnapshot
}

// UnpricedSnapshot holds unpriced aggregates.
type UnpricedSnapshot struct {
	Requests int64
	Tokens   Tokens
	Models   map[string]bool
}

// NewMeter creates a new empty meter with StartedAt set to the current time.
func NewMeter() *Meter {
	return &Meter{
		StartedAt: time.Now(),
		data:      make(map[string]map[string]map[string]map[string]map[string]*aggregate),
		unpriced: &unpriced{
			Models: make(map[string]bool),
		},
	}
}

// Record aggregates a single request by prefix, run, ticket, tier, and model.
// known indicates whether the model was found in the price table.
// If known=false, the record is added to unpriced.
// If tokens are all zero (unparseable usage), only unpriced.requests is incremented.
func (m *Meter) Record(tags Tags, model string, tier string, tokens Tokens, usd float64, known bool) {
	m.mu.Lock()
	defer m.mu.Unlock()

	// Ensure nested map structure exists
	if m.data[tags.Prefix] == nil {
		m.data[tags.Prefix] = make(map[string]map[string]map[string]map[string]*aggregate)
	}
	if m.data[tags.Prefix][tags.Run] == nil {
		m.data[tags.Prefix][tags.Run] = make(map[string]map[string]map[string]*aggregate)
	}
	if m.data[tags.Prefix][tags.Run][tags.Ticket] == nil {
		m.data[tags.Prefix][tags.Run][tags.Ticket] = make(map[string]map[string]*aggregate)
	}
	if m.data[tags.Prefix][tags.Run][tags.Ticket][tier] == nil {
		m.data[tags.Prefix][tags.Run][tags.Ticket][tier] = make(map[string]*aggregate)
	}

	key := model
	if m.data[tags.Prefix][tags.Run][tags.Ticket][tier][key] == nil {
		m.data[tags.Prefix][tags.Run][tags.Ticket][tier][key] = &aggregate{}
	}

	agg := m.data[tags.Prefix][tags.Run][tags.Ticket][tier][key]

	// Always increment the aggregate (all records count toward totals)
	agg.Requests++
	agg.Tokens.InputTokens += tokens.InputTokens
	agg.Tokens.OutputTokens += tokens.OutputTokens
	agg.Tokens.CacheCreationInputTokens += tokens.CacheCreationInputTokens
	agg.Tokens.CacheReadInputTokens += tokens.CacheReadInputTokens
	agg.USD += usd

	// Check if tokens are all zero (unparseable usage)
	isUnparseable := tokens == (Tokens{})

	// Handle unpriced accounting
	if !known {
		// Unknown model: increment unpriced completely
		m.unpriced.Requests++
		m.unpriced.Tokens.InputTokens += tokens.InputTokens
		m.unpriced.Tokens.OutputTokens += tokens.OutputTokens
		m.unpriced.Tokens.CacheCreationInputTokens += tokens.CacheCreationInputTokens
		m.unpriced.Tokens.CacheReadInputTokens += tokens.CacheReadInputTokens
		m.unpriced.Models[model] = true
	} else if isUnparseable {
		// Unparseable usage: only increment unpriced.requests
		m.unpriced.Requests++
	}
}

// Snapshot returns aggregates for a given prefix, optionally filtered by run.
// If run is empty string, all runs are included.
// If the prefix does not exist, returns zeroed aggregates.
func (m *Meter) Snapshot(prefix, run string) Snapshot {
	m.mu.RLock()
	defer m.mu.RUnlock()

	result := Snapshot{
		Unpriced: UnpricedSnapshot{
			Models: make(map[string]bool),
		},
	}

	prefixData, ok := m.data[prefix]
	if !ok {
		return result
	}

	// If run is specified, only aggregate that run; otherwise aggregate all runs
	if run != "" {
		// Single run
		runData, ok := prefixData[run]
		if !ok {
			return result
		}
		m.aggregateRunData(runData, &result)
	} else {
		// All runs
		for _, runData := range prefixData {
			m.aggregateRunData(runData, &result)
		}
	}

	// Copy unpriced data from meter
	result.Unpriced.Requests = m.unpriced.Requests
	result.Unpriced.Tokens = m.unpriced.Tokens
	for model := range m.unpriced.Models {
		result.Unpriced.Models[model] = true
	}

	return result
}

// aggregateRunData sums all aggregates within a run's data (across all tickets, tiers, models).
func (m *Meter) aggregateRunData(runData map[string]map[string]map[string]*aggregate, result *Snapshot) {
	for _, ticketData := range runData {
		for _, tierData := range ticketData {
			for _, agg := range tierData {
				result.Requests += agg.Requests
				result.Tokens.InputTokens += agg.Tokens.InputTokens
				result.Tokens.OutputTokens += agg.Tokens.OutputTokens
				result.Tokens.CacheCreationInputTokens += agg.Tokens.CacheCreationInputTokens
				result.Tokens.CacheReadInputTokens += agg.Tokens.CacheReadInputTokens
				result.USD += agg.USD
			}
		}
	}
}
