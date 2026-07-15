package main

import (
	"bytes"
	"encoding/json"
	"net/http/httptest"
	"testing"
)

func TestTagHandler_Post_SetMapping(t *testing.T) {
	tm := NewTagMap()
	handler := tagHandler(tm)
	
	body := []byte(`{"run":"r1","ticket":"BILL-201"}`)
	req := httptest.NewRequest("POST", "/tag", bytes.NewReader(body))
	w := httptest.NewRecorder()
	
	handler.ServeHTTP(w, req)
	
	if w.Code != 200 {
		t.Fatalf("Expected 200, got %d", w.Code)
	}
	
	var resp map[string]string
	json.Unmarshal(w.Body.Bytes(), &resp)
	if resp["ticket"] != "BILL-201" || resp["prefix"] != "BILL" {
		t.Fatalf("Response incorrect: %v", resp)
	}
}

func TestTagHandler_Post_MalformedTicket(t *testing.T) {
	tm := NewTagMap()
	handler := tagHandler(tm)
	
	body := []byte(`{"run":"r1","ticket":"bad"}`)
	req := httptest.NewRequest("POST", "/tag", bytes.NewReader(body))
	w := httptest.NewRecorder()
	
	handler.ServeHTTP(w, req)
	
	if w.Code != 400 {
		t.Fatalf("Expected 400 for malformed ticket, got %d", w.Code)
	}
}

func TestTagHandler_Post_MissingRun(t *testing.T) {
	tm := NewTagMap()
	handler := tagHandler(tm)
	
	body := []byte(`{"ticket":"BILL-201"}`)
	req := httptest.NewRequest("POST", "/tag", bytes.NewReader(body))
	w := httptest.NewRecorder()
	
	handler.ServeHTTP(w, req)
	
	if w.Code != 400 {
		t.Fatalf("Expected 400 for missing run, got %d", w.Code)
	}
}

func TestTagHandler_Post_UntaggedRun(t *testing.T) {
	tm := NewTagMap()
	handler := tagHandler(tm)
	
	body := []byte(`{"run":"untagged","ticket":"BILL-201"}`)
	req := httptest.NewRequest("POST", "/tag", bytes.NewReader(body))
	w := httptest.NewRecorder()
	
	handler.ServeHTTP(w, req)
	
	if w.Code != 400 {
		t.Fatalf("Expected 400 for untagged run, got %d", w.Code)
	}
}

func TestTagHandler_Post_EmptyRun(t *testing.T) {
	tm := NewTagMap()
	handler := tagHandler(tm)
	
	body := []byte(`{"run":"","ticket":"BILL-201"}`)
	req := httptest.NewRequest("POST", "/tag", bytes.NewReader(body))
	w := httptest.NewRecorder()
	
	handler.ServeHTTP(w, req)
	
	if w.Code != 400 {
		t.Fatalf("Expected 400 for empty run, got %d", w.Code)
	}
}

func TestTagHandler_Post_ClearMapping(t *testing.T) {
	tm := NewTagMap()
	handler := tagHandler(tm)
	
	body := []byte(`{"run":"r1","ticket":""}`)
	req := httptest.NewRequest("POST", "/tag", bytes.NewReader(body))
	w := httptest.NewRecorder()
	
	handler.ServeHTTP(w, req)
	
	if w.Code != 200 {
		t.Fatalf("Expected 200 for clear, got %d", w.Code)
	}
	
	var resp map[string]string
	json.Unmarshal(w.Body.Bytes(), &resp)
	if resp["ticket"] != "untagged" {
		t.Fatalf("Expected untagged after clear, got %q", resp["ticket"])
	}
}

func TestTagHandler_Post_UntaggedTicket(t *testing.T) {
	tm := NewTagMap()
	handler := tagHandler(tm)
	
	body := []byte(`{"run":"r1","ticket":"untagged"}`)
	req := httptest.NewRequest("POST", "/tag", bytes.NewReader(body))
	w := httptest.NewRecorder()
	
	handler.ServeHTTP(w, req)
	
	if w.Code != 200 {
		t.Fatalf("Expected 200 for untagged ticket, got %d", w.Code)
	}
	
	var resp map[string]string
	json.Unmarshal(w.Body.Bytes(), &resp)
	if resp["ticket"] != "untagged" {
		t.Fatalf("Expected untagged in response, got %q", resp["ticket"])
	}
}

func TestTagHandler_Get_ReturnsMap(t *testing.T) {
	tm := NewTagMap()
	handler := tagHandler(tm)
	
	tm.Set("r1", "BILL-201")
	tm.Set("r2", "SOP-5")
	
	req := httptest.NewRequest("GET", "/tag", nil)
	w := httptest.NewRecorder()
	
	handler.ServeHTTP(w, req)
	
	if w.Code != 200 {
		t.Fatalf("Expected 200, got %d", w.Code)
	}
	
	var resp map[string]string
	json.Unmarshal(w.Body.Bytes(), &resp)
	if resp["r1"] != "BILL-201" || resp["r2"] != "SOP-5" {
		t.Fatalf("Response incorrect: %v", resp)
	}
}

func TestTagHandler_Get_EmptyMap(t *testing.T) {
	tm := NewTagMap()
	handler := tagHandler(tm)
	
	req := httptest.NewRequest("GET", "/tag", nil)
	w := httptest.NewRecorder()
	
	handler.ServeHTTP(w, req)
	
	if w.Code != 200 {
		t.Fatalf("Expected 200, got %d", w.Code)
	}
	
	body := w.Body.String()
	if body != "{}\n" {
		t.Fatalf("Expected empty map response, got %q", body)
	}
}
