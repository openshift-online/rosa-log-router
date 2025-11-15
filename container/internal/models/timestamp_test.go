package models

import (
	"testing"
	"time"

	"github.com/stretchr/testify/assert"
)

func TestProcessTimestampLikeVector_StringISO(t *testing.T) {
	testCases := []struct {
		name              string
		timestamp         string
		expectedTimestamp int64 // in milliseconds
	}{
		{
			name:              "RFC3339_with_Z",
			timestamp:         "2024-01-15T10:30:00Z",
			expectedTimestamp: time.Date(2024, 1, 15, 10, 30, 0, 0, time.UTC).UnixMilli(),
		},
		{
			name:              "RFC3339_with_timezone",
			timestamp:         "2024-01-15T10:30:00+00:00",
			expectedTimestamp: time.Date(2024, 1, 15, 10, 30, 0, 0, time.UTC).UnixMilli(),
		},
		{
			name:              "RFC3339Nano_with_Z",
			timestamp:         "2024-01-15T10:30:00.123456789Z",
			expectedTimestamp: time.Date(2024, 1, 15, 10, 30, 0, 123456789, time.UTC).UnixMilli(),
		},
		{
			name:              "RFC3339Nano_with_timezone",
			timestamp:         "2024-01-15T10:30:00.123456789+00:00",
			expectedTimestamp: time.Date(2024, 1, 15, 10, 30, 0, 123456789, time.UTC).UnixMilli(),
		},
	}

	for _, tc := range testCases {
		t.Run(tc.name, func(t *testing.T) {
			result := ProcessTimestampLikeVector(tc.timestamp, nil)
			assert.Equal(t, tc.expectedTimestamp, result)
		})
	}
}

func TestProcessTimestampLikeVector_StringInvalid(t *testing.T) {
	// Invalid timestamp should return current time (within 1 second)
	before := time.Now().UnixMilli()
	result := ProcessTimestampLikeVector("invalid-timestamp", nil)
	after := time.Now().UnixMilli()

	assert.GreaterOrEqual(t, result, before)
	assert.LessOrEqual(t, result, after)
}

func TestProcessTimestampLikeVector_Float64Milliseconds(t *testing.T) {
	// Timestamp in milliseconds (> 1000000000000.0)
	timestampMs := 1705318200000.0 // 2024-01-15T10:30:00Z in milliseconds
	result := ProcessTimestampLikeVector(timestampMs, nil)
	assert.Equal(t, int64(1705318200000), result)
}

func TestProcessTimestampLikeVector_Float64Seconds(t *testing.T) {
	// Timestamp in seconds (< 1000000000000.0)
	timestampSec := 1705318200.0 // 2024-01-15T10:30:00Z in seconds
	result := ProcessTimestampLikeVector(timestampSec, nil)
	assert.Equal(t, int64(1705318200000), result)
}

func TestProcessTimestampLikeVector_Int64Milliseconds(t *testing.T) {
	// Timestamp in milliseconds (> 1000000000000)
	timestampMs := int64(1705318200000)
	result := ProcessTimestampLikeVector(timestampMs, nil)
	assert.Equal(t, int64(1705318200000), result)
}

func TestProcessTimestampLikeVector_Int64Seconds(t *testing.T) {
	// Timestamp in seconds (< 1000000000000)
	timestampSec := int64(1705318200)
	result := ProcessTimestampLikeVector(timestampSec, nil)
	assert.Equal(t, int64(1705318200000), result)
}

func TestProcessTimestampLikeVector_IntMilliseconds(t *testing.T) {
	// Timestamp in milliseconds (> 1000000000000)
	timestampMs := int(1705318200000)
	result := ProcessTimestampLikeVector(timestampMs, nil)
	assert.Equal(t, int64(1705318200000), result)
}

func TestProcessTimestampLikeVector_IntSeconds(t *testing.T) {
	// Timestamp in seconds (< 1000000000000)
	timestampSec := int(1705318200)
	result := ProcessTimestampLikeVector(timestampSec, nil)
	assert.Equal(t, int64(1705318200000), result)
}

func TestProcessTimestampLikeVector_Nil(t *testing.T) {
	// Nil timestamp should return current time (within 1 second)
	before := time.Now().UnixMilli()
	result := ProcessTimestampLikeVector(nil, nil)
	after := time.Now().UnixMilli()

	assert.GreaterOrEqual(t, result, before)
	assert.LessOrEqual(t, result, after)
}

func TestProcessTimestampLikeVector_UnknownType(t *testing.T) {
	// Unknown type should return current time (within 1 second)
	before := time.Now().UnixMilli()
	result := ProcessTimestampLikeVector(struct{}{}, nil)
	after := time.Now().UnixMilli()

	assert.GreaterOrEqual(t, result, before)
	assert.LessOrEqual(t, result, after)
}

func TestParseISOTimestamp_Success(t *testing.T) {
	testCases := []struct {
		name              string
		timestamp         string
		expectedTimestamp time.Time
	}{
		{
			name:              "RFC3339_with_Z",
			timestamp:         "2024-01-15T10:30:00Z",
			expectedTimestamp: time.Date(2024, 1, 15, 10, 30, 0, 0, time.UTC),
		},
		{
			name:              "RFC3339_with_timezone",
			timestamp:         "2024-01-15T10:30:00+00:00",
			expectedTimestamp: time.Date(2024, 1, 15, 10, 30, 0, 0, time.UTC),
		},
		{
			name:              "RFC3339Nano_with_Z",
			timestamp:         "2024-01-15T10:30:00.123Z",
			expectedTimestamp: time.Date(2024, 1, 15, 10, 30, 0, 123000000, time.UTC),
		},
	}

	for _, tc := range testCases {
		t.Run(tc.name, func(t *testing.T) {
			result, err := parseISOTimestamp(tc.timestamp)
			assert.NoError(t, err)
			assert.Equal(t, tc.expectedTimestamp.Unix(), result.Unix())
		})
	}
}

func TestParseISOTimestamp_Error(t *testing.T) {
	testCases := []struct {
		name      string
		timestamp string
	}{
		{
			name:      "invalid_format",
			timestamp: "2024-01-15 10:30:00",
		},
		{
			name:      "empty_string",
			timestamp: "",
		},
		{
			name:      "malformed_date",
			timestamp: "not-a-date",
		},
	}

	for _, tc := range testCases {
		t.Run(tc.name, func(t *testing.T) {
			_, err := parseISOTimestamp(tc.timestamp)
			assert.Error(t, err)
		})
	}
}
