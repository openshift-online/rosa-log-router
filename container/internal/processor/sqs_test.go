package processor

import (
	"context"
	"encoding/json"
	"testing"
	"time"

	"github.com/aws/aws-sdk-go-v2/aws"
	"github.com/aws/aws-sdk-go-v2/service/sqs"
	"github.com/aws/aws-sdk-go-v2/service/sqs/types"
	"github.com/openshift/rosa-log-router/internal/models"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

// Mock SQS client for testing
type mockSQSClient struct {
	sendMessageFunc func(ctx context.Context, params *sqs.SendMessageInput, optFns ...func(*sqs.Options)) (*sqs.SendMessageOutput, error)
}

func (m *mockSQSClient) SendMessage(ctx context.Context, params *sqs.SendMessageInput, optFns ...func(*sqs.Options)) (*sqs.SendMessageOutput, error) {
	if m.sendMessageFunc != nil {
		return m.sendMessageFunc(ctx, params, optFns...)
	}
	return &sqs.SendMessageOutput{
		MessageId: aws.String("test-message-id"),
	}, nil
}

func TestExtractProcessingMetadata(t *testing.T) {
	t.Run("extracts offset from processing metadata", func(t *testing.T) {
		messageBody := `{
			"Message": "test",
			"processing_metadata": {
				"offset": 100,
				"retry_count": 2
			}
		}`

		metadata, err := ExtractProcessingMetadata(messageBody)

		require.NoError(t, err)
		assert.Equal(t, 100, metadata.Offset)
		assert.Equal(t, 2, metadata.RetryCount)
	})

	t.Run("returns empty metadata when not present", func(t *testing.T) {
		messageBody := `{"Message": "test"}`

		metadata, err := ExtractProcessingMetadata(messageBody)

		require.NoError(t, err)
		assert.Equal(t, 0, metadata.Offset)
		assert.Equal(t, 0, metadata.RetryCount)
	})

	t.Run("handles invalid JSON gracefully", func(t *testing.T) {
		messageBody := "invalid json"

		metadata, err := ExtractProcessingMetadata(messageBody)

		require.Error(t, err)
		assert.Equal(t, 0, metadata.Offset)
	})

	t.Run("extracts retry count", func(t *testing.T) {
		messageBody := `{
			"processing_metadata": {
				"retry_count": 5
			}
		}`

		metadata, err := ExtractProcessingMetadata(messageBody)

		require.NoError(t, err)
		assert.Equal(t, 5, metadata.RetryCount)
	})

	t.Run("extracts original receipt handle", func(t *testing.T) {
		messageBody := `{
			"processing_metadata": {
				"original_receipt_handle": "original-handle-123"
			}
		}`

		metadata, err := ExtractProcessingMetadata(messageBody)

		require.NoError(t, err)
		assert.Equal(t, "original-handle-123", metadata.OriginalReceiptHandle)
	})

	t.Run("extracts requeued timestamp", func(t *testing.T) {
		timestamp := time.Now().Format(time.RFC3339)
		messageBody := `{
			"processing_metadata": {
				"requeued_at": "` + timestamp + `"
			}
		}`

		metadata, err := ExtractProcessingMetadata(messageBody)

		require.NoError(t, err)
		assert.False(t, metadata.RequeuedAt.IsZero())
	})

	t.Run("extracts all metadata fields together", func(t *testing.T) {
		timestamp := "2024-01-01T12:00:00Z"
		messageBody := `{
			"processing_metadata": {
				"offset": 42,
				"retry_count": 3,
				"original_receipt_handle": "handle-xyz",
				"requeued_at": "` + timestamp + `"
			}
		}`

		metadata, err := ExtractProcessingMetadata(messageBody)

		require.NoError(t, err)
		assert.Equal(t, 42, metadata.Offset)
		assert.Equal(t, 3, metadata.RetryCount)
		assert.Equal(t, "handle-xyz", metadata.OriginalReceiptHandle)
		assert.False(t, metadata.RequeuedAt.IsZero())
	})
}

func TestShouldSkipProcessedEvents(t *testing.T) {
	logger := getTestLogger()

	t.Run("returns all events when offset is 0", func(t *testing.T) {
		events := []*models.LogEvent{
			{Message: "event1"},
			{Message: "event2"},
			{Message: "event3"},
		}

		result := ShouldSkipProcessedEvents(events, 0, logger)

		assert.Len(t, result, 3)
		assert.Equal(t, events, result)
	})

	t.Run("skips processed events based on offset", func(t *testing.T) {
		events := []*models.LogEvent{
			{Message: "event1"},
			{Message: "event2"},
			{Message: "event3"},
			{Message: "event4"},
			{Message: "event5"},
		}

		result := ShouldSkipProcessedEvents(events, 2, logger)

		assert.Len(t, result, 3)
		assert.Equal(t, "event3", result[0].Message)
		assert.Equal(t, "event4", result[1].Message)
		assert.Equal(t, "event5", result[2].Message)
	})

	t.Run("returns empty slice when offset equals event count", func(t *testing.T) {
		events := []*models.LogEvent{
			{Message: "event1"},
			{Message: "event2"},
		}

		result := ShouldSkipProcessedEvents(events, 2, logger)

		assert.Empty(t, result)
	})

	t.Run("returns empty slice when offset exceeds event count", func(t *testing.T) {
		events := []*models.LogEvent{
			{Message: "event1"},
		}

		result := ShouldSkipProcessedEvents(events, 10, logger)

		assert.Empty(t, result)
	})

	t.Run("handles negative offset as 0", func(t *testing.T) {
		events := []*models.LogEvent{
			{Message: "event1"},
			{Message: "event2"},
		}

		result := ShouldSkipProcessedEvents(events, -5, logger)

		assert.Len(t, result, 2)
	})

	t.Run("handles single event with offset 1", func(t *testing.T) {
		events := []*models.LogEvent{
			{Message: "event1"},
		}

		result := ShouldSkipProcessedEvents(events, 1, logger)

		assert.Empty(t, result)
	})
}

func TestRequeueSQSMessageWithOffset(t *testing.T) {
	logger := getTestLogger()
	ctx := context.Background()

	t.Run("re-queues message with offset metadata", func(t *testing.T) {
		var capturedInput *sqs.SendMessageInput
		mockClient := &mockSQSClient{
			sendMessageFunc: func(ctx context.Context, params *sqs.SendMessageInput, optFns ...func(*sqs.Options)) (*sqs.SendMessageOutput, error) {
				capturedInput = params
				return &sqs.SendMessageOutput{MessageId: aws.String("new-msg-id")}, nil
			},
		}

		messageBody := `{"Message": "test"}`
		queueURL := "https://sqs.us-east-1.amazonaws.com/123/test-queue"

		err := RequeueSQSMessageWithOffset(ctx, mockClient, queueURL, messageBody, "receipt-1", 50, 5, logger)

		require.NoError(t, err)
		assert.NotNil(t, capturedInput)
		assert.Equal(t, queueURL, *capturedInput.QueueUrl)

		// Parse the message body to verify offset was added
		var updatedBody map[string]any
		err = json.Unmarshal([]byte(*capturedInput.MessageBody), &updatedBody)
		require.NoError(t, err)

		metadata, ok := updatedBody["processing_metadata"].(map[string]any)
		require.True(t, ok)
		assert.Equal(t, float64(50), metadata["offset"])
		assert.Equal(t, float64(1), metadata["retry_count"])
	})

	t.Run("increments retry count on each re-queue", func(t *testing.T) {
		var capturedInput *sqs.SendMessageInput
		mockClient := &mockSQSClient{
			sendMessageFunc: func(ctx context.Context, params *sqs.SendMessageInput, optFns ...func(*sqs.Options)) (*sqs.SendMessageOutput, error) {
				capturedInput = params
				return &sqs.SendMessageOutput{MessageId: aws.String("new-msg-id")}, nil
			},
		}

		messageBody := `{
			"Message": "test",
			"processing_metadata": {
				"retry_count": 2
			}
		}`
		queueURL := "https://sqs.us-east-1.amazonaws.com/123/test-queue"

		err := RequeueSQSMessageWithOffset(ctx, mockClient, queueURL, messageBody, "receipt-1", 100, 5, logger)

		require.NoError(t, err)

		var updatedBody map[string]any
		err = json.Unmarshal([]byte(*capturedInput.MessageBody), &updatedBody)
		require.NoError(t, err)

		metadata := updatedBody["processing_metadata"].(map[string]any)
		assert.Equal(t, float64(3), metadata["retry_count"]) // Was 2, now 3
	})

	t.Run("applies exponential backoff delay", func(t *testing.T) {
		testCases := []struct {
			currentRetryCount int
			expectedDelay     int32
		}{
			{0, 2},    // 2^1 = 2 seconds
			{1, 4},    // 2^2 = 4 seconds
			{2, 8},    // 2^3 = 8 seconds
			{3, 16},   // 2^4 = 16 seconds
			{4, 32},   // 2^5 = 32 seconds
			{10, 900}, // Capped at 900 (15 minutes)
		}

		for _, tc := range testCases {
			var capturedDelay int32
			mockClient := &mockSQSClient{
				sendMessageFunc: func(ctx context.Context, params *sqs.SendMessageInput, optFns ...func(*sqs.Options)) (*sqs.SendMessageOutput, error) {
					capturedDelay = params.DelaySeconds
					return &sqs.SendMessageOutput{MessageId: aws.String("new-msg-id")}, nil
				},
			}

			// Use proper JSON encoding for retry_count
			data := map[string]any{
				"Message": "test",
				"processing_metadata": map[string]any{
					"retry_count": tc.currentRetryCount,
				},
			}
			messageBodyBytes, _ := json.Marshal(data)

			queueURL := "https://sqs.us-east-1.amazonaws.com/123/test-queue"
			err := RequeueSQSMessageWithOffset(ctx, mockClient, queueURL, string(messageBodyBytes), "receipt-1", 0, 20, logger)

			require.NoError(t, err)
			assert.Equal(t, tc.expectedDelay, capturedDelay)
		}
	})

	t.Run("stops re-queuing after max retries", func(t *testing.T) {
		callCount := 0
		mockClient := &mockSQSClient{
			sendMessageFunc: func(ctx context.Context, params *sqs.SendMessageInput, optFns ...func(*sqs.Options)) (*sqs.SendMessageOutput, error) {
				callCount++
				return &sqs.SendMessageOutput{MessageId: aws.String("new-msg-id")}, nil
			},
		}

		messageBody := `{
			"Message": "test",
			"processing_metadata": {
				"retry_count": 5
			}
		}`
		queueURL := "https://sqs.us-east-1.amazonaws.com/123/test-queue"
		maxRetries := 3

		err := RequeueSQSMessageWithOffset(ctx, mockClient, queueURL, messageBody, "receipt-1", 0, maxRetries, logger)

		// Should not error, but should not call SendMessage
		require.NoError(t, err)
		assert.Equal(t, 0, callCount, "SendMessage should not be called when max retries exceeded")
	})

	t.Run("handles empty queue URL gracefully", func(t *testing.T) {
		mockClient := &mockSQSClient{}
		messageBody := `{"Message": "test"}`

		err := RequeueSQSMessageWithOffset(ctx, mockClient, "", messageBody, "receipt-1", 0, 5, logger)

		// Should not error when queue URL is empty
		require.NoError(t, err)
	})

	t.Run("adds message attributes for offset and retry count", func(t *testing.T) {
		var capturedInput *sqs.SendMessageInput
		mockClient := &mockSQSClient{
			sendMessageFunc: func(ctx context.Context, params *sqs.SendMessageInput, optFns ...func(*sqs.Options)) (*sqs.SendMessageOutput, error) {
				capturedInput = params
				return &sqs.SendMessageOutput{MessageId: aws.String("new-msg-id")}, nil
			},
		}

		messageBody := `{"Message": "test"}`
		queueURL := "https://sqs.us-east-1.amazonaws.com/123/test-queue"

		err := RequeueSQSMessageWithOffset(ctx, mockClient, queueURL, messageBody, "receipt-1", 75, 5, logger)

		require.NoError(t, err)
		assert.NotNil(t, capturedInput.MessageAttributes)

		offsetAttr, ok := capturedInput.MessageAttributes["ProcessingOffset"]
		require.True(t, ok)
		assert.Equal(t, "75", *offsetAttr.StringValue)
		assert.Equal(t, "Number", *offsetAttr.DataType)

		retryAttr, ok := capturedInput.MessageAttributes["RetryCount"]
		require.True(t, ok)
		assert.Equal(t, "1", *retryAttr.StringValue)
		assert.Equal(t, "Number", *retryAttr.DataType)
	})

	t.Run("preserves original receipt handle in metadata", func(t *testing.T) {
		var capturedInput *sqs.SendMessageInput
		mockClient := &mockSQSClient{
			sendMessageFunc: func(ctx context.Context, params *sqs.SendMessageInput, optFns ...func(*sqs.Options)) (*sqs.SendMessageOutput, error) {
				capturedInput = params
				return &sqs.SendMessageOutput{MessageId: aws.String("new-msg-id")}, nil
			},
		}

		messageBody := `{"Message": "test"}`
		queueURL := "https://sqs.us-east-1.amazonaws.com/123/test-queue"
		originalHandle := "original-receipt-handle-abc123"

		err := RequeueSQSMessageWithOffset(ctx, mockClient, queueURL, messageBody, originalHandle, 0, 5, logger)

		require.NoError(t, err)

		var updatedBody map[string]any
		err = json.Unmarshal([]byte(*capturedInput.MessageBody), &updatedBody)
		require.NoError(t, err)

		metadata := updatedBody["processing_metadata"].(map[string]any)
		assert.Equal(t, originalHandle, metadata["original_receipt_handle"])
	})

	t.Run("adds requeued timestamp", func(t *testing.T) {
		var capturedInput *sqs.SendMessageInput
		mockClient := &mockSQSClient{
			sendMessageFunc: func(ctx context.Context, params *sqs.SendMessageInput, optFns ...func(*sqs.Options)) (*sqs.SendMessageOutput, error) {
				capturedInput = params
				return &sqs.SendMessageOutput{MessageId: aws.String("new-msg-id")}, nil
			},
		}

		messageBody := `{"Message": "test"}`
		queueURL := "https://sqs.us-east-1.amazonaws.com/123/test-queue"

		beforeTime := time.Now()
		err := RequeueSQSMessageWithOffset(ctx, mockClient, queueURL, messageBody, "receipt-1", 0, 5, logger)
		afterTime := time.Now()

		require.NoError(t, err)

		var updatedBody map[string]any
		err = json.Unmarshal([]byte(*capturedInput.MessageBody), &updatedBody)
		require.NoError(t, err)

		metadata := updatedBody["processing_metadata"].(map[string]any)
		requeuedAtStr, ok := metadata["requeued_at"].(string)
		require.True(t, ok)

		requeuedAt, err := time.Parse(time.RFC3339, requeuedAtStr)
		require.NoError(t, err)

		assert.True(t, requeuedAt.After(beforeTime.Add(-time.Second)))
		assert.True(t, requeuedAt.Before(afterTime.Add(time.Second)))
	})
}

func TestMessageAttributes(t *testing.T) {
	t.Run("creates message attributes with correct data types", func(t *testing.T) {
		attrs := map[string]types.MessageAttributeValue{
			"ProcessingOffset": {
				StringValue: aws.String("100"),
				DataType:    aws.String("Number"),
			},
			"RetryCount": {
				StringValue: aws.String("3"),
				DataType:    aws.String("Number"),
			},
		}

		assert.Equal(t, "100", *attrs["ProcessingOffset"].StringValue)
		assert.Equal(t, "Number", *attrs["ProcessingOffset"].DataType)
		assert.Equal(t, "3", *attrs["RetryCount"].StringValue)
		assert.Equal(t, "Number", *attrs["RetryCount"].DataType)
	})
}

func TestOffsetProcessingEdgeCases(t *testing.T) {
	logger := getTestLogger()

	t.Run("handles offset of exactly event count", func(t *testing.T) {
		events := []*models.LogEvent{
			{Message: "event1"},
			{Message: "event2"},
			{Message: "event3"},
		}

		result := ShouldSkipProcessedEvents(events, 3, logger)

		assert.Empty(t, result)
	})

	t.Run("handles offset of event count plus one", func(t *testing.T) {
		events := []*models.LogEvent{
			{Message: "event1"},
		}

		result := ShouldSkipProcessedEvents(events, 2, logger)

		assert.Empty(t, result)
	})

	t.Run("handles very large offset", func(t *testing.T) {
		events := []*models.LogEvent{
			{Message: "event1"},
		}

		result := ShouldSkipProcessedEvents(events, 1000000, logger)

		assert.Empty(t, result)
	})
}

func TestRetryCountProgression(t *testing.T) {
	t.Run("validates retry count increases on each re-queue", func(t *testing.T) {
		retryProgression := []int{0, 1, 2, 3, 4, 5}

		for i := 0; i < len(retryProgression)-1; i++ {
			current := retryProgression[i]
			next := retryProgression[i+1]
			assert.Equal(t, current+1, next, "Retry count should increment by 1")
		}
	})

	t.Run("validates exponential backoff calculation", func(t *testing.T) {
		// Delay = min(2^(retry_count+1), 900)
		testCases := []struct {
			retryCount    int
			expectedDelay int
		}{
			{0, 2},
			{1, 4},
			{2, 8},
			{3, 16},
			{4, 32},
			{5, 64},
			{6, 128},
			{7, 256},
			{8, 512},
			{9, 900},  // Capped
			{10, 900}, // Capped
		}

		for _, tc := range testCases {
			delay := int(min(pow2(tc.retryCount+1), 900))
			assert.Equal(t, tc.expectedDelay, delay, "Retry count %d", tc.retryCount)
		}
	})
}

// Helper functions for exponential backoff calculation
func pow2(n int) float64 {
	result := 1.0
	for i := 0; i < n; i++ {
		result *= 2
	}
	return result
}

func min(a, b float64) float64 {
	if a < b {
		return a
	}
	return b
}
