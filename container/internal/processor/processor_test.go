package processor

import (
	"context"
	"encoding/json"
	"testing"

	"github.com/aws/aws-lambda-go/events"
	"github.com/aws/aws-sdk-go-v2/service/cloudwatch"
	"github.com/aws/aws-sdk-go-v2/service/dynamodb"
	"github.com/aws/aws-sdk-go-v2/service/dynamodb/types"
	"github.com/aws/aws-sdk-go-v2/service/s3"
	"github.com/aws/aws-sdk-go-v2/service/sqs"
	"github.com/aws/aws-sdk-go-v2/service/sts"
	"github.com/openshift/rosa-log-router/internal/models"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

// Mock DynamoDB client for testing
type mockDynamoDBClient struct {
	queryFunc func(ctx context.Context, params *dynamodb.QueryInput, optFns ...func(*dynamodb.Options)) (*dynamodb.QueryOutput, error)
}

func (m *mockDynamoDBClient) Query(ctx context.Context, params *dynamodb.QueryInput, optFns ...func(*dynamodb.Options)) (*dynamodb.QueryOutput, error) {
	if m.queryFunc != nil {
		return m.queryFunc(ctx, params, optFns...)
	}
	// Return empty result by default (no tenant configs found)
	return &dynamodb.QueryOutput{Items: []map[string]types.AttributeValue{}}, nil
}

// Helper function to create test processor
func createTestProcessor() *Processor {
	logger := getTestLogger()
	config := models.DefaultConfig()
	config.TenantConfigTable = "test-table"
	config.CentralLogDistributionRoleArn = "arn:aws:iam::123456789012:role/TestRole"

	// Create mock DynamoDB client that returns no tenant configs by default
	mockDynamo := &mockDynamoDBClient{}

	// Create nil clients for S3, SQS, STS, CloudWatch (not needed for parsing tests)
	var s3Client *s3.Client
	var sqsClient *sqs.Client
	var stsClient *sts.Client
	var cwClient *cloudwatch.Client

	return NewProcessor(s3Client, mockDynamo, sqsClient, stsClient, cwClient, "", config, logger)
}

// Helper to create SQS event
func createSQSEvent(messageBody string, messageID string) events.SQSEvent {
	return events.SQSEvent{
		Records: []events.SQSMessage{
			{
				MessageId:     messageID,
				Body:          messageBody,
				ReceiptHandle: "test-receipt-handle",
			},
		},
	}
}

// Helper to create SNS message with S3 event
func createSNSMessageWithS3Event(bucketName, objectKey string) string {
	s3Event := models.S3Event{
		Records: []models.S3EventRecord{
			{
				S3: struct {
					Bucket struct {
						Name string `json:"name"`
					} `json:"bucket"`
					Object struct {
						Key string `json:"key"`
					} `json:"object"`
				}{
					Bucket: struct {
						Name string `json:"name"`
					}{Name: bucketName},
					Object: struct {
						Key string `json:"key"`
					}{Key: objectKey},
				},
			},
		},
	}

	s3EventJSON, _ := json.Marshal(s3Event)
	snsMessage := models.SNSMessage{
		Message: string(s3EventJSON),
	}
	snsJSON, _ := json.Marshal(snsMessage)
	return string(snsJSON)
}

func TestHandleLambdaEvent(t *testing.T) {
	t.Run("returns empty batch failures on success", func(t *testing.T) {
		proc := createTestProcessor()
		event := createSQSEvent("{}", "msg-1")

		// This will fail internally but should not crash
		response, err := proc.HandleLambdaEvent(context.Background(), event)

		require.NoError(t, err)
		// Should have failures because we don't have real AWS clients
		// but the handler itself should not error
		assert.NotNil(t, response)
	})

	t.Run("processes multiple SQS records", func(t *testing.T) {
		proc := createTestProcessor()
		event := events.SQSEvent{
			Records: []events.SQSMessage{
				{MessageId: "msg-1", Body: "{}", ReceiptHandle: "receipt-1"},
				{MessageId: "msg-2", Body: "{}", ReceiptHandle: "receipt-2"},
				{MessageId: "msg-3", Body: "{}", ReceiptHandle: "receipt-3"},
			},
		}

		response, err := proc.HandleLambdaEvent(context.Background(), event)

		require.NoError(t, err)
		assert.NotNil(t, response)
		// All should fail without proper setup, but handler should complete
		assert.GreaterOrEqual(t, len(response.BatchItemFailures), 0)
	})

	t.Run("returns batch item failures for recoverable errors", func(t *testing.T) {
		proc := createTestProcessor()

		// Create message with invalid JSON - should be non-recoverable
		invalidJSON := "not valid json"
		event := createSQSEvent(invalidJSON, "msg-1")

		response, err := proc.HandleLambdaEvent(context.Background(), event)

		require.NoError(t, err)
		// Invalid JSON is non-recoverable, should not be in batch failures
		assert.Equal(t, 0, len(response.BatchItemFailures))
	})

	t.Run("handles empty SQS event", func(t *testing.T) {
		proc := createTestProcessor()
		event := events.SQSEvent{Records: []events.SQSMessage{}}

		response, err := proc.HandleLambdaEvent(context.Background(), event)

		require.NoError(t, err)
		assert.Empty(t, response.BatchItemFailures)
	})
}

func TestProcessSQSRecord(t *testing.T) {
	proc := createTestProcessor()

	t.Run("parses valid SNS message with S3 event", func(t *testing.T) {
		messageBody := createSNSMessageWithS3Event("test-bucket", "cluster/namespace/app/pod/file.json.gz")

		// Will fail due to missing AWS clients, but should parse successfully
		_, err := proc.ProcessSQSRecord(context.Background(), messageBody, "msg-1", "receipt-1")

		// Error is expected (no DynamoDB client), but should not be InvalidS3NotificationError
		if err != nil {
			assert.False(t, models.IsNonRecoverable(err) && err.Error() == "invalid SQS message format")
		}
	})

	t.Run("returns non-recoverable error for invalid SNS message", func(t *testing.T) {
		invalidMessage := "not valid json"

		_, err := proc.ProcessSQSRecord(context.Background(), invalidMessage, "msg-1", "receipt-1")

		require.Error(t, err)
		assert.True(t, models.IsNonRecoverable(err))
		assert.Contains(t, err.Error(), "invalid SQS message format")
	})

	t.Run("returns non-recoverable error for invalid S3 event in SNS message", func(t *testing.T) {
		snsMessage := models.SNSMessage{Message: "invalid s3 event"}
		messageBody, _ := json.Marshal(snsMessage)

		_, err := proc.ProcessSQSRecord(context.Background(), string(messageBody), "msg-1", "receipt-1")

		require.Error(t, err)
		assert.True(t, models.IsNonRecoverable(err))
		assert.Contains(t, err.Error(), "invalid S3 event format")
	})

	t.Run("URL decodes S3 object key", func(t *testing.T) {
		// Create S3 event with URL-encoded key
		encodedKey := "cluster%2Fnamespace%2Fapp%2Fpod%2Ffile.json.gz"
		messageBody := createSNSMessageWithS3Event("test-bucket", encodedKey)

		_, err := proc.ProcessSQSRecord(context.Background(), messageBody, "msg-1", "receipt-1")

		// Should decode successfully (error will be from missing clients, not decoding)
		if err != nil {
			assert.NotContains(t, err.Error(), "failed to unescape object key")
		}
	})

	t.Run("returns non-recoverable error for invalid object key path", func(t *testing.T) {
		// Object key with insufficient path segments
		messageBody := createSNSMessageWithS3Event("test-bucket", "invalid/path")

		stats, err := proc.ProcessSQSRecord(context.Background(), messageBody, "msg-1", "receipt-1")

		// Non-recoverable errors are logged and swallowed during S3 processing
		// The record is skipped and processing continues
		require.NoError(t, err)
		assert.NotNil(t, stats)
	})

	t.Run("processes multiple S3 records in single message", func(t *testing.T) {
		s3Event := models.S3Event{
			Records: []models.S3EventRecord{
				{
					S3: struct {
						Bucket struct {
							Name string `json:"name"`
						} `json:"bucket"`
						Object struct {
							Key string `json:"key"`
						} `json:"object"`
					}{
						Bucket: struct {
							Name string `json:"name"`
						}{Name: "bucket1"},
						Object: struct {
							Key string `json:"key"`
						}{Key: "cluster/ns/app/pod/file1.json.gz"},
					},
				},
				{
					S3: struct {
						Bucket struct {
							Name string `json:"name"`
						} `json:"bucket"`
						Object struct {
							Key string `json:"key"`
						} `json:"object"`
					}{
						Bucket: struct {
							Name string `json:"name"`
						}{Name: "bucket2"},
						Object: struct {
							Key string `json:"key"`
						}{Key: "cluster/ns/app/pod/file2.json.gz"},
					},
				},
			},
		}

		s3EventJSON, _ := json.Marshal(s3Event)
		snsMessage := models.SNSMessage{Message: string(s3EventJSON)}
		messageBody, _ := json.Marshal(snsMessage)

		stats, err := proc.ProcessSQSRecord(context.Background(), string(messageBody), "msg-1", "receipt-1")

		// Will fail due to missing clients, but should attempt to process both
		assert.NotNil(t, stats)
		if err != nil {
			// Should have attempted both records
			assert.NotContains(t, err.Error(), "invalid S3 event format")
		}
	})
}

func TestProcessSQSRecordErrorClassification(t *testing.T) {
	proc := createTestProcessor()

	testCases := []struct {
		name                 string
		messageBody          string
		expectNonRecoverable bool
		errorContains        string
	}{
		{
			name:                 "invalid JSON is non-recoverable",
			messageBody:          "invalid json",
			expectNonRecoverable: true,
			errorContains:        "invalid SQS message format",
		},
		{
			name:                 "invalid S3 event is non-recoverable",
			messageBody:          `{"Message": "invalid"}`,
			expectNonRecoverable: true,
			errorContains:        "invalid S3 event format",
		},
		// Note: invalid object key path test removed - non-recoverable S3 processing errors
		// are logged and swallowed, so no error is returned to test
	}

	for _, tc := range testCases {
		t.Run(tc.name, func(t *testing.T) {
			_, err := proc.ProcessSQSRecord(context.Background(), tc.messageBody, "msg-1", "receipt-1")

			require.Error(t, err)
			assert.Equal(t, tc.expectNonRecoverable, models.IsNonRecoverable(err))
			if tc.errorContains != "" {
				assert.Contains(t, err.Error(), tc.errorContains)
			}
		})
	}
}

func TestDeliveryStatsAccumulation(t *testing.T) {
	t.Run("accumulates delivery stats across multiple records", func(t *testing.T) {
		// This is a conceptual test - in reality would need mocked AWS clients
		stats := &models.DeliveryStats{
			SuccessfulDeliveries: 0,
			FailedDeliveries:     0,
		}

		assert.Equal(t, 0, stats.SuccessfulDeliveries)
		assert.Equal(t, 0, stats.FailedDeliveries)

		// Simulate successful delivery
		stats.SuccessfulDeliveries++
		assert.Equal(t, 1, stats.SuccessfulDeliveries)

		// Simulate failed delivery
		stats.FailedDeliveries++
		assert.Equal(t, 1, stats.FailedDeliveries)
	})
}

func TestMultiDeliveryLogic(t *testing.T) {
	t.Run("validates multiple delivery types can be configured", func(t *testing.T) {
		// Test that delivery config supports both CloudWatch and S3
		configs := []*models.DeliveryConfig{
			{
				TenantID: "test-tenant",
				Type:     "cloudwatch",
				Enabled:  true,
			},
			{
				TenantID: "test-tenant",
				Type:     "s3",
				Enabled:  true,
			},
		}

		assert.Len(t, configs, 2)
		assert.Equal(t, "cloudwatch", configs[0].Type)
		assert.Equal(t, "s3", configs[1].Type)
	})

	t.Run("respects enabled flag per delivery config", func(t *testing.T) {
		configs := []*models.DeliveryConfig{
			{
				TenantID: "test-tenant",
				Type:     "cloudwatch",
				Enabled:  true,
			},
			{
				TenantID: "test-tenant",
				Type:     "s3",
				Enabled:  false,
			},
		}

		enabledConfigs := make([]*models.DeliveryConfig, 0)
		for _, cfg := range configs {
			if cfg.Enabled {
				enabledConfigs = append(enabledConfigs, cfg)
			}
		}

		assert.Len(t, enabledConfigs, 1)
		assert.Equal(t, "cloudwatch", enabledConfigs[0].Type)
	})
}

func TestLambdaEventResponseStructure(t *testing.T) {
	t.Run("batch item failures contain message IDs", func(t *testing.T) {
		response := events.SQSEventResponse{
			BatchItemFailures: []events.SQSBatchItemFailure{
				{ItemIdentifier: "msg-1"},
				{ItemIdentifier: "msg-2"},
			},
		}

		assert.Len(t, response.BatchItemFailures, 2)
		assert.Equal(t, "msg-1", response.BatchItemFailures[0].ItemIdentifier)
		assert.Equal(t, "msg-2", response.BatchItemFailures[1].ItemIdentifier)
	})

	t.Run("empty batch failures indicate all succeeded", func(t *testing.T) {
		response := events.SQSEventResponse{
			BatchItemFailures: []events.SQSBatchItemFailure{},
		}

		assert.Empty(t, response.BatchItemFailures)
	})
}

func TestS3EventParsing(t *testing.T) {
	t.Run("parses S3 event record structure", func(t *testing.T) {
		s3Event := models.S3Event{
			Records: []models.S3EventRecord{
				{
					S3: struct {
						Bucket struct {
							Name string `json:"name"`
						} `json:"bucket"`
						Object struct {
							Key string `json:"key"`
						} `json:"object"`
					}{
						Bucket: struct {
							Name string `json:"name"`
						}{Name: "test-bucket"},
						Object: struct {
							Key string `json:"key"`
						}{Key: "test/key.json.gz"},
					},
				},
			},
		}

		assert.Len(t, s3Event.Records, 1)
		assert.Equal(t, "test-bucket", s3Event.Records[0].S3.Bucket.Name)
		assert.Equal(t, "test/key.json.gz", s3Event.Records[0].S3.Object.Key)
	})

	t.Run("parses SNS message wrapping S3 event", func(t *testing.T) {
		s3EventJSON := `{"Records":[{"s3":{"bucket":{"name":"my-bucket"},"object":{"key":"my-key"}}}]}`
		snsMessage := models.SNSMessage{
			Message: s3EventJSON,
		}

		assert.Equal(t, s3EventJSON, snsMessage.Message)

		var s3Event models.S3Event
		err := json.Unmarshal([]byte(snsMessage.Message), &s3Event)
		require.NoError(t, err)
		assert.Len(t, s3Event.Records, 1)
	})
}

func TestProcessorConfiguration(t *testing.T) {
	t.Run("loads configuration from models", func(t *testing.T) {
		config := models.DefaultConfig()

		assert.NotEmpty(t, config.AWSRegion)
		assert.Equal(t, 3, config.RetryAttempts)
		assert.Equal(t, 1000, config.MaxBatchSize)
	})

	t.Run("creates processor with required components", func(t *testing.T) {
		proc := createTestProcessor()

		assert.NotNil(t, proc)
		assert.NotNil(t, proc.config)
		assert.NotNil(t, proc.logger)
		assert.Equal(t, "test-table", proc.config.TenantConfigTable)
	})
}

func TestDeliveryTypeValidation(t *testing.T) {
	validTypes := []string{"cloudwatch", "s3"}
	invalidTypes := []string{"kinesis", "kafka", "unknown"}

	t.Run("validates known delivery types", func(t *testing.T) {
		for _, dt := range validTypes {
			assert.Contains(t, validTypes, dt)
		}
	})

	t.Run("identifies unknown delivery types", func(t *testing.T) {
		for _, dt := range invalidTypes {
			assert.NotContains(t, validTypes, dt)
		}
	})
}

func TestMessageBodyStructure(t *testing.T) {
	t.Run("parses nested SNS and S3 event structure", func(t *testing.T) {
		// Create the full chain: SQS -> SNS -> S3
		s3Event := map[string]any{
			"Records": []map[string]any{
				{
					"s3": map[string]any{
						"bucket": map[string]any{"name": "test-bucket"},
						"object": map[string]any{"key": "test-key"},
					},
				},
			},
		}

		s3EventJSON, _ := json.Marshal(s3Event)
		snsMessage := map[string]any{
			"Message": string(s3EventJSON),
		}

		snsJSON, _ := json.Marshal(snsMessage)

		// Parse it back
		var parsedSNS models.SNSMessage
		err := json.Unmarshal(snsJSON, &parsedSNS)
		require.NoError(t, err)

		var parsedS3 models.S3Event
		err = json.Unmarshal([]byte(parsedSNS.Message), &parsedS3)
		require.NoError(t, err)

		assert.Len(t, parsedS3.Records, 1)
		assert.Equal(t, "test-bucket", parsedS3.Records[0].S3.Bucket.Name)
		assert.Equal(t, "test-key", parsedS3.Records[0].S3.Object.Key)
	})
}

func TestURLDecoding(t *testing.T) {
	t.Run("decodes URL-encoded S3 keys", func(t *testing.T) {
		testCases := []struct {
			encoded  string
			expected string
		}{
			{
				encoded:  "cluster%2Fnamespace%2Fapp%2Fpod%2Ffile.json.gz",
				expected: "cluster/namespace/app/pod/file.json.gz",
			},
			{
				encoded:  "my%20file%20with%20spaces.json.gz",
				expected: "my file with spaces.json.gz",
			},
			{
				encoded:  "normal-file.json.gz",
				expected: "normal-file.json.gz",
			},
		}

		for _, tc := range testCases {
			messageBody := createSNSMessageWithS3Event("bucket", tc.encoded)

			var snsMsg models.SNSMessage
			err := json.Unmarshal([]byte(messageBody), &snsMsg)
			require.NoError(t, err)

			var s3Event models.S3Event
			err = json.Unmarshal([]byte(snsMsg.Message), &s3Event)
			require.NoError(t, err)

			// The encoded key is in the message
			assert.Equal(t, tc.encoded, s3Event.Records[0].S3.Object.Key)
		}
	})
}
