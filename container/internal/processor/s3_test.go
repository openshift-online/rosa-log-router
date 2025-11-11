package processor

import (
	"fmt"
	"log/slog"
	"os"
	"testing"

	"github.com/openshift/rosa-log-router/internal/models"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

func getTestLogger() *slog.Logger {
	return slog.New(slog.NewJSONHandler(os.Stdout, &slog.HandlerOptions{
		Level: slog.LevelError, // Reduce noise in tests
	}))
}

func TestExtractTenantInfoFromKey(t *testing.T) {
	logger := getTestLogger()

	t.Run("extracts tenant info from valid key", func(t *testing.T) {
		objectKey := "prod-cluster-1/openshift-logging/fluentd/fluentd-abc123/20240101-uuid.json.gz"

		tenantInfo, err := ExtractTenantInfoFromKey(objectKey, logger)

		require.NoError(t, err)
		assert.Equal(t, "prod-cluster-1", tenantInfo.ClusterID)
		assert.Equal(t, "openshift-logging", tenantInfo.Namespace)
		assert.Equal(t, "openshift-logging", tenantInfo.TenantID)
		assert.Equal(t, "fluentd", tenantInfo.Application)
		assert.Equal(t, "fluentd-abc123", tenantInfo.PodName)
		assert.Equal(t, "production", tenantInfo.Environment) // prod prefix detected
	})

	t.Run("extracts environment from cluster ID prefix", func(t *testing.T) {
		testCases := []struct {
			clusterID   string
			expectedEnv string
		}{
			{"prod-cluster-1", "production"},
			{"stg-cluster-2", "staging"},
			{"dev-cluster-3", "development"},
			{"other-cluster-4", "production"}, // Default
		}

		for _, tc := range testCases {
			objectKey := tc.clusterID + "/namespace/app/pod/file.json.gz"
			tenantInfo, err := ExtractTenantInfoFromKey(objectKey, logger)

			require.NoError(t, err)
			assert.Equal(t, tc.expectedEnv, tenantInfo.Environment, "cluster_id: %s", tc.clusterID)
		}
	})

	t.Run("fails with insufficient path segments", func(t *testing.T) {
		objectKey := "cluster/namespace/app"

		_, err := ExtractTenantInfoFromKey(objectKey, logger)

		require.Error(t, err)
		assert.Contains(t, err.Error(), "invalid object key format")
		assert.Contains(t, err.Error(), "Expected at least 5 path segments")
	})

	t.Run("fails with empty path segment", func(t *testing.T) {
		objectKey := "cluster//app/pod/file.json.gz" // Empty namespace

		_, err := ExtractTenantInfoFromKey(objectKey, logger)

		require.Error(t, err)
		assert.Contains(t, err.Error(), "cannot be empty")
	})

	t.Run("handles paths with extra segments", func(t *testing.T) {
		objectKey := "cluster/namespace/app/pod/subdir/file.json.gz"

		tenantInfo, err := ExtractTenantInfoFromKey(objectKey, logger)

		require.NoError(t, err)
		assert.Equal(t, "cluster", tenantInfo.ClusterID)
		assert.Equal(t, "namespace", tenantInfo.Namespace)
		assert.Equal(t, "app", tenantInfo.Application)
		assert.Equal(t, "pod", tenantInfo.PodName)
	})
}

func TestConvertLogRecordToEvent(t *testing.T) {
	logger := getTestLogger()

	t.Run("converts record with timestamp and message", func(t *testing.T) {
		record := map[string]any{
			"timestamp": "2024-01-01T12:00:00Z",
			"message":   "test log message",
		}

		event := ConvertLogRecordToEvent(record, logger)

		require.NotNil(t, event)
		ts, ok := event.Timestamp.(int64)
		require.True(t, ok, "timestamp should be int64")
		assert.Greater(t, ts, int64(0))
		assert.Equal(t, "test log message", event.Message)
	})

	t.Run("handles numeric timestamp in seconds", func(t *testing.T) {
		record := map[string]any{
			"timestamp": float64(1704110400), // 2024-01-01 12:00:00 UTC in seconds
			"message":   "test",
		}

		event := ConvertLogRecordToEvent(record, logger)

		require.NotNil(t, event)
		assert.Equal(t, int64(1704110400000), event.Timestamp) // Converted to milliseconds
	})

	t.Run("handles numeric timestamp in milliseconds", func(t *testing.T) {
		record := map[string]any{
			"timestamp": float64(1704110400000), // Already in milliseconds
			"message":   "test",
		}

		event := ConvertLogRecordToEvent(record, logger)

		require.NotNil(t, event)
		assert.Equal(t, int64(1704110400000), event.Timestamp)
	})

	t.Run("uses fallback when message field is missing", func(t *testing.T) {
		record := map[string]any{
			"timestamp": "2024-01-01T12:00:00Z",
			"level":     "INFO",
			"data":      "some data",
		}

		event := ConvertLogRecordToEvent(record, logger)

		require.NotNil(t, event)
		// Message should be a map without Vector metadata fields
		messageMap, ok := event.Message.(map[string]any)
		require.True(t, ok)
		assert.Equal(t, "INFO", messageMap["level"])
		assert.Equal(t, "some data", messageMap["data"])
		assert.NotContains(t, messageMap, "timestamp") // Vector metadata excluded
	})

	t.Run("excludes Vector metadata fields from fallback", func(t *testing.T) {
		record := map[string]any{
			"timestamp":        "2024-01-01T12:00:00Z",
			"cluster_id":       "cluster-1",
			"namespace":        "default",
			"application":      "app",
			"pod_name":         "pod-1",
			"ingest_timestamp": "2024-01-01T12:00:00Z",
			"custom_field":     "should be included",
		}

		event := ConvertLogRecordToEvent(record, logger)

		require.NotNil(t, event)
		messageMap, ok := event.Message.(map[string]any)
		require.True(t, ok)

		// Only custom_field should remain
		assert.Equal(t, "should be included", messageMap["custom_field"])
		assert.NotContains(t, messageMap, "cluster_id")
		assert.NotContains(t, messageMap, "namespace")
		assert.NotContains(t, messageMap, "application")
	})

	t.Run("returns nil for non-map record", func(t *testing.T) {
		record := "not a map"

		event := ConvertLogRecordToEvent(record, logger)

		assert.Nil(t, event)
	})

	t.Run("preserves JSON objects in message field", func(t *testing.T) {
		record := map[string]any{
			"timestamp": "2024-01-01T12:00:00Z",
			"message": map[string]any{
				"level":   "ERROR",
				"details": "something went wrong",
			},
		}

		event := ConvertLogRecordToEvent(record, logger)

		require.NotNil(t, event)
		messageMap, ok := event.Message.(map[string]any)
		require.True(t, ok)
		assert.Equal(t, "ERROR", messageMap["level"])
		assert.Equal(t, "something went wrong", messageMap["details"])
	})
}

func TestProcessJSONFile(t *testing.T) {
	logger := getTestLogger()

	t.Run("processes NDJSON format", func(t *testing.T) {
		ndjson := `{"timestamp":"2024-01-01T12:00:00Z","message":"first log"}
{"timestamp":"2024-01-01T12:01:00Z","message":"second log"}
{"timestamp":"2024-01-01T12:02:00Z","message":"third log"}`

		events, err := ProcessJSONFile([]byte(ndjson), logger)

		require.NoError(t, err)
		assert.Len(t, events, 3)
		assert.Equal(t, "first log", events[0].Message)
		assert.Equal(t, "second log", events[1].Message)
		assert.Equal(t, "third log", events[2].Message)
	})

	t.Run("processes JSON array format as fallback", func(t *testing.T) {
		// Compact JSON array on single line to trigger fallback (all lines fail except array)
		jsonArray := `[{"timestamp":"2024-01-01T12:00:00Z","message":"first log"},{"timestamp":"2024-01-01T12:01:00Z","message":"second log"}]`

		events, err := ProcessJSONFile([]byte(jsonArray), logger)

		require.NoError(t, err)
		assert.Len(t, events, 2)
		assert.Equal(t, "first log", events[0].Message)
		assert.Equal(t, "second log", events[1].Message)
	})

	t.Run("processes single JSON object as fallback", func(t *testing.T) {
		singleObject := `{"timestamp":"2024-01-01T12:00:00Z","message":"single log"}`

		events, err := ProcessJSONFile([]byte(singleObject), logger)

		require.NoError(t, err)
		assert.Len(t, events, 1)
		assert.Equal(t, "single log", events[0].Message)
	})

	t.Run("handles NDJSON with empty lines", func(t *testing.T) {
		ndjson := `{"timestamp":"2024-01-01T12:00:00Z","message":"first log"}

{"timestamp":"2024-01-01T12:01:00Z","message":"second log"}

`

		events, err := ProcessJSONFile([]byte(ndjson), logger)

		require.NoError(t, err)
		assert.Len(t, events, 2) // Empty lines should be skipped
		assert.Equal(t, "first log", events[0].Message)
		assert.Equal(t, "second log", events[1].Message)
	})

	t.Run("handles structured log messages", func(t *testing.T) {
		ndjson := `{"timestamp":"2024-01-01T12:00:00Z","message":{"level":"ERROR","msg":"error occurred"}}`

		events, err := ProcessJSONFile([]byte(ndjson), logger)

		require.NoError(t, err)
		assert.Len(t, events, 1)
		messageMap, ok := events[0].Message.(map[string]any)
		require.True(t, ok)
		assert.Equal(t, "ERROR", messageMap["level"])
		assert.Equal(t, "error occurred", messageMap["msg"])
	})

	t.Run("skips invalid JSON lines in NDJSON", func(t *testing.T) {
		ndjson := `{"timestamp":"2024-01-01T12:00:00Z","message":"valid log"}
invalid json line
{"timestamp":"2024-01-01T12:01:00Z","message":"another valid log"}`

		events, err := ProcessJSONFile([]byte(ndjson), logger)

		require.NoError(t, err)
		assert.Len(t, events, 2) // Invalid line skipped
		assert.Equal(t, "valid log", events[0].Message)
		assert.Equal(t, "another valid log", events[1].Message)
	})

	t.Run("handles empty content", func(t *testing.T) {
		events, err := ProcessJSONFile([]byte(""), logger)

		require.NoError(t, err)
		assert.Len(t, events, 0)
	})

	t.Run("returns error for completely invalid JSON", func(t *testing.T) {
		invalidJSON := `this is not json at all`

		events, err := ProcessJSONFile([]byte(invalidJSON), logger)

		require.Error(t, err)
		assert.Nil(t, events)
	})

	t.Run("filters out records without message or valid content", func(t *testing.T) {
		ndjson := `{"timestamp":"2024-01-01T12:00:00Z","message":"valid log"}
{"timestamp":"2024-01-01T12:01:00Z"}
{"message":"log without timestamp"}`

		events, err := ProcessJSONFile([]byte(ndjson), logger)

		require.NoError(t, err)
		// All records should be processed, even if missing some fields
		// ConvertLogRecordToEvent handles the missing fields
		assert.Greater(t, len(events), 0)
	})

	t.Run("handles large NDJSON files", func(t *testing.T) {
		// Generate 1000 log records
		var ndjson string
		for i := 0; i < 1000; i++ {
			ndjson += fmt.Sprintf(`{"timestamp":"2024-01-01T12:00:00Z","message":"log entry %d"}`, i) + "\n"
		}

		events, err := ProcessJSONFile([]byte(ndjson), logger)

		require.NoError(t, err)
		assert.Len(t, events, 1000)
	})

	t.Run("preserves all non-Vector metadata fields", func(t *testing.T) {
		ndjson := `{"timestamp":"2024-01-01T12:00:00Z","custom_field":"value","another_field":123}`

		events, err := ProcessJSONFile([]byte(ndjson), logger)

		require.NoError(t, err)
		assert.Len(t, events, 1)
		messageMap, ok := events[0].Message.(map[string]any)
		require.True(t, ok)
		assert.Equal(t, "value", messageMap["custom_field"])
		assert.Equal(t, float64(123), messageMap["another_field"])
	})
}

func TestProcessTimestampLikeVector(t *testing.T) {
	logger := getTestLogger()

	t.Run("parses RFC3339 string timestamp", func(t *testing.T) {
		ts := models.ProcessTimestampLikeVector("2024-01-01T12:00:00Z", logger)
		assert.Greater(t, ts, int64(0))
		// 2024-01-01 12:00:00 UTC = 1704110400 seconds = 1704110400000 milliseconds
		assert.Equal(t, int64(1704110400000), ts)
	})

	t.Run("parses RFC3339 with timezone offset", func(t *testing.T) {
		ts := models.ProcessTimestampLikeVector("2024-01-01T12:00:00-05:00", logger)
		assert.Greater(t, ts, int64(0))
		// Should be 5 hours later in milliseconds
		assert.Equal(t, int64(1704128400000), ts)
	})

	t.Run("parses numeric timestamp in seconds", func(t *testing.T) {
		ts := models.ProcessTimestampLikeVector(float64(1704110400), logger)
		assert.Equal(t, int64(1704110400000), ts) // Converted to milliseconds
	})

	t.Run("parses numeric timestamp in milliseconds", func(t *testing.T) {
		ts := models.ProcessTimestampLikeVector(float64(1704110400000), logger)
		assert.Equal(t, int64(1704110400000), ts)
	})

	t.Run("parses integer timestamp in seconds", func(t *testing.T) {
		ts := models.ProcessTimestampLikeVector(int64(1704110400), logger)
		assert.Equal(t, int64(1704110400000), ts)
	})

	t.Run("returns current time for invalid timestamp format", func(t *testing.T) {
		ts := models.ProcessTimestampLikeVector("invalid-timestamp", logger)
		// Should return current time as fallback, not 0
		assert.Greater(t, ts, int64(0))
		assert.Greater(t, ts, int64(1704110400000)) // After 2024-01-01
	})

	t.Run("returns current time for nil timestamp", func(t *testing.T) {
		ts := models.ProcessTimestampLikeVector(nil, logger)
		// Should return current time as fallback, not 0
		assert.Greater(t, ts, int64(0))
		assert.Greater(t, ts, int64(1704110400000)) // After 2024-01-01
	})

	t.Run("handles very large timestamps", func(t *testing.T) {
		// Year 2100 timestamp
		ts := models.ProcessTimestampLikeVector(float64(4102444800000), logger)
		assert.Equal(t, int64(4102444800000), ts)
	})

	t.Run("handles edge case: timestamp boundary between seconds and milliseconds", func(t *testing.T) {
		// 999999999999 is just under the seconds/milliseconds threshold (< 1000000000000)
		// so it's treated as seconds and multiplied by 1000
		ts := models.ProcessTimestampLikeVector(float64(999999999999), logger)
		assert.Equal(t, int64(999999999999000), ts) // Converted to milliseconds

		// 1000000000000 equals the threshold but condition uses >, not >=
		// so it's still treated as seconds
		ts = models.ProcessTimestampLikeVector(float64(1000000000000), logger)
		assert.Equal(t, int64(1000000000000000), ts) // Converted to milliseconds

		// 1000000000001 is above the threshold
		ts = models.ProcessTimestampLikeVector(float64(1000000000001), logger)
		assert.Equal(t, int64(1000000000001), ts) // Kept as milliseconds
	})
}

func TestTruncateString(t *testing.T) {
	t.Run("truncates string exceeding max length", func(t *testing.T) {
		input := "this is a very long string that should be truncated"
		result := truncateString(input, 20)
		// Implementation appends "..." after truncation, so result is maxLen + 3
		assert.Equal(t, "this is a very long ...", result)
		assert.Len(t, result, 23) // 20 + 3 for "..."
	})

	t.Run("does not truncate string within max length", func(t *testing.T) {
		input := "short string"
		result := truncateString(input, 20)
		assert.Equal(t, "short string", result)
	})

	t.Run("handles empty string", func(t *testing.T) {
		result := truncateString("", 10)
		assert.Equal(t, "", result)
	})

	t.Run("handles max length shorter than ellipsis", func(t *testing.T) {
		input := "test"
		result := truncateString(input, 2)
		// Implementation doesn't account for ellipsis length, so result is longer than maxLen
		assert.Equal(t, "te...", result)
	})
}

func TestGetKeys(t *testing.T) {
	t.Run("returns keys from map", func(t *testing.T) {
		input := map[string]any{
			"key1": "value1",
			"key2": 123,
			"key3": true,
		}
		keys := getKeys(input)
		assert.Len(t, keys, 3)
		assert.Contains(t, keys, "key1")
		assert.Contains(t, keys, "key2")
		assert.Contains(t, keys, "key3")
	})

	t.Run("returns empty slice for empty map", func(t *testing.T) {
		input := map[string]any{}
		keys := getKeys(input)
		assert.Len(t, keys, 0)
	})

	t.Run("returns empty slice for nil map", func(t *testing.T) {
		keys := getKeys(nil)
		assert.Len(t, keys, 0)
	})
}
