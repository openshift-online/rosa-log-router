package processor

import (
	"testing"

	"github.com/aws/aws-lambda-go/events"
	"github.com/stretchr/testify/assert"
)

func TestGetCurrentQueue(t *testing.T) {
	testCases := []struct {
		name             string
		eventSourceARN   string
		expectedQueue    string
		expectedQueueStr string
	}{
		{
			name:             "detects main queue",
			eventSourceARN:   "arn:aws:sqs:us-east-1:123456789012:hcp-log-int-log-delivery-queue",
			expectedQueue:    QueueTypeMain,
			expectedQueueStr: "main",
		},
		{
			name:             "detects retry queue",
			eventSourceARN:   "arn:aws:sqs:us-east-1:123456789012:hcp-log-int-log-delivery-retry-queue",
			expectedQueue:    QueueTypeRetry,
			expectedQueueStr: "retry",
		},
		{
			name:             "detects partial queue",
			eventSourceARN:   "arn:aws:sqs:us-east-1:123456789012:hcp-log-int-log-delivery-partial-queue",
			expectedQueue:    QueueTypePartial,
			expectedQueueStr: "partial",
		},
		{
			name:             "returns unknown for empty ARN",
			eventSourceARN:   "",
			expectedQueue:    QueueTypeUnknown,
			expectedQueueStr: "unknown",
		},
		{
			name:             "returns unknown for invalid ARN",
			eventSourceARN:   "arn:aws:sqs:us-east-1:123456789012:some-other-queue",
			expectedQueue:    QueueTypeUnknown,
			expectedQueueStr: "unknown",
		},
		{
			name:             "returns unknown for DLQ",
			eventSourceARN:   "arn:aws:sqs:us-east-1:123456789012:hcp-log-int-log-delivery-main-dlq",
			expectedQueue:    QueueTypeUnknown,
			expectedQueueStr: "unknown",
		},
		{
			name:             "correctly prioritizes partial over main (suffix check)",
			eventSourceARN:   "arn:aws:sqs:us-east-1:123456789012:hcp-log-int-log-delivery-partial-queue",
			expectedQueue:    QueueTypePartial,
			expectedQueueStr: "partial",
		},
		{
			name:             "correctly prioritizes retry over main (suffix check)",
			eventSourceARN:   "arn:aws:sqs:us-east-1:123456789012:hcp-log-int-log-delivery-retry-queue",
			expectedQueue:    QueueTypeRetry,
			expectedQueueStr: "retry",
		},
	}

	for _, tc := range testCases {
		t.Run(tc.name, func(t *testing.T) {
			result := getCurrentQueue(tc.eventSourceARN)
			assert.Equal(t, tc.expectedQueue, result)
			assert.Equal(t, tc.expectedQueueStr, result, "queue type string should match")
		})
	}
}

func TestGetReceiveCount(t *testing.T) {
	testCases := []struct {
		name          string
		message       events.SQSMessage
		expectedCount int
	}{
		{
			name: "extracts valid receive count",
			message: events.SQSMessage{
				Attributes: map[string]string{
					"ApproximateReceiveCount": "1",
				},
			},
			expectedCount: 1,
		},
		{
			name: "extracts receive count of 2",
			message: events.SQSMessage{
				Attributes: map[string]string{
					"ApproximateReceiveCount": "2",
				},
			},
			expectedCount: 2,
		},
		{
			name: "extracts receive count of 3",
			message: events.SQSMessage{
				Attributes: map[string]string{
					"ApproximateReceiveCount": "3",
				},
			},
			expectedCount: 3,
		},
		{
			name: "extracts high receive count",
			message: events.SQSMessage{
				Attributes: map[string]string{
					"ApproximateReceiveCount": "10",
				},
			},
			expectedCount: 10,
		},
		{
			name: "returns 0 for missing attribute",
			message: events.SQSMessage{
				Attributes: map[string]string{},
			},
			expectedCount: 0,
		},
		{
			name: "returns 0 for nil attributes",
			message: events.SQSMessage{
				Attributes: nil,
			},
			expectedCount: 0,
		},
		{
			name: "returns 0 for invalid format (non-numeric)",
			message: events.SQSMessage{
				Attributes: map[string]string{
					"ApproximateReceiveCount": "invalid",
				},
			},
			expectedCount: 0,
		},
		{
			name: "returns 0 for empty string",
			message: events.SQSMessage{
				Attributes: map[string]string{
					"ApproximateReceiveCount": "",
				},
			},
			expectedCount: 0,
		},
		{
			name: "handles receive count of 0",
			message: events.SQSMessage{
				Attributes: map[string]string{
					"ApproximateReceiveCount": "0",
				},
			},
			expectedCount: 0,
		},
	}

	for _, tc := range testCases {
		t.Run(tc.name, func(t *testing.T) {
			result := getReceiveCount(tc.message)
			assert.Equal(t, tc.expectedCount, result)
		})
	}
}
