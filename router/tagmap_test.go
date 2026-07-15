package main

import (
	"fmt"
	"sync"
	"testing"
)

func TestTagMap_SetGetClear(t *testing.T) {
	tm := NewTagMap()
	tm.Set("r1", "BILL-201")
	ticket, ok := tm.Get("r1")
	if !ok || ticket != "BILL-201" {
		t.Fatalf("Set/Get failed")
	}
	tm.Clear("r1")
	ticket, ok = tm.Get("r1")
	if ok {
		t.Fatalf("Clear failed")
	}
	if tm.Set("untagged", "BILL-1") == nil {
		t.Fatalf("Should reject untagged run")
	}
	if tm.Set("", "BILL-1") == nil {
		t.Fatalf("Should reject empty run")
	}
}

func TestTagMap_All(t *testing.T) {
	tm := NewTagMap()
	if len(tm.All()) != 0 {
		t.Fatalf("Empty map check failed")
	}
	tm.Set("r1", "BILL-201")
	tm.Set("r2", "SOP-5")
	tm.Set("r3", "BILL-100")
	all := tm.All()
	if len(all) != 3 {
		t.Fatalf("All() should have 3 entries")
	}
	if all["r1"] != "BILL-201" || all["r2"] != "SOP-5" || all["r3"] != "BILL-100" {
		t.Fatalf("All() entries incorrect")
	}
	tm.Clear("r2")
	all = tm.All()
	if len(all) != 2 {
		t.Fatalf("After Clear, map should have 2 entries")
	}
}

// TestTagMap_ConcurrentAccess exercises Set/Get/Clear/All from many goroutines on
// shared keys, per the file map's requirement to test "TagMap concurrent access".
// Run with -race: a single unguarded read/write would trip the race detector.
func TestTagMap_ConcurrentAccess(t *testing.T) {
	tm := NewTagMap()
	const goroutines = 50
	const opsPerGoroutine = 100

	var wg sync.WaitGroup
	for g := 0; g < goroutines; g++ {
		wg.Add(1)
		go func(id int) {
			defer wg.Done()
			run := fmt.Sprintf("r%d", id%5) // shared keys across goroutines
			for i := 0; i < opsPerGoroutine; i++ {
				switch i % 3 {
				case 0:
					tm.Set(run, fmt.Sprintf("BILL-%d", id))
				case 1:
					tm.Get(run)
				case 2:
					tm.All()
				}
			}
			tm.Clear(run)
		}(g)
	}
	wg.Wait()

	// No assertion on final map contents (concurrent writers race by design);
	// the test's purpose is to prove the mutex holds under -race, not to pin a
	// final state.
}
