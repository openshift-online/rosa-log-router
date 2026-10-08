package processor

import (
	"context"
	"encoding/json"
	"testing"

	"github.com/aws/aws-sdk-go-v2/aws"
	"github.com/aws/aws-sdk-go-v2/service/sqs"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

// mockSQSClientForRouting is a mock SQS client for testing routing functions
type mockSQSClientForRouting struct {
	sendMessageFunc func(ctx context.Context, params *sqs.SendMessageInput, optFns ...func(*sqs.Options)) (*sqs.SendMessageOutput, error)
	lastSentMessage *sqs.SendMessageInput
}

// SendMessage implements SQSClientAPI for testing routing functions.
func (m *mockSQSClientForRouting) SendMessage(ctx context.Context, params *sqs.SendMessageInput, optFns ...func(*sqs.Options)) (*sqs.SendMessageOutput, error) {
	m.lastSentMessage = params
	if m.sendMessageFunc != nil {
		return m.sendMessageFunc(ctx, params, optFns...)
	}
	return &sqs.SendMessageOutput{
		MessageId: aws.String("test-message-id"),
	}, nil
}

// ReceiveMessage implements SQSClientAPI for testing (not used in routing tests).
func (m *mockSQSClientForRouting) ReceiveMessage(ctx context.Context, params *sqs.ReceiveMessageInput, optFns ...func(*sqs.Options)) (*sqs.ReceiveMessageOutput, error) {
	return nil, nil
}

// DeleteMessage implements SQSClientAPI for testing (not used in routing tests).
func (m *mockSQSClientForRouting) DeleteMessage(ctx context.Context, params *sqs.DeleteMessageInput, optFns ...func(*sqs.Options)) (*sqs.DeleteMessageOutput, error) {
	return nil, nil
}

// ChangeMessageVisibility implements SQSClientAPI for testing (not used in routing tests).
func (m *mockSQSClientForRouting) ChangeMessageVisibility(ctx context.Context, params *sqs.ChangeMessageVisibilityInput, optFns ...func(*sqs.Options)) (*sqs.ChangeMessageVisibilityOutput, error) {
	return nil, nil
}

func TestSendToPartialQueueWithMetadata(t *testing.T) {
	t.Run("sends message with partial success metadata", func(t *testing.T) {
		mockSQS := &mockSQSClientForRouting{}
		logger := getTestLogger()

		// Create original message body
		originalMessage := map[string]interface{}{
			"Message": `{"Records":[{"s3":{"bucket":{"name":"test-bucket"},"object":{"key":"test-key"}}}]}`,
		}
		messageBody, _ := json.Marshal(originalMessage)

		completedDeliveries := []string{"s3:example-bucket"}
		err := SendToPartialQueueWithMetadata(
			context.Background(),
			mockSQS,
			"https://sqs.us-east-1.amazonaws.com/123456789012/partial-queue",
			string(messageBody),
			completedDeliveries,
			0, // currentHops
			"partial_success",
			logger,
		)

		require.NoError(t, err)
		require.NotNil(t, mockSQS.lastSentMessage)

		// Verify queue URL
		assert.Equal(t, "https://sqs.us-east-1.amazonaws.com/123456789012/partial-queue", *mockSQS.lastSentMessage.QueueUrl)

		// Parse sent message body
		var sentMessage map[string]interface{}
		err = json.Unmarshal([]byte(*mockSQS.lastSentMessage.MessageBody), &sentMessage)
		require.NoError(t, err)

		// Verify processing metadata
		metadata, ok := sentMessage["processing_metadata"].(map[string]interface{})
		require.True(t, ok)

		assert.Equal(t, completedDeliveries, interfaceSliceToStringSlice(metadata["completed_deliveries"].([]interface{})))
		assert.Equal(t, float64(0), metadata["retry_count"])
		assert.Equal(t, true, metadata["from_partial_queue"])
		assert.NotEmpty(t, metadata["sent_to_partial_queue_at"])
		assert.Equal(t, float64(1), metadata["hops"]) // currentHops + 1
		assert.Equal(t, "partial_success", metadata["hop_reason"])

		// Verify destination states
		destStates, ok := metadata["destination_states"].(map[string]interface{})
		require.True(t, ok)
		s3State, ok := destStates["s3:example-bucket"].(map[string]interface{})
		require.True(t, ok)
		assert.Equal(t, "success", s3State["status"])
		assert.NotEmpty(t, s3State["updated_at"])
	})

	t.Run("increments hops correctly", func(t *testing.T) {
		mockSQS := &mockSQSClientForRouting{}
		logger := getTestLogger()

		messageBody := `{"Message":"test"}`
		err := SendToPartialQueueWithMetadata(
			context.Background(),
			mockSQS,
			"https://sqs.us-east-1.amazonaws.com/123456789012/partial-queue",
			messageBody,
			[]string{},
			5, // currentHops = 5
			"test_reason",
			logger,
		)

		require.NoError(t, err)

		var sentMessage map[string]interface{}
		err = json.Unmarshal([]byte(*mockSQS.lastSentMessage.MessageBody), &sentMessage)
		require.NoError(t, err)
		metadata := sentMessage["processing_metadata"].(map[string]interface{})

		assert.Equal(t, float64(6), metadata["hops"]) // 5 + 1
	})

	t.Run("handles empty completed deliveries", func(t *testing.T) {
		mockSQS := &mockSQSClientForRouting{}
		logger := getTestLogger()

		messageBody := `{"Message":"test"}`
		err := SendToPartialQueueWithMetadata(
			context.Background(),
			mockSQS,
			"https://sqs.us-east-1.amazonaws.com/123456789012/partial-queue",
			messageBody,
			[]string{},
			0,
			"partial_success",
			logger,
		)

		require.NoError(t, err)

		var sentMessage map[string]interface{}
		err = json.Unmarshal([]byte(*mockSQS.lastSentMessage.MessageBody), &sentMessage)
		require.NoError(t, err)
		metadata := sentMessage["processing_metadata"].(map[string]interface{})

		completedDeliveries := metadata["completed_deliveries"].([]interface{})
		assert.Equal(t, 0, len(completedDeliveries))
	})
}

// Helper function to convert []interface{} to []string for assertions
func interfaceSliceToStringSlice(slice []interface{}) []string {
	result := make([]string, len(slice))
	for i, v := range slice {
		result[i] = v.(string)
	}
	return result
}
