package models

import (
	"log/slog"
	"os"
	"time"
)

// TenantInfo contains information extracted from S3 object key
type TenantInfo struct {
	ClusterID   string `json:"cluster_id"`
	Namespace   string `json:"namespace"`
	TenantID    string `json:"tenant_id"` // Same as namespace for DynamoDB lookup
	Application string `json:"application"`
	PodName     string `json:"pod_name"`
	Environment string `json:"environment"`
}

// DeliveryConfig represents a tenant delivery configuration from DynamoDB
type DeliveryConfig struct {
	TenantID               string   `json:"tenant_id" dynamodbav:"tenant_id"`
	Type                   string   `json:"type" dynamodbav:"type"`
	Enabled                bool     `json:"enabled" dynamodbav:"enabled"`
	TargetRegion           string   `json:"target_region,omitempty" dynamodbav:"target_region,omitempty"`
	DesiredLogs            []string `json:"desired_logs,omitempty" dynamodbav:"desired_logs,omitempty"`
	Groups                 []string `json:"groups,omitempty" dynamodbav:"groups,omitempty"`
	LogDistributionRoleArn string   `json:"log_distribution_role_arn,omitempty" dynamodbav:"log_distribution_role_arn,omitempty"`
	LogGroupName           string   `json:"log_group_name,omitempty" dynamodbav:"log_group_name,omitempty"`
	BucketName             string   `json:"bucket_name,omitempty" dynamodbav:"bucket_name,omitempty"`
	BucketPrefix           string   `json:"bucket_prefix,omitempty" dynamodbav:"bucket_prefix,omitempty"`
}

// LogEvent represents a CloudWatch Logs event
type LogEvent struct {
	Timestamp int64       `json:"timestamp"`
	Message   interface{} `json:"message"` // Can be string or map[string]interface{}
}

// ProcessingMetadata contains SQS message processing metadata
type ProcessingMetadata struct {
	Offset                int       `json:"offset"`
	RetryCount            int       `json:"retry_count"`
	OriginalReceiptHandle string    `json:"original_receipt_handle"`
	RequeuedAt            time.Time `json:"requeued_at,omitempty"`
}

// DeliveryStats tracks delivery success/failure statistics
type DeliveryStats struct {
	SuccessfulDeliveries int `json:"successful_deliveries"`
	FailedDeliveries     int `json:"failed_deliveries"`
	SuccessfulEvents     int `json:"successful_events,omitempty"`
	FailedEvents         int `json:"failed_events,omitempty"`
	TotalProcessed       int `json:"total_processed,omitempty"`
}

// S3EventRecord represents an S3 event record from SNS
type S3EventRecord struct {
	S3 struct {
		Bucket struct {
			Name string `json:"name"`
		} `json:"bucket"`
		Object struct {
			Key string `json:"key"`
		} `json:"object"`
	} `json:"s3"`
}

// S3Event represents an S3 event notification
type S3Event struct {
	Records []S3EventRecord `json:"Records"`
}

// SNSMessage represents an SNS message containing S3 event
type SNSMessage struct {
	Message string `json:"Message"`
}

// VectorMetadataFields are Vector metadata fields that should be excluded when creating fallback messages.
var VectorMetadataFields = map[string]bool{
	"cluster_id":       true,
	"namespace":        true,
	"application":      true,
	"pod_name":         true,
	"ingest_timestamp": true,
	"timestamp":        true,
	"kubernetes":       true,
}

// ApplicationGroups defines application group definitions for filtering.
var ApplicationGroups = map[string][]string{
	"API": {
		"kube-apiserver",
		"openshift-apiserver",
	},
	"Authentication": {
		"oauth-openshift",
		"openshift-oauth-apiserver",
	},
	"Controller Manager": {
		"kube-controller-manager",
		"openshift-controller-manager",
		"openshift-route-controller-manager",
	},
	"Scheduler": {
		"kube-scheduler",
	},
}

// Config represents the application configuration
type Config struct {
	TenantConfigTable             string
	MaxBatchSize                  int
	RetryAttempts                 int
	CentralLogDistributionRoleArn string
	SQSQueueURL                   string
	AWSRegion                     string
	ExecutionMode                 string // lambda, sqs, manual, scan
	SourceBucket                  string // For scan mode
	ScanInterval                  int    // For scan mode
	S3UsePathStyle                bool   // Use path-style S3 URLs (for LocalStack; defaults to false for AWS virtual-hosted style)
	AWSEndpointURL                string // AWS endpoint URL (for LocalStack/testing; empty for real AWS)
}

// DefaultConfig returns a configuration with default values
func DefaultConfig() *Config {
	return &Config{
		TenantConfigTable: "tenant-configurations",
		MaxBatchSize:      1000,
		RetryAttempts:     3,
		AWSRegion:         "us-east-1",
		ScanInterval:      10,
		S3UsePathStyle:    false, // Default to AWS virtual-hosted style
	}
}

// NewDefaultLogger creates a default logger for testing
func NewDefaultLogger() *slog.Logger {
	return slog.New(slog.NewTextHandler(os.Stdout, &slog.HandlerOptions{
		Level: slog.LevelInfo,
	}))
}
