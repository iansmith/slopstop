package main

import (
	"bufio"
	"bytes"
	"encoding/json"
)

// UsageFromJSON extracts token usage from a non-streaming JSON response body.
// It returns the extracted Tokens and ok=true on success, or (Tokens{}, ok=false)
// if the body cannot be parsed or lacks a usage object.
func UsageFromJSON(body []byte) (Tokens, bool) {
	var resp struct {
		Usage *Tokens `json:"usage"`
	}

	if err := json.Unmarshal(body, &resp); err != nil {
		return Tokens{}, false
	}

	if resp.Usage == nil {
		return Tokens{}, false
	}

	return *resp.Usage, true
}

// UsageFromSSE extracts token usage from a streaming SSE response body.
// The stream must contain:
// - A message_start event with usage containing input and cache tokens
// - One or more message_delta events with cumulative output_tokens
// The final output_tokens value is used (not the sum of deltas).
// Returns (Tokens, ok=true) on success or (Tokens{}, ok=false) on parse error.
func UsageFromSSE(body []byte) (Tokens, bool) {
	result := Tokens{}
	scanner := bufio.NewScanner(bytes.NewReader(body))

	for scanner.Scan() {
		line := scanner.Bytes()

		// Skip empty lines
		if len(line) == 0 {
			continue
		}

		// Look for event lines
		if eventStr, ok := bytes.CutPrefix(line, []byte("event: ")); ok {
			eventType := string(eventStr)

			// Read the next line which should be the data
			if !scanner.Scan() {
				return Tokens{}, false
			}
			dataLine := scanner.Bytes()

			dataJSON, ok := bytes.CutPrefix(dataLine, []byte("data: "))
			if !ok {
				return Tokens{}, false
			}

			switch eventType {
			case "message_start":
				var event struct {
					Message struct {
						Usage *Tokens `json:"usage"`
					} `json:"message"`
				}
				if err := json.Unmarshal(dataJSON, &event); err != nil {
					return Tokens{}, false
				}
				if event.Message.Usage != nil {
					result = *event.Message.Usage
				}

			case "message_delta":
				var event struct {
					Usage *Tokens `json:"usage"`
				}
				if err := json.Unmarshal(dataJSON, &event); err != nil {
					return Tokens{}, false
				}
				if event.Usage != nil {
					// Update output_tokens to the cumulative value
					if event.Usage.OutputTokens > 0 {
						result.OutputTokens = event.Usage.OutputTokens
					}
				}
			}
		}
	}

	// If we never got any usage data from message_start, fail
	if result == (Tokens{}) {
		return Tokens{}, false
	}

	return result, true
}

// ModelFromRequest extracts the model field from a Messages API request body.
// Returns (model, ok=true) if the model field is present, or ("", ok=false) otherwise.
func ModelFromRequest(body []byte) (string, bool) {
	var req struct {
		Model string `json:"model"`
	}

	if err := json.Unmarshal(body, &req); err != nil {
		return "", false
	}

	if req.Model == "" {
		return "", false
	}

	return req.Model, true
}
