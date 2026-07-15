package main

import (
	"fmt"
	"sync"
)

// TagMap holds a thread-safe mapping of run IDs to ticket IDs.
type TagMap struct {
	mu   sync.RWMutex
	tags map[string]string
}

// NewTagMap creates a new empty TagMap.
func NewTagMap() *TagMap {
	return &TagMap{
		tags: make(map[string]string),
	}
}

// Set stores a mapping from run to ticket. Returns an error if run is empty or "untagged".
func (tm *TagMap) Set(run, ticket string) error {
	if run == "" || run == "untagged" {
		return fmt.Errorf("invalid run: must not be empty or 'untagged'")
	}
	
	tm.mu.Lock()
	defer tm.mu.Unlock()
	tm.tags[run] = ticket
	return nil
}

// Clear removes a mapping for the given run.
func (tm *TagMap) Clear(run string) {
	tm.mu.Lock()
	defer tm.mu.Unlock()
	delete(tm.tags, run)
}

// Get retrieves the ticket for a run. Returns ("", false) if not found.
func (tm *TagMap) Get(run string) (string, bool) {
	tm.mu.RLock()
	defer tm.mu.RUnlock()
	ticket, ok := tm.tags[run]
	return ticket, ok
}

// All returns a copy of the entire map.
func (tm *TagMap) All() map[string]string {
	tm.mu.RLock()
	defer tm.mu.RUnlock()
	result := make(map[string]string)
	for k, v := range tm.tags {
		result[k] = v
	}
	return result
}
