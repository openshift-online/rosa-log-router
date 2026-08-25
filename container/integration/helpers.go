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
	"github.com/aws/aws-sdk-go-v2/service/dynamodb"
	dtypes "github.com/aws/aws-sdk-go-v2/service/dynamodb/types"
	"github.com/aws/aws-sdk-go-v2/service/s3"
	"github.com/aws/aws-sdk-go-v2/service/sqs"
	sqstypes "github.com/aws/aws-sdk-go-v2/service/sqs/types"
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
	dynamoClient *dynamodb.Client
	sqsClient    *sqs.Client

	// LocalStack-specific
	localstackURL string

	// Terraform outputs (fetched dynamically)
	centralBucket      string
	customer1Bucket    string
	customer2Bucket    string
	customer2LogGroup  string
	apiGatewayEndpoint string
	retryQueueURL      string
	tenantConfigTable  string
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
	dynamoClient := dynamodb.NewFromConfig(cfg)
	sqsClient := sqs.NewFromConfig(cfg)

	// Fetch terraform outputs
	centralBucket := getTerraformOutput(t, "central_source_bucket")
	customer1Bucket := getTerraformOutput(t, "customer1_bucket")
	customer2Bucket := getTerraformOutput(t, "customer2_bucket")
	customer2LogGroup := getTerraformOutput(t, "customer2_log_group")

	// Fetch optional API Gateway endpoint (may not be deployed)
	apiGatewayEndpoint := getTerraformOutputOptional(t, "api_gateway_endpoint")

	// Convert AWS-style API Gateway URL to LocalStack format
	// From: https://reuozwkfnn.execute-api.us-east-1.amazonaws.com/int
	// To:   http://localhost:4566/restapis/reuozwkfnn/int/_user_request_
	if apiGatewayEndpoint != "" && strings.Contains(apiGatewayEndpoint, "amazonaws.com") {
		apiGatewayEndpoint = convertToLocalStackAPIGatewayURL(apiGatewayEndpoint)
	}

	retryQueueURL := getTerraformOutputOptional(t, "central_retry_queue_url")
	tenantConfigTable := getTerraformOutput(t, "central_dynamodb_table")

	return &E2ETestHelper{
		ctx:                ctx,
		s3Client:           s3Client,
		cwLogsClient:       cwLogsClient,
		dynamoClient:       dynamoClient,
		sqsClient:          sqsClient,
		localstackURL:      LocalStackEndpoint,
		centralBucket:      centralBucket,
		customer1Bucket:    customer1Bucket,
		customer2Bucket:    customer2Bucket,
		customer2LogGroup:  customer2LogGroup,
		apiGatewayEndpoint: apiGatewayEndpoint,
		retryQueueURL:      retryQueueURL,
		tenantConfigTable:  tenantConfigTable,
	}
}

// convertToLocalStackAPIGatewayURL converts an AWS-style API Gateway URL to LocalStack format
// From: https://reuozwkfnn.execute-api.us-east-1.amazonaws.com/int
// To:   http://localhost:4566/restapis/reuozwkfnn/int/_user_request_
func convertToLocalStackAPIGatewayURL(awsURL string) string {
	// Parse the AWS URL to extract API ID and stage
	// Format: https://{api-id}.execute-api.{region}.amazonaws.com/{stage}
	parts := strings.Split(strings.TrimPrefix(awsURL, "https://"), "/")
	if len(parts) < 2 {
		return awsURL // Return original if format doesn't match
	}

	// Extract API ID from subdomain
	apiIDParts := strings.Split(parts[0], ".")
	if len(apiIDParts) == 0 {
		return awsURL
	}
	apiID := apiIDParts[0]

	// Extract stage (everything after first /)
	stage := strings.Join(parts[1:], "/")

	// Build LocalStack URL
	return fmt.Sprintf("%s/restapis/%s/%s/_user_request_", LocalStackEndpoint, apiID, stage)
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

// getTerraformOutputOptional fetches a terraform output value that may not exist (returns empty string if not found)
func getTerraformOutputOptional(t *testing.T, outputName string) string {
	t.Helper()

	cmd := exec.Command("terraform", "output", "-raw", outputName)
	cmd.Dir = "../../terraform/local" // Relative to container/integration directory
	output, err := cmd.CombinedOutput()
	if err != nil {
		// Output doesn't exist or terraform failed - this is OK for optional outputs
		t.Logf("Terraform output %s not found (optional): %s", outputName, string(output))
		return ""
	}

	value := strings.TrimSpace(string(output))
	if value != "" {
		t.Logf("Terraform output %s = %s", outputName, value)
	}
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

// APIGatewayEndpoint retrieves the API Gateway endpoint from cached Terraform outputs
func (h *E2ETestHelper) APIGatewayEndpoint() string {
	return h.apiGatewayEndpoint
}

// APIPSK retrieves the API PSK from Terraform outputs
func (h *E2ETestHelper) APIPSK() string {
	// Use the default test PSK
	return "test-psk-localstack-do-not-use-in-production"
}

// RetryQueueURL returns the retry queue URL from terraform output
func (h *E2ETestHelper) RetryQueueURL() string {
	return h.retryQueueURL
}

// CreateTestTenantConfig creates a DynamoDB entry for a test tenant
func (h *E2ETestHelper) CreateTestTenantConfig(t *testing.T, tenantID, deliveryType string, attrs map[string]dtypes.AttributeValue) {
	t.Helper()

	item := map[string]dtypes.AttributeValue{
		"tenant_id": &dtypes.AttributeValueMemberS{Value: tenantID},
		"type":      &dtypes.AttributeValueMemberS{Value: deliveryType},
		"enabled":   &dtypes.AttributeValueMemberBOOL{Value: true},
	}
	for k, v := range attrs {
		item[k] = v
	}

	_, err := h.dynamoClient.PutItem(h.ctx, &dynamodb.PutItemInput{
		TableName: aws.String(h.tenantConfigTable),
		Item:      item,
	})
	require.NoError(t, err, "failed to create test tenant config for %s/%s", tenantID, deliveryType)
	t.Logf("Created test tenant config: %s/%s", tenantID, deliveryType)
}

// DeleteTestTenantConfig removes a DynamoDB entry for a test tenant
func (h *E2ETestHelper) DeleteTestTenantConfig(t *testing.T, tenantID, deliveryType string) {
	t.Helper()

	_, err := h.dynamoClient.DeleteItem(h.ctx, &dynamodb.DeleteItemInput{
		TableName: aws.String(h.tenantConfigTable),
		Key: map[string]dtypes.AttributeValue{
			"tenant_id": &dtypes.AttributeValueMemberS{Value: tenantID},
			"type":      &dtypes.AttributeValueMemberS{Value: deliveryType},
		},
	})
	require.NoError(t, err, "failed to delete test tenant config for %s/%s", tenantID, deliveryType)
}

// WaitForSQSMessage polls an SQS queue for a message containing the test UUID.
// Uses ReceiveMessage to inspect message content. Note: in environments where a
// Lambda event source mapping is consuming from the same queue, prefer
// WaitForSQSMessageCount for non-destructive assertions to avoid racing the consumer.
func (h *E2ETestHelper) WaitForSQSMessage(t *testing.T, queueURL, testID string, timeout time.Duration) string {
	t.Helper()

	var lastErr error
	deadline := time.Now().Add(timeout)
	for time.Now().Before(deadline) {
		resp, err := h.sqsClient.ReceiveMessage(h.ctx, &sqs.ReceiveMessageInput{
			QueueUrl:            aws.String(queueURL),
			MaxNumberOfMessages: 10,
			WaitTimeSeconds:     2,
			VisibilityTimeout:   0,
		})
		if err != nil {
			lastErr = err
			time.Sleep(PollInterval)
			continue
		}

		for _, msg := range resp.Messages {
			if msg.Body != nil && strings.Contains(*msg.Body, testID) {
				t.Logf("Found message with UUID %s in queue %s", testID, queueURL)
				return *msg.Body
			}
		}

		time.Sleep(PollInterval)
	}

	require.Fail(t, "timeout waiting for SQS message", "UUID %s not found in queue %s after %v (last error: %v)", testID, queueURL, timeout, lastErr)
	return ""
}

// WaitForSQSMessageCount polls a queue's attributes until the message count
// reaches or exceeds the target. This is non-destructive — it doesn't receive
// or modify messages — so it's safe to use on queues with active Lambda ESMs.
func (h *E2ETestHelper) WaitForSQSMessageCount(t *testing.T, queueURL string, minCount int, timeout time.Duration) int {
	t.Helper()

	deadline := time.Now().Add(timeout)
	for time.Now().Before(deadline) {
		count := h.GetSQSQueueMessageCount(t, queueURL)
		if count >= minCount {
			t.Logf("Queue %s has %d messages (target: %d)", queueURL, count, minCount)
			return count
		}
		time.Sleep(PollInterval)
	}

	require.Fail(t, "timeout waiting for SQS message count",
		"queue %s did not reach %d messages after %v", queueURL, minCount, timeout)
	return 0
}

// GetSQSQueueMessageCount returns the approximate number of messages in a queue
func (h *E2ETestHelper) GetSQSQueueMessageCount(t *testing.T, queueURL string) int {
	t.Helper()

	resp, err := h.sqsClient.GetQueueAttributes(h.ctx, &sqs.GetQueueAttributesInput{
		QueueUrl:       aws.String(queueURL),
		AttributeNames: []sqstypes.QueueAttributeName{"ApproximateNumberOfMessages"},
	})
	require.NoError(t, err, "failed to get queue attributes for %s", queueURL)

	countStr := resp.Attributes["ApproximateNumberOfMessages"]
	var count int
	_, err = fmt.Sscanf(countStr, "%d", &count)
	require.NoError(t, err, "invalid ApproximateNumberOfMessages value %q", countStr)
	return count
}

// SendSQSMessage sends a message to an SQS queue.
func (h *E2ETestHelper) SendSQSMessage(t *testing.T, queueURL, body string) {
	t.Helper()

	_, err := h.sqsClient.SendMessage(h.ctx, &sqs.SendMessageInput{
		QueueUrl:    aws.String(queueURL),
		MessageBody: aws.String(body),
	})
	require.NoError(t, err, "failed to send message to queue %s", queueURL)
}

// Cleanup performs any necessary cleanup after tests (currently a no-op but provided for future use)
func (h *E2ETestHelper) Cleanup(t *testing.T) {
	t.Helper()
	// No cleanup needed for now - LocalStack is ephemeral
	// Could add cleanup of test logs here if needed
}
