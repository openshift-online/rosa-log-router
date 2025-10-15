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
	var messageBody map[string]interface{}
	if err := json.Unmarshal([]byte(sqsRecordBody), &messageBody); err != nil {
		return &models.ProcessingMetadata{}, nil // Return empty metadata on parse error
	}

	metadataMap, ok := messageBody["processing_metadata"].(map[string]interface{})
	if !ok {
		return &models.ProcessingMetadata{}, nil
	}

	metadata := &models.ProcessingMetadata{}

	if offset, ok := metadataMap["offset"].(float64); ok {
		metadata.Offset = int(offset)
	}

	if retryCount, ok := metadataMap["retry_count"].(float64); ok {
		metadata.RetryCount = int(retryCount)
	}

	if receiptHandle, ok := metadataMap["original_receipt_handle"].(string); ok {
		metadata.OriginalReceiptHandle = receiptHandle
	}

	if requeuedAt, ok := metadataMap["requeued_at"].(string); ok {
		if t, err := time.Parse(time.RFC3339, requeuedAt); err == nil {
			metadata.RequeuedAt = t
		}
	}

	return metadata, nil
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

// RequeueSQSMessageWithOffset re-queues an SQS message with processing offset information
func RequeueSQSMessageWithOffset(ctx context.Context, sqsClient SQSClientAPI, queueURL, messageBody, originalReceiptHandle string, processingOffset, maxRetries int, logger *slog.Logger) error {
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
