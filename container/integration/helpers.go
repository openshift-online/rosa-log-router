//go:build integration
// +build integration

package integration

import (
	"bytes"
	"compress/gzip"
	"context"
	"encoding/json"
	"fmt"
	"os/exec"
	"strings"
	"testing"
	"time"

	"github.com/aws/aws-sdk-go-v2/aws"
	"github.com/aws/aws-sdk-go-v2/config"
	"github.com/aws/aws-sdk-go-v2/service/cloudwatchlogs"
	"github.com/aws/aws-sdk-go-v2/service/s3"
	"github.com/google/uuid"
	"github.com/stretchr/testify/require"
)

const (
	// LocalStack configuration
	LocalStackEndpoint = "http://localhost:4566"
	LocalStackRegion   = "us-east-1"

	// LocalStack multi-account simulation
	CentralAccountID   = "111111111111"
	Customer1AccountID = "222222222222" // ACME Corp - S3 delivery
	Customer2AccountID = "333333333333" // Globex Industries - CloudWatch delivery

	// Default timeout for polling operations
	DefaultTimeout = 30 * time.Second
	PollInterval   = 2 * time.Second
)

// E2ETestHelper provides utilities for end-to-end integration testing
type E2ETestHelper struct {
	ctx          context.Context
	s3Client     *s3.Client
	cwLogsClient *cloudwatchlogs.Client

	// LocalStack-specific
	localstackURL string

	// Terraform outputs (fetched dynamically)
	centralBucket      string
	customer1Bucket    string
	customer2Bucket    string
	customer2LogGroup  string
	apiGatewayEndpoint string
}

// NewE2ETestHelper creates a new test helper with LocalStack-configured AWS clients
func NewE2ETestHelper(t *testing.T) *E2ETestHelper {
	t.Helper()

	ctx := context.Background()

	// Create AWS config for LocalStack with central account credentials
	cfg, err := config.LoadDefaultConfig(ctx,
		config.WithRegion(LocalStackRegion),
		config.WithCredentialsProvider(aws.CredentialsProviderFunc(
			func(ctx context.Context) (aws.Credentials, error) {
				return aws.Credentials{
					AccessKeyID:     CentralAccountID,
					SecretAccessKey: "test",
				}, nil
			},
		)),
		config.WithEndpointResolverWithOptions(
			aws.EndpointResolverWithOptionsFunc(func(service, region string, options ...interface{}) (aws.Endpoint, error) {
				return aws.Endpoint{
					URL:               LocalStackEndpoint,
					HostnameImmutable: true,
				}, nil
			}),
		),
	)
	require.NoError(t, err, "failed to create AWS config for LocalStack")

	// Create S3 client with path-style addressing (required for LocalStack)
	s3Client := s3.NewFromConfig(cfg, func(o *s3.Options) {
		o.UsePathStyle = true
	})

	// Create CloudWatch Logs client for customer account verification
	cwLogsClient := cloudwatchlogs.NewFromConfig(cfg)

	// Fetch terraform outputs
	centralBucket := getTerraformOutput(t, "central_source_bucket")
	customer1Bucket := getTerraformOutput(t, "customer1_bucket")
	customer2Bucket := getTerraformOutput(t, "customer2_bucket")
	customer2LogGroup := getTerraformOutput(t, "customer2_log_group")

	return &E2ETestHelper{
		ctx:               ctx,
		s3Client:          s3Client,
		cwLogsClient:      cwLogsClient,
		localstackURL:     LocalStackEndpoint,
		centralBucket:     centralBucket,
		customer1Bucket:   customer1Bucket,
		customer2Bucket:   customer2Bucket,
		customer2LogGroup: customer2LogGroup,
	}
}

// getTerraformOutput fetches a terraform output value by shelling out to terraform
func getTerraformOutput(t *testing.T, outputName string) string {
	t.Helper()

	cmd := exec.Command("terraform", "output", "-raw", outputName)
	cmd.Dir = "../../terraform/local" // Relative to container/integration directory
	output, err := cmd.CombinedOutput()
	require.NoError(t, err, "failed to get terraform output '%s': %s", outputName, string(output))

	value := strings.TrimSpace(string(output))
	require.NotEmpty(t, value, "terraform output '%s' is empty", outputName)

	t.Logf("Terraform output %s = %s", outputName, value)
	return value
}

// Getter methods for terraform outputs

func (h *E2ETestHelper) CentralBucket() string {
	return h.centralBucket
}

func (h *E2ETestHelper) Customer1Bucket() string {
	return h.customer1Bucket
}

func (h *E2ETestHelper) Customer2Bucket() string {
	return h.customer2Bucket
}

func (h *E2ETestHelper) Customer2LogGroup() string {
	return h.customer2LogGroup
}

// TestLogMessage represents the structure of a test log message
type TestLogMessage struct {
	Text      string `json:"text"`
	TraceID   string `json:"trace_id"`
	RequestID string `json:"request_id"`
	Level     string `json:"level"`
	Service   string `json:"service"`
	Customer  string `json:"customer"`
}

// TestLog represents a complete test log entry
type TestLog struct {
	Timestamp string         `json:"timestamp"`
	Message   TestLogMessage `json:"message"`
}

// GenerateTestLog creates a test log with embedded UUID for verification
// Returns the UUID and the gzipped log data ready for upload
func (h *E2ETestHelper) GenerateTestLog(customerID, service, pod string) (testID string, logData []byte) {
	testID = uuid.New().String()

	testLog := TestLog{
		Timestamp: time.Now().UTC().Format(time.RFC3339),
		Message: TestLogMessage{
			Text:      fmt.Sprintf("E2E test log for %s", service),
			TraceID:   testID,
			RequestID: testID,
			Level:     "INFO",
			Service:   service,
			Customer:  customerID,
		},
	}

	// Marshal to JSON
	jsonData, err := json.Marshal(testLog)
	if err != nil {
		panic(fmt.Sprintf("failed to marshal test log: %v", err))
	}

	// Gzip the JSON
	var buf bytes.Buffer
	gzWriter := gzip.NewWriter(&buf)
	if _, err := gzWriter.Write(jsonData); err != nil {
		panic(fmt.Sprintf("failed to write gzip data: %v", err))
	}
	if err := gzWriter.Close(); err != nil {
		panic(fmt.Sprintf("failed to close gzip writer: %v", err))
	}

	return testID, buf.Bytes()
}

// UploadTestLog uploads test log data to the specified S3 bucket and key
func (h *E2ETestHelper) UploadTestLog(t *testing.T, bucket, key string, data []byte) {
	t.Helper()

	_, err := h.s3Client.PutObject(h.ctx, &s3.PutObjectInput{
		Bucket: aws.String(bucket),
		Key:    aws.String(key),
		Body:   bytes.NewReader(data),
	})
	require.NoError(t, err, "failed to upload test log to S3")

	t.Logf("Uploaded test log to s3://%s/%s", bucket, key)
}

// WaitForS3Delivery polls the destination S3 bucket for a delivered file containing the test UUID
// Returns the delivered file key if found
func (h *E2ETestHelper) WaitForS3Delivery(t *testing.T, accountID, bucket, prefix, testID string, timeout time.Duration) string {
	t.Helper()

	// Create S3 client with customer account credentials for verification
	customerCfg, err := config.LoadDefaultConfig(h.ctx,
		config.WithRegion(LocalStackRegion),
		config.WithCredentialsProvider(aws.CredentialsProviderFunc(
			func(ctx context.Context) (aws.Credentials, error) {
				return aws.Credentials{
					AccessKeyID:     accountID,
					SecretAccessKey: "test",
				}, nil
			},
		)),
		config.WithEndpointResolverWithOptions(
			aws.EndpointResolverWithOptionsFunc(func(service, region string, options ...interface{}) (aws.Endpoint, error) {
				return aws.Endpoint{
					URL:               LocalStackEndpoint,
					HostnameImmutable: true,
				}, nil
			}),
		),
	)
	require.NoError(t, err, "failed to create customer AWS config")

	customerS3 := s3.NewFromConfig(customerCfg, func(o *s3.Options) {
		o.UsePathStyle = true
	})

	deadline := time.Now().Add(timeout)
	for time.Now().Before(deadline) {
		// List objects with the given prefix
		listResp, err := customerS3.ListObjectsV2(h.ctx, &s3.ListObjectsV2Input{
			Bucket: aws.String(bucket),
			Prefix: aws.String(prefix),
		})

		if err == nil && listResp.Contents != nil && len(listResp.Contents) > 0 {
			// Check each file for the test UUID
			for _, obj := range listResp.Contents {
				// Download and check content
				getResp, err := customerS3.GetObject(h.ctx, &s3.GetObjectInput{
					Bucket: aws.String(bucket),
					Key:    obj.Key,
				})

				if err != nil {
					continue
				}

				// Read and decompress
				gzReader, err := gzip.NewReader(getResp.Body)
				if err != nil {
					getResp.Body.Close()
					continue
				}

				var buf bytes.Buffer
				if _, err := buf.ReadFrom(gzReader); err != nil {
					gzReader.Close()
					getResp.Body.Close()
					continue
				}

				gzReader.Close()
				getResp.Body.Close()

				// Check if UUID is in the content
				if strings.Contains(buf.String(), testID) {
					t.Logf("Found delivered file with UUID: s3://%s/%s", bucket, *obj.Key)
					return *obj.Key
				}
			}
		}

		time.Sleep(PollInterval)
	}

	require.Fail(t, "timeout waiting for S3 delivery", "UUID %s not found in bucket %s after %v", testID, bucket, timeout)
	return ""
}

// WaitForCloudWatchDelivery polls CloudWatch Logs for log events containing the test UUID
func (h *E2ETestHelper) WaitForCloudWatchDelivery(t *testing.T, accountID, logGroup, logStream, testID string, timeout time.Duration) {
	t.Helper()

	// Create CloudWatch Logs client with customer account credentials
	customerCfg, err := config.LoadDefaultConfig(h.ctx,
		config.WithRegion(LocalStackRegion),
		config.WithCredentialsProvider(aws.CredentialsProviderFunc(
			func(ctx context.Context) (aws.Credentials, error) {
				return aws.Credentials{
					AccessKeyID:     accountID,
					SecretAccessKey: "test",
				}, nil
			},
		)),
		config.WithEndpointResolverWithOptions(
			aws.EndpointResolverWithOptionsFunc(func(service, region string, options ...interface{}) (aws.Endpoint, error) {
				return aws.Endpoint{
					URL:               LocalStackEndpoint,
					HostnameImmutable: true,
				}, nil
			}),
		),
	)
	require.NoError(t, err, "failed to create customer AWS config")

	customerCWLogs := cloudwatchlogs.NewFromConfig(customerCfg)

	deadline := time.Now().Add(timeout)
	for time.Now().Before(deadline) {
		// Try to get log events from the stream
		resp, err := customerCWLogs.GetLogEvents(h.ctx, &cloudwatchlogs.GetLogEventsInput{
			LogGroupName:  aws.String(logGroup),
			LogStreamName: aws.String(logStream),
			Limit:         aws.Int32(100),
		})

		if err == nil && resp.Events != nil {
			// Check each event for the test UUID
			for _, event := range resp.Events {
				if event.Message != nil && strings.Contains(*event.Message, testID) {
					t.Logf("Found CloudWatch log event with UUID in log group %s, stream %s", logGroup, logStream)
					return
				}
			}
		}

		time.Sleep(PollInterval)
	}

	require.Fail(t, "timeout waiting for CloudWatch delivery", "UUID %s not found in log group %s, stream %s after %v", testID, logGroup, logStream, timeout)
}

// APIGatewayEndpoint retrieves the API Gateway endpoint from Terraform outputs
func (h *E2ETestHelper) APIGatewayEndpoint() string {
	if h.apiGatewayEndpoint == "" {
		output := h.terraformOutput("api_gateway_endpoint")
		h.apiGatewayEndpoint = strings.TrimSpace(output)
	}
	return h.apiGatewayEndpoint
}

// APIPSK retrieves the API PSK from Terraform outputs
func (h *E2ETestHelper) APIPSK() string {
	// Use the default test PSK
	return "test-psk-localstack-do-not-use-in-production"
}

// Cleanup performs any necessary cleanup after tests (currently a no-op but provided for future use)
func (h *E2ETestHelper) Cleanup(t *testing.T) {
	t.Helper()
	// No cleanup needed for now - LocalStack is ephemeral
	// Could add cleanup of test logs here if needed
}
