package main

import (
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
