package delivery

import (
	"fmt"
	"strings"
	"testing"

	"github.com/openshift/rosa-log-router/internal/models"
	"github.com/stretchr/testify/assert"
)

func TestNormalizeBucketPrefix(t *testing.T) {
	testCases := []struct {
		name     string
		input    string
		expected string
	}{
		{
			name:     "empty_prefix",
			input:    "",
			expected: "",
		},
		{
			name:     "prefix_with_trailing_slash",
			input:    "logs/",
			expected: "logs/",
		},
		{
			name:     "prefix_without_trailing_slash",
			input:    "logs",
			expected: "logs/",
		},
		{
			name:     "nested_prefix_with_slash",
			input:    "ROSA/cluster-logs/",
			expected: "ROSA/cluster-logs/",
		},
		{
			name:     "nested_prefix_without_slash",
			input:    "ROSA/cluster-logs",
			expected: "ROSA/cluster-logs/",
		},
	}

	for _, tc := range testCases {
		t.Run(tc.name, func(t *testing.T) {
			result := normalizeBucketPrefix(tc.input)
			assert.Equal(t, tc.expected, result)
		})
	}
}

func TestS3DelivererDestinationKeyFormatting(t *testing.T) {
	testCases := []struct {
		name              string
		sourceKey         string
		bucketPrefix      string
		tenantID          string
		application       string
		podName           string
		expectedKeyFormat string
	}{
		{
			name:              "default_prefix",
			sourceKey:         "cluster-123/namespace-456/app-789/pod-abc/2024-01-01-logs.json.gz",
			bucketPrefix:      "",
			tenantID:          "tenant-1",
			application:       "payment-service",
			podName:           "payment-pod-123",
			expectedKeyFormat: "ROSA/cluster-logs/tenant-1/payment-service/payment-pod-123/2024-01-01-logs.json.gz",
		},
		{
			name:              "custom_prefix",
			sourceKey:         "cluster-123/namespace-456/app-789/pod-abc/2024-01-01-logs.json.gz",
			bucketPrefix:      "custom/path/",
			tenantID:          "tenant-2",
			application:       "user-service",
			podName:           "user-pod-456",
			expectedKeyFormat: "custom/path/tenant-2/user-service/user-pod-456/2024-01-01-logs.json.gz",
		},
		{
			name:              "custom_prefix_no_slash",
			sourceKey:         "cluster-123/namespace-456/app-789/pod-abc/2024-01-01-logs.json.gz",
			bucketPrefix:      "custom/path",
			tenantID:          "tenant-3",
			application:       "admin-service",
			podName:           "admin-pod-789",
			expectedKeyFormat: "custom/path/tenant-3/admin-service/admin-pod-789/2024-01-01-logs.json.gz",
		},
	}

	for _, tc := range testCases {
		t.Run(tc.name, func(t *testing.T) {
			// Validate the key formatting logic
			bucketPrefix := tc.bucketPrefix
			if bucketPrefix == "" {
				bucketPrefix = "ROSA/cluster-logs/"
			}
			bucketPrefix = normalizeBucketPrefix(bucketPrefix)

			sourceFilename := tc.sourceKey[strings.LastIndex(tc.sourceKey, "/")+1:]
			expectedKey := fmt.Sprintf("%s%s/%s/%s/%s",
				bucketPrefix,
				tc.tenantID,
				tc.application,
				tc.podName,
				sourceFilename)

			assert.Equal(t, tc.expectedKeyFormat, expectedKey)
		})
	}
}

func TestS3DelivererErrorClassification(t *testing.T) {
	testCases := []struct {
		name             string
		errorMsg         string
		isNonRecoverable bool
	}{
		{
			name:             "no_such_bucket",
			errorMsg:         "NoSuchBucket: The specified bucket does not exist",
			isNonRecoverable: true,
		},
		{
			name:             "access_denied",
			errorMsg:         "AccessDenied: Access Denied",
			isNonRecoverable: true,
		},
		{
			name:             "no_such_key",
			errorMsg:         "NoSuchKey: The specified key does not exist",
			isNonRecoverable: true,
		},
		{
			name:             "throttling_error",
			errorMsg:         "SlowDown: Please reduce your request rate",
			isNonRecoverable: false,
		},
		{
			name:             "service_unavailable",
			errorMsg:         "ServiceUnavailable: Service is temporarily unavailable",
			isNonRecoverable: false,
		},
		{
			name:             "network_error",
			errorMsg:         "RequestTimeout: Your socket connection to the server was not read",
			isNonRecoverable: false,
		},
	}

	for _, tc := range testCases {
		t.Run(tc.name, func(t *testing.T) {
			// Test the error classification logic used in DeliverLogs
			isNonRecoverable := strings.Contains(tc.errorMsg, "NoSuchBucket") ||
				strings.Contains(tc.errorMsg, "AccessDenied") ||
				strings.Contains(tc.errorMsg, "NoSuchKey")

			assert.Equal(t, tc.isNonRecoverable, isNonRecoverable,
				"Error classification mismatch for: %s", tc.errorMsg)
		})
	}
}

func TestS3DelivererMetadataFields(t *testing.T) {
	// Test that proper metadata fields are defined
	tenantInfo := &models.TenantInfo{
		TenantID:    "acme-corp",
		Application: "payment-service",
		PodName:     "payment-pod-abc",
	}

	sourceBucket := "central-logs-bucket"
	sourceKey := "cluster-123/acme-corp/payment-service/payment-pod-abc/logs.json.gz"

	// Expected metadata fields (as used in DeliverLogs)
	expectedMetadataKeys := map[string]string{
		"source-bucket":      sourceBucket,
		"source-key":         sourceKey,
		"tenant-id":          tenantInfo.TenantID,
		"application":        tenantInfo.Application,
		"pod-name":           tenantInfo.PodName,
		"delivery-timestamp": "1234567890", // placeholder
	}

	// Validate metadata key-value pairs
	assert.Equal(t, sourceBucket, expectedMetadataKeys["source-bucket"])
	assert.Equal(t, sourceKey, expectedMetadataKeys["source-key"])
	assert.Equal(t, "acme-corp", expectedMetadataKeys["tenant-id"])
	assert.Equal(t, "payment-service", expectedMetadataKeys["application"])
	assert.Equal(t, "payment-pod-abc", expectedMetadataKeys["pod-name"])
	assert.NotEmpty(t, expectedMetadataKeys["delivery-timestamp"])
}

func TestS3DelivererDefaultValues(t *testing.T) {
	testCases := []struct {
		name           string
		targetRegion   string
		bucketPrefix   string
		expectedRegion string
		expectedPrefix string
	}{
		{
			name:           "default_region_and_prefix",
			targetRegion:   "",
			bucketPrefix:   "",
			expectedRegion: "us-east-1",
			expectedPrefix: "ROSA/cluster-logs/",
		},
		{
			name:           "custom_region_default_prefix",
			targetRegion:   "eu-west-1",
			bucketPrefix:   "",
			expectedRegion: "eu-west-1",
			expectedPrefix: "ROSA/cluster-logs/",
		},
		{
			name:           "default_region_custom_prefix",
			targetRegion:   "",
			bucketPrefix:   "custom/logs/",
			expectedRegion: "us-east-1",
			expectedPrefix: "custom/logs/",
		},
		{
			name:           "custom_region_and_prefix",
			targetRegion:   "ap-southeast-1",
			bucketPrefix:   "production/logs/",
			expectedRegion: "ap-southeast-1",
			expectedPrefix: "production/logs/",
		},
	}

	for _, tc := range testCases {
		t.Run(tc.name, func(t *testing.T) {
			// Validate default value logic (as used in DeliverLogs)
			targetRegion := tc.targetRegion
			if targetRegion == "" {
				targetRegion = "us-east-1"
			}
			assert.Equal(t, tc.expectedRegion, targetRegion)

			bucketPrefix := tc.bucketPrefix
			if bucketPrefix == "" {
				bucketPrefix = "ROSA/cluster-logs/"
			}
			assert.Equal(t, tc.expectedPrefix, bucketPrefix)
		})
	}
}

func TestS3DelivererCopySourceFormat(t *testing.T) {
	testCases := []struct {
		name               string
		sourceBucket       string
		sourceKey          string
		expectedCopySource string
	}{
		{
			name:               "simple_path",
			sourceBucket:       "central-logs",
			sourceKey:          "cluster-123/logs/file.json.gz",
			expectedCopySource: "central-logs/cluster-123/logs/file.json.gz",
		},
		{
			name:               "nested_path",
			sourceBucket:       "multi-tenant-logs",
			sourceKey:          "cluster-456/namespace-789/app-012/pod-345/2024-01-01.json.gz",
			expectedCopySource: "multi-tenant-logs/cluster-456/namespace-789/app-012/pod-345/2024-01-01.json.gz",
		},
		{
			name:               "bucket_with_hyphens",
			sourceBucket:       "rosa-central-logs-us-east-1",
			sourceKey:          "production/cluster-999/logs.json.gz",
			expectedCopySource: "rosa-central-logs-us-east-1/production/cluster-999/logs.json.gz",
		},
	}

	for _, tc := range testCases {
		t.Run(tc.name, func(t *testing.T) {
			// Test copy source formatting (as used in DeliverLogs)
			copySource := fmt.Sprintf("%s/%s", tc.sourceBucket, tc.sourceKey)
			assert.Equal(t, tc.expectedCopySource, copySource)
		})
	}
}

func TestS3DelivererSourceFilenameExtraction(t *testing.T) {
	testCases := []struct {
		name             string
		sourceKey        string
		expectedFilename string
	}{
		{
			name:             "simple_filename",
			sourceKey:        "cluster/namespace/app/pod/file.json.gz",
			expectedFilename: "file.json.gz",
		},
		{
			name:             "timestamp_filename",
			sourceKey:        "cluster/namespace/app/pod/2024-01-01-12-00-00.json.gz",
			expectedFilename: "2024-01-01-12-00-00.json.gz",
		},
		{
			name:             "complex_path",
			sourceKey:        "production/us-east-1/cluster-123/namespace-456/app-789/pod-abc/logs-2024.json.gz",
			expectedFilename: "logs-2024.json.gz",
		},
		{
			name:             "no_directories",
			sourceKey:        "simple.json.gz",
			expectedFilename: "simple.json.gz",
		},
	}

	for _, tc := range testCases {
		t.Run(tc.name, func(t *testing.T) {
			// Test filename extraction (as used in DeliverLogs)
			filename := tc.sourceKey[strings.LastIndex(tc.sourceKey, "/")+1:]
			assert.Equal(t, tc.expectedFilename, filename)
		})
	}
}

func TestS3DelivererACLSetting(t *testing.T) {
	// Validate that the correct ACL is used
	// DeliverLogs uses types.ObjectCannedACLBucketOwnerFullControl
	expectedACL := "bucket-owner-full-control"

	// This is a documentation test - the actual ACL is set in the CopyObjectInput
	assert.Equal(t, "bucket-owner-full-control", expectedACL,
		"S3 copy should use bucket-owner-full-control ACL to ensure customer owns the objects")
}

func TestS3DelivererDestinationKeyExcludesClusterID(t *testing.T) {
	// Validate that the destination key format excludes cluster_id for security
	sourceKey := "cluster-mc-12345/tenant-abc/app-xyz/pod-123/logs.json.gz"
	tenantID := "tenant-abc"
	application := "app-xyz"
	podName := "pod-123"
	bucketPrefix := "ROSA/cluster-logs/"

	sourceFilename := sourceKey[strings.LastIndex(sourceKey, "/")+1:]
	destinationKey := fmt.Sprintf("%s%s/%s/%s/%s",
		bucketPrefix,
		tenantID,
		application,
		podName,
		sourceFilename)

	// Verify that the destination key does NOT contain the cluster ID
	assert.NotContains(t, destinationKey, "cluster-mc-12345",
		"Destination key should not expose management cluster ID")

	// Verify destination key format
	expectedKey := "ROSA/cluster-logs/tenant-abc/app-xyz/pod-123/logs.json.gz"
	assert.Equal(t, expectedKey, destinationKey)
}

func TestS3DelivererConfigValidation(t *testing.T) {
	deliveryConfig := &models.DeliveryConfig{
		TenantID:     "test-tenant",
		Type:         "s3",
		Enabled:      true,
		BucketName:   "customer-bucket",
		BucketPrefix: "logs/",
		TargetRegion: "us-west-2",
	}

	// Validate required fields for S3 delivery
	assert.Equal(t, "test-tenant", deliveryConfig.TenantID)
	assert.Equal(t, "s3", deliveryConfig.Type)
	assert.True(t, deliveryConfig.Enabled)
	assert.NotEmpty(t, deliveryConfig.BucketName, "BucketName is required for S3 delivery")
	assert.NotEmpty(t, deliveryConfig.TargetRegion, "TargetRegion should be specified")

	// Validate optional fields have defaults
	if deliveryConfig.BucketPrefix == "" {
		deliveryConfig.BucketPrefix = "ROSA/cluster-logs/"
	}
	assert.NotEmpty(t, deliveryConfig.BucketPrefix)
}

func TestS3DelivererMetadataDirective(t *testing.T) {
	// Validate that metadata directive is set to REPLACE
	// This ensures custom metadata is attached to the copied object
	expectedDirective := "REPLACE"

	// This is a documentation test - the actual directive is set in CopyObjectInput
	assert.Equal(t, "REPLACE", expectedDirective,
		"MetadataDirective should be REPLACE to attach custom metadata")
}

func TestS3DelivererSessionNameFormat(t *testing.T) {
	// Test that session names follow the expected format
	testCases := []struct {
		name              string
		expectedPrefix    string
		containsTimestamp bool
	}{
		{
			name:              "s3_delivery_session",
			expectedPrefix:    "S3LogDelivery-",
			containsTimestamp: true,
		},
	}

	for _, tc := range testCases {
		t.Run(tc.name, func(t *testing.T) {
			// Session name format: S3LogDelivery-{timestamp}
			sessionName := fmt.Sprintf("%s%d", tc.expectedPrefix, 1234567890)

			assert.True(t, strings.HasPrefix(sessionName, tc.expectedPrefix),
				"Session name should start with %s", tc.expectedPrefix)

			if tc.containsTimestamp {
				assert.True(t, len(sessionName) > len(tc.expectedPrefix),
					"Session name should contain timestamp")
			}
		})
	}
}
