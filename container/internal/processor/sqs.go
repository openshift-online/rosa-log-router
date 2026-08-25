package processor

import (
	"context"
	"encoding/json"
	"fmt"
	"log/slog"
	"math"
	"time"

	"github.com/aws/aws-sdk-go-v2/aws"
	"github.com/aws/aws-sdk-go-v2/service/sqs"
	"github.com/aws/aws-sdk-go-v2/service/sqs/types"
	"github.com/openshift/rosa-log-router/internal/models"
)

// SQSClientAPI defines the interface for SQS operations needed for testing
type SQSClientAPI interface {
	SendMessage(ctx context.Context, params *sqs.SendMessageInput, optFns ...func(*sqs.Options)) (*sqs.SendMessageOutput, error)
}

// ExtractProcessingMetadata extracts processing metadata from SQS record
func ExtractProcessingMetadata(sqsRecordBody string) (*models.ProcessingMetadata, error) {
	var message struct {
		ProcessingMetadata *models.ProcessingMetadata `json:"processing_metadata"`
	}

	if err := json.Unmarshal([]byte(sqsRecordBody), &message); err != nil {
		return &models.ProcessingMetadata{}, fmt.Errorf("failed to extract metadata from SQS record: %w", err)
	}

	if message.ProcessingMetadata == nil {
		return &models.ProcessingMetadata{}, nil
	}

	return message.ProcessingMetadata, nil
}

// ShouldSkipProcessedEvents skips events that have already been processed based on offset
func ShouldSkipProcessedEvents(events []*models.LogEvent, offset int, logger *slog.Logger) []*models.LogEvent {
	if offset <= 0 {
		return events
	}

	if offset >= len(events) {
		logger.Warn("offset is >= event count, no events to process",
			"offset", offset,
			"event_count", len(events))
		return []*models.LogEvent{}
	}

	logger.Info("skipping already processed events",
		"offset", offset,
		"total_events", len(events),
		"remaining_events", len(events)-offset)

	return events[offset:]
}

// SendToRetryQueue sends a message to the retry queue with completed delivery metadata.
// Used for permission errors that need slow retry with longer backoff.
func SendToRetryQueue(ctx context.Context, sqsClient SQSClientAPI, retryQueueURL, messageBody string, completedDeliveries []string, logger *slog.Logger) error {
	var messageData map[string]interface{}
	if err := json.Unmarshal([]byte(messageBody), &messageData); err != nil {
		return fmt.Errorf("failed to parse message body: %w", err)
	}

	if messageData["processing_metadata"] == nil {
		messageData["processing_metadata"] = make(map[string]interface{})
	}
	procMetadata, ok := messageData["processing_metadata"].(map[string]interface{})
	if !ok {
		procMetadata = make(map[string]interface{})
		messageData["processing_metadata"] = procMetadata
	}

	procMetadata["completed_deliveries"] = completedDeliveries
	procMetadata["retry_count"] = 0
	procMetadata["from_retry_queue"] = true
	procMetadata["sent_to_retry_queue_at"] = time.Now().Format(time.RFC3339)

	updatedBody, err := json.Marshal(messageData)
	if err != nil {
		return fmt.Errorf("failed to marshal updated message body: %w", err)
	}

	_, err = sqsClient.SendMessage(ctx, &sqs.SendMessageInput{
		QueueUrl:    aws.String(retryQueueURL),
		MessageBody: aws.String(string(updatedBody)),
	})
	if err != nil {
		return fmt.Errorf("failed to send message to retry queue: %w", err)
	}

	logger.Info("sent message to retry queue",
		"completed_deliveries", completedDeliveries)
	return nil
}

// RequeueSQSMessageWithOffset re-queues an SQS message with processing offset information
func RequeueSQSMessageWithOffset(ctx context.Context, sqsClient SQSClientAPI, queueURL, messageBody, originalReceiptHandle string, processingOffset, maxRetries int, completedDeliveries []string, logger *slog.Logger) error {
	if queueURL == "" {
		logger.Warn("SQS_QUEUE_URL not configured, cannot re-queue message")
		return nil
	}

	// Parse original message to add offset information
	var messageData map[string]interface{}
	if err := json.Unmarshal([]byte(messageBody), &messageData); err != nil {
		logger.Error("failed to parse message body for re-queuing", "error", err)
		return fmt.Errorf("failed to parse message body: %w", err)
	}

	// Add processing metadata
	if messageData["processing_metadata"] == nil {
		messageData["processing_metadata"] = make(map[string]interface{})
	}

	procMetadata, ok := messageData["processing_metadata"].(map[string]interface{})
	if !ok {
		procMetadata = make(map[string]interface{})
		messageData["processing_metadata"] = procMetadata
	}

	// Get current retry count before incrementing
	currentRetryCount := 0
	if rc, ok := procMetadata["retry_count"].(float64); ok {
		currentRetryCount = int(rc)
	}
	newRetryCount := currentRetryCount + 1

	procMetadata["offset"] = processingOffset
	procMetadata["retry_count"] = newRetryCount
	procMetadata["original_receipt_handle"] = originalReceiptHandle
	procMetadata["requeued_at"] = time.Now().Format(time.RFC3339)
	delete(procMetadata, "from_retry_queue")
	if len(completedDeliveries) > 0 {
		procMetadata["completed_deliveries"] = completedDeliveries
	}

	// Check if we've exceeded retry limits
	if newRetryCount > maxRetries {
		logger.Error("message has exceeded maximum retry count, discarding",
			"max_retries", maxRetries,
			"retry_count", newRetryCount)
		return nil
	}

	// Calculate delay based on original retry count (exponential backoff)
	delaySeconds := int32(math.Min(math.Pow(2, float64(currentRetryCount+1)), 900)) // Max 15 minutes

	logger.Info("re-queuing message with offset",
		"offset", processingOffset,
		"retry_count", newRetryCount,
		"delay_seconds", delaySeconds)

	// Marshal updated message body
	updatedBody, err := json.Marshal(messageData)
	if err != nil {
		return fmt.Errorf("failed to marshal updated message body: %w", err)
	}

	// Send message back to queue with delay
	_, err = sqsClient.SendMessage(ctx, &sqs.SendMessageInput{
		QueueUrl:     aws.String(queueURL),
		MessageBody:  aws.String(string(updatedBody)),
		DelaySeconds: delaySeconds,
		MessageAttributes: map[string]types.MessageAttributeValue{
			"ProcessingOffset": {
				StringValue: aws.String(fmt.Sprintf("%d", processingOffset)),
				DataType:    aws.String("Number"),
			},
			"RetryCount": {
				StringValue: aws.String(fmt.Sprintf("%d", newRetryCount)),
				DataType:    aws.String("Number"),
			},
		},
	})

	if err != nil {
		logger.Error("failed to re-queue SQS message", "error", err)
		return fmt.Errorf("failed to send message to SQS: %w", err)
	}

	logger.Info("successfully re-queued message")
	return nil
}
