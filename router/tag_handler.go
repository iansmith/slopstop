package main

import (
	"encoding/json"
	"net/http"
)

// tagHandler returns an HTTP handler that dispatches POST and GET /tag requests.
func tagHandler(tm *TagMap) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		if r.Method == "POST" {
			handleTagPost(w, r, tm)
		} else if r.Method == "GET" {
			handleTagGet(w, r, tm)
		} else {
			w.WriteHeader(http.StatusMethodNotAllowed)
		}
	}
}

// handleTagPost handles POST /tag requests.
func handleTagPost(w http.ResponseWriter, r *http.Request, tm *TagMap) {
	var req struct {
		Run    string `json:"run"`
		Ticket string `json:"ticket"`
	}
	
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusBadRequest)
		json.NewEncoder(w).Encode(map[string]string{"error": "invalid JSON"})
		return
	}
	
	// Validate run
	if req.Run == "" || req.Run == "untagged" {
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusBadRequest)
		json.NewEncoder(w).Encode(map[string]string{"error": "invalid run"})
		return
	}
	
	// If ticket is empty or "untagged", clear the mapping
	if req.Ticket == "" || req.Ticket == "untagged" {
		tm.Clear(req.Run)
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusOK)
		json.NewEncoder(w).Encode(map[string]string{
			"run": req.Run,
			"ticket": "untagged",
			"prefix": "untagged",
		})
		return
	}
	
	// Validate ticket format
	ticket, prefix := parseTicket(req.Ticket)
	if ticket == "untagged" {
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusBadRequest)
		json.NewEncoder(w).Encode(map[string]string{"error": "malformed ticket"})
		return
	}
	
	// Set the mapping
	tm.Set(req.Run, ticket)
	
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(http.StatusOK)
	json.NewEncoder(w).Encode(map[string]string{
		"run": req.Run,
		"ticket": ticket,
		"prefix": prefix,
	})
}

// handleTagGet handles GET /tag requests.
func handleTagGet(w http.ResponseWriter, r *http.Request, tm *TagMap) {
	all := tm.All()
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(http.StatusOK)
	json.NewEncoder(w).Encode(all)
}
