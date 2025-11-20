package processor

import (
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
	return result.Body, result.LastModified.UnixMilli(), nil
}

// ProcessLogFile extracts the log events from a file
func ProcessLogFile(ctx context.Context, filename string, content io.Reader, logger *slog.Logger) ([]*models.LogEvent, error) {
	fileContent, err := io.ReadAll(content)
	if err != nil {
		return nil, fmt.Errorf("failed to read S3 object content: %w", err)
	}

	// Decompress if gzipped
	if strings.HasSuffix(filename, ".gz") {
		gzReader, err := gzip.NewReader(strings.NewReader(string(fileContent)))
		if err != nil {
			return nil, fmt.Errorf("failed to create gzip reader: %w", err)
		}
		defer gzReader.Close()

		decompressed, err := io.ReadAll(gzReader)
		if err != nil {
			return nil, fmt.Errorf("failed to decompress gzip content: %w", err)
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

// ProcessJSON processes JSON content and extracts log events
// Prioritizes Vector's NDJSON (line-delimited JSON) format with JSON array fallback
func ProcessJSON(fileContent []byte, logger *slog.Logger) ([]*models.LogEvent, error) {
	content := string(fileContent)
	lines := strings.Split(strings.TrimSpace(content), "\n")

	logger.Info("processing JSON file", "lines", len(lines))

	var logEvents []*models.LogEvent
	lineParseSuccess := 0
	lineParseErrors := 0

	// Try line-delimited JSON first (Vector NDJSON format)
	for lineNum, line := range lines {
		if strings.TrimSpace(line) == "" {
			continue
		}

		var parsedData interface{}
		err := json.Unmarshal([]byte(line), &parsedData)
		if err != nil {
			lineParseErrors++
			if lineNum < 3 { // Log first few parse errors
				logger.Warn("line JSON parse error",
					"line_num", lineNum,
					"error", err,
					"content_preview", truncateString(line, 100))
			}
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
			// Single log record
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
	}

	logger.Info("line parsing results",
		"successful", lineParseSuccess,
		"errors", lineParseErrors)

	// If no events found via line parsing, try fallback methods
	if len(logEvents) == 0 && lineParseErrors > 0 {
		logger.Info("no events from line parsing, trying fallback JSON parsing")
		var data interface{}
		err := json.Unmarshal(fileContent, &data)
		if err != nil {
			return nil, fmt.Errorf("fallback JSON parsing failed: %w", err)
		}

		if arr, ok := data.([]interface{}); ok {
			logger.Info("parsed as JSON array", "items", len(arr))
			for _, logRecord := range arr {
				event := ConvertLogRecordToEvent(logRecord, logger)
				if event != nil {
					logEvents = append(logEvents, event)
				}
			}
		} else {
			// Single JSON object
			logger.Info("parsed as single JSON object")
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
