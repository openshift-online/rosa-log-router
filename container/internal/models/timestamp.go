package models

import (
	"errors"
	"log/slog"
	"strings"
	"time"
)

// ProcessTimestampLikeVector processes timestamp exactly like Vector's extract_timestamp transform.
// Handles ISO strings, numeric values, and millisecond/second detection.
// Returns timestamp in milliseconds for CloudWatch API.
//
// This matches the Python implementation in log_processor.py:process_timestamp_like_vector
func ProcessTimestampLikeVector(timestamp interface{}, logger *slog.Logger) int64 {
	switch ts := timestamp.(type) {
	case string:
		// Handle ISO timestamp string (Vector uses "%+" format)
		// Try multiple ISO formats for robustness
		parsedTime, err := parseISOTimestamp(ts)
		if err == nil {
			return parsedTime.UnixMilli()
		}

		if logger != nil {
			logger.Warn("failed to parse timestamp string, using current time",
				"timestamp", ts,
				"error", err)
		}
		return time.Now().UnixMilli()

	case float64:
		// Vector's logic: if value > 1000000000000.0, it's milliseconds
		if ts > 1000000000000.0 {
			return int64(ts)
		}
		// In seconds, convert to milliseconds
		return int64(ts * 1000)

	case int64:
		// Direct int64 timestamp
		if ts > 1000000000000 {
			return ts
		}
		return ts * 1000

	case int:
		// Direct int timestamp
		ts64 := int64(ts)
		if ts64 > 1000000000000 {
			return ts64
		}
		return ts64 * 1000

	default:
		// Unknown type or nil, use current time
		if logger != nil {
			logger.Warn("unknown timestamp type, using current time",
				"type", ts,
				"value", timestamp)
		}
		return time.Now().UnixMilli()
	}
}

// parseISOTimestamp attempts to parse ISO timestamp strings in multiple formats
func parseISOTimestamp(ts string) (time.Time, error) {
	// Handle trailing 'Z' by replacing with +00:00 timezone
	if strings.HasSuffix(ts, "Z") {
		ts = ts[:len(ts)-1] + "+00:00"
	}

	// Try RFC3339 format first (most common)
	if t, err := time.Parse(time.RFC3339, ts); err == nil {
		return t, nil
	}

	// Try RFC3339Nano format (with nanoseconds)
	if t, err := time.Parse(time.RFC3339Nano, ts); err == nil {
		return t, nil
	}

	// Try without timezone conversion (in case Z was already replaced)
	originalTS := ts
	if strings.HasSuffix(originalTS, "Z") {
		if t, err := time.Parse(time.RFC3339, originalTS); err == nil {
			return t, nil
		}
		if t, err := time.Parse(time.RFC3339Nano, originalTS); err == nil {
			return t, nil
		}
	}

	return time.Time{}, errors.New("unable to parse timestamp")
}
