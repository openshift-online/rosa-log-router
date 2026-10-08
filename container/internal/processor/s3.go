package processor

import (
	"bufio"
	"bytes"
	"compress/gzip"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"log/slog"
	"strings"
	"time"

	"github.com/aws/aws-sdk-go-v2/service/s3"
	"github.com/openshift/rosa-log-router/internal/models"
)

// maxReadBytes removed - now passed as parameter to ProcessLogFile
// to use the dynamically configured limit based on Lambda memory

// ExtractTenantInfoFromKey extracts tenant information from S3 object key path
// Expected format (from Vector): cluster_id/namespace/application/pod_name/timestamp-uuid.json.gz
func ExtractTenantInfoFromKey(objectKey string, logger *slog.Logger) (*models.TenantInfo, error) {
	pathParts := strings.Split(objectKey, "/")

	if len(pathParts) < 5 {
		return nil, models.NewInvalidS3NotificationError(
			fmt.Sprintf("invalid object key format. Expected at least 5 path segments, got %d: %s", len(pathParts), objectKey))
	}

	// Validate that required path segments are not empty (handles double slashes in paths)
	requiredSegments := []struct {
		name  string
		index int
	}{
		{"cluster_id", 0},
		{"namespace", 1},
		{"application", 2},
		{"pod_name", 3},
	}

	for _, segment := range requiredSegments {
		if segment.index >= len(pathParts) || strings.TrimSpace(pathParts[segment.index]) == "" {
			return nil, models.NewInvalidS3NotificationError(
				fmt.Sprintf("invalid object key format. %s (segment %d) cannot be empty: %s",
					segment.name, segment.index, objectKey))
		}
	}

	// Vector schema: cluster_id/namespace/application/pod_name/file.gz
	// Use namespace as tenant_id for DynamoDB delivery configuration lookup
	tenantInfo := &models.TenantInfo{
		ClusterID:   pathParts[0], // Management cluster ID from Vector CLUSTER_ID env var
		Namespace:   pathParts[1], // Kubernetes pod namespace from Vector
		TenantID:    pathParts[1], // Use namespace as tenant_id for DynamoDB lookup
		Application: pathParts[2], // Application name from pod labels
		PodName:     pathParts[3], // Kubernetes pod name
		Environment: "production",
	}

	// Extract environment from cluster_id if it contains it
	if strings.Contains(tenantInfo.ClusterID, "-") {
		envPrefix := strings.Split(tenantInfo.ClusterID, "-")[0]
		envMap := map[string]string{
			"prod": "production",
			"stg":  "staging",
			"dev":  "development",
		}
		if env, ok := envMap[envPrefix]; ok {
			tenantInfo.Environment = env
		}
	}

	// Log extracted values to help debug any schema mismatches
	logger.Info("extracted tenant info from S3 key",
		"object_key", objectKey,
		"cluster_id", tenantInfo.ClusterID,
		"namespace", tenantInfo.Namespace,
		"tenant_id", tenantInfo.TenantID,
		"application", tenantInfo.Application,
		"pod_name", tenantInfo.PodName)

	return tenantInfo, nil
}

// GetS3Object retrieves a file from S3 and it's upload time
func GetS3Object(ctx context.Context, s3Client *s3.Client, bucketName, objectKey string, logger *slog.Logger) (io.ReadCloser, int64, error) {
	// Download from S3
	result, err := s3Client.GetObject(ctx, &s3.GetObjectInput{
		Bucket: &bucketName,
		Key:    &objectKey,
	})
	if err != nil {
		return nil, 0, fmt.Errorf("failed to download S3 object s3://%s/%s: %w", bucketName, objectKey, err)
	}

	// Safely handle nil LastModified (shouldn't happen, but prevents panic)
	var uploadTime int64
	if result.LastModified != nil {
		uploadTime = result.LastModified.UnixMilli()
	} else {
		uploadTime = time.Now().UnixMilli()
		logger.Warn("S3 GetObject returned nil LastModified, using current time")
	}

	return result.Body, uploadTime, nil
}

// ProcessLogFile extracts the log events from a file
// maxBytes limits both raw and decompressed content to prevent OOM
// Accepts []byte directly to avoid unnecessary copies (caller already has the data in memory)
func ProcessLogFile(ctx context.Context, filename string, content []byte, logger *slog.Logger, maxBytes int64) ([]*models.LogEvent, error) {
	// Verify size constraint (caller should have already checked, but double-check)
	if int64(len(content)) > maxBytes {
		return nil, models.NewNonRecoverableError(
			fmt.Sprintf("S3 object exceeds maximum allowed size of %d bytes", maxBytes))
	}

	fileContent := content

	// Decompress if gzipped
	if strings.HasSuffix(filename, ".gz") {
		gzReader, err := gzip.NewReader(bytes.NewReader(fileContent))
		if err != nil {
			return nil, fmt.Errorf("failed to create gzip reader: %w", err)
		}
		defer gzReader.Close()

		decompressed, err := io.ReadAll(io.LimitReader(gzReader, maxBytes+1))
		if err != nil {
			return nil, fmt.Errorf("failed to decompress gzip content: %w", err)
		}
		if int64(len(decompressed)) > maxBytes {
			return nil, models.NewNonRecoverableError(
				fmt.Sprintf("decompressed size exceeds maximum allowed size of %d bytes", maxBytes))
		}

		fileContent = decompressed
		logger.Info("decompressed file",
			"size_bytes_decompressed", len(fileContent))
	}

	logEvents, err := ProcessJSON(fileContent, logger)
	if err != nil {
		return nil, err
	}

	return logEvents, nil
}

// vectorLogRecord is a minimal struct for fast-path JSON parsing
// Most Vector NDJSON records contain timestamp + message, so we parse directly to struct
// to avoid allocating full map[string]interface{} (~1-2 KB per record)
// Memory savings: ~30-50 MiB for typical 82K record batch
type vectorLogRecord struct {
	Timestamp interface{} `json:"timestamp"`
	Message   interface{} `json:"message"`
}

// ProcessJSON processes JSON content and extracts log events
// Prioritizes Vector's NDJSON (line-delimited JSON) format with JSON array fallback
// Uses streaming bufio.Scanner to avoid allocating string(fileContent) and strings.Split() arrays
func ProcessJSON(fileContent []byte, logger *slog.Logger) ([]*models.LogEvent, error) {
	var logEvents []*models.LogEvent
	lineParseSuccess := 0
	lineParseErrors := 0
	lineNum := 0

	// Use bufio.Scanner for streaming line-by-line parsing
	// Memory optimization: Avoids string(fileContent) + strings.Split() allocations
	scanner := bufio.NewScanner(bytes.NewReader(fileContent))

	// Set scanner buffer to handle lines up to fileContent size (bounded by MaxReadBytes)
	// Start with 64 KB initial buffer, grow up to len(fileContent) as needed
	// This allows processing of large JSON objects (up to 66 MiB) without artificial limits
	maxLineSize := len(fileContent)
	if maxLineSize < 64*1024 {
		maxLineSize = 64 * 1024 // Minimum 64 KB
	}
	scanner.Buffer(make([]byte, 0, 64*1024), maxLineSize)

	// Try line-delimited JSON first (Vector NDJSON format)
	for scanner.Scan() {
		line := scanner.Bytes() // Returns []byte directly, no string conversion!

		// Skip empty lines (trim and check)
		if len(bytes.TrimSpace(line)) == 0 {
			lineNum++
			continue
		}

		// Fast path: Parse to minimal struct (avoids map allocation for ~95% of records)
		// Most Vector records have timestamp + message, so this saves ~1.5 KB per record
		var fastRecord vectorLogRecord
		fastErr := json.Unmarshal(line, &fastRecord)

		// Fast path succeeded and message exists - create event directly (common case ~95%)
		if fastErr == nil && fastRecord.Message != nil {
			event := &models.LogEvent{
				Timestamp: models.ProcessTimestampLikeVector(fastRecord.Timestamp, logger),
				Message:   fastRecord.Message,
			}
			logEvents = append(logEvents, event)
			lineParseSuccess++

			// Log first record keys for debugging (parse to map just for logging)
			if lineNum == 0 {
				var debugRecord map[string]interface{}
				if err := json.Unmarshal(line, &debugRecord); err == nil {
					logger.Info("first log record", "keys", getKeys(debugRecord))
				}
			}

			lineNum++
			continue
		}

		// Slow path: fast unmarshal failed (JSON array) OR no message field
		// Parse to interface{} to handle arrays and objects without message
		var parsedData interface{}
		if err := json.Unmarshal(line, &parsedData); err != nil {
			lineParseErrors++
			if lineNum < 3 { // Log first few parse errors
				logger.Warn("line JSON parse error",
					"line_num", lineNum,
					"error", err,
					"content_preview", truncateString(string(line), 100))
			}
			lineNum++
			continue
		}

		lineParseSuccess++

		// Handle if the line is a JSON array
		if arr, ok := parsedData.([]interface{}); ok {
			logger.Info("line is JSON array", "line_num", lineNum, "items", len(arr))
			for idx, logRecord := range arr {
				if idx == 0 && lineNum == 0 {
					if record, ok := logRecord.(map[string]interface{}); ok {
						logger.Info("first log record", "keys", getKeys(record))
					}
				}
				event := ConvertLogRecordToEvent(logRecord, logger)
				if event != nil {
					logEvents = append(logEvents, event)
				}
			}
		} else {
			// Single log record without message field
			if lineNum == 0 {
				if record, ok := parsedData.(map[string]interface{}); ok {
					logger.Info("first log record", "keys", getKeys(record))
				}
			}
			event := ConvertLogRecordToEvent(parsedData, logger)
			if event != nil {
				logEvents = append(logEvents, event)
			}
		}

		lineNum++
	}

	scanErr := scanner.Err()

	// Track if we hit buffer size limit (need fallback for oversized lines)
	hitSizeLimit := false
	if scanErr != nil {
		if scanErr == bufio.ErrTooLong {
			logger.Warn("scanner hit line size limit, will attempt fallback parsing",
				"max_line_size", maxLineSize)
			hitSizeLimit = true
			lineParseErrors = 1 // Mark that errors occurred
		} else {
			return nil, fmt.Errorf("error reading JSON content: %w", scanErr)
		}
	}

	logger.Info("line parsing results",
		"successful", lineParseSuccess,
		"errors", lineParseErrors,
		"total_lines", lineNum)

	// Try fallback parsing ONLY when:
	// 1. Scanner hit size limit (ErrTooLong) - oversized lines may contain valid data
	// 2. No events found at all (len(logEvents) == 0) - might be array/object format
	//
	// Do NOT run fallback for regular invalid JSON lines (they can be safely skipped)
	if hitSizeLimit || (len(logEvents) == 0 && lineParseErrors > 0) {
		reason := "no events found"
		if hitSizeLimit {
			reason = "scanner size limit exceeded"
		}
		logger.Info("attempting fallback JSON parsing",
			"reason", reason,
			"prior_events", len(logEvents),
			"errors", lineParseErrors)

		var data interface{}
		err := json.Unmarshal(fileContent, &data)
		if err != nil {
			// Fallback failed
			if len(logEvents) > 0 {
				// Return partial success WITH error (caller knows data loss occurred)
				return logEvents, fmt.Errorf("partial parse: %d events succeeded, %d lines failed, fallback unsuccessful: %w",
					len(logEvents), lineParseErrors, err)
			}
			// Total failure
			return nil, fmt.Errorf("all parsing methods failed: %w", err)
		}

		// Fallback succeeded - add newly parsed events to existing ones
		if arr, ok := data.([]interface{}); ok {
			logger.Info("fallback parsed as JSON array", "items", len(arr))
			for _, logRecord := range arr {
				event := ConvertLogRecordToEvent(logRecord, logger)
				if event != nil {
					logEvents = append(logEvents, event)
				}
			}
		} else {
			// Single JSON object
			logger.Info("fallback parsed as single JSON object")
			event := ConvertLogRecordToEvent(data, logger)
			if event != nil {
				logEvents = append(logEvents, event)
			}
		}
	}

	logger.Info("processed log events from JSON file", "event_count", len(logEvents))
	return logEvents, nil
}

// ConvertLogRecordToEvent converts log record to CloudWatch Logs event format
func ConvertLogRecordToEvent(logRecord interface{}, logger *slog.Logger) *models.LogEvent {
	record, ok := logRecord.(map[string]interface{})
	if !ok {
		logger.Warn("log record is not a map", "type", fmt.Sprintf("%T", logRecord))
		return nil
	}

	// Use the actual log timestamp for CloudWatch delivery
	var timestampMS int64
	if ts, ok := record["timestamp"]; ok {
		timestampMS = models.ProcessTimestampLikeVector(ts, logger)
	} else {
		timestampMS = time.Now().UnixMilli()
	}

	// Extract message from the structured log record
	var message interface{}
	if msg, ok := record["message"]; ok {
		message = msg
	} else {
		// Fallback: if no message field, use the entire record (excluding Vector metadata)
		cleanRecord := make(map[string]interface{})
		for k, v := range record {
			if !models.VectorMetadataFields[k] {
				cleanRecord[k] = v
			}
		}
		message = cleanRecord
	}

	return &models.LogEvent{
		Timestamp: timestampMS,
		Message:   message,
	}
}

// Helper functions
func truncateString(s string, maxLen int) string {
	if len(s) <= maxLen {
		return s
	}
	return s[:maxLen] + "..."
}

func getKeys(m map[string]interface{}) []string {
	keys := make([]string, 0, len(m))
	for k := range m {
		keys = append(keys, k)
	}
	return keys
}
