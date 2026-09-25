// Package processor implements the core log processing logic for SQS, Lambda, and S3 scan modes.
package processor

import (
	"context"
	"encoding/json"
	"fmt"
	"log/slog"
	"net/url"
	"regexp"
	"slices"
	"strconv"
	"time"

	"github.com/aws/aws-lambda-go/events"
	"github.com/aws/aws-sdk-go-v2/aws"
	"github.com/aws/aws-sdk-go-v2/service/cloudwatch"
	"github.com/aws/aws-sdk-go-v2/service/s3"
	"github.com/aws/aws-sdk-go-v2/service/sqs"
	"github.com/aws/aws-sdk-go-v2/service/sts"
	awsmetrics "github.com/openshift/rosa-log-router/internal/aws"
	"github.com/openshift/rosa-log-router/internal/delivery"
	"github.com/openshift/rosa-log-router/internal/models"
	"github.com/openshift/rosa-log-router/internal/tenant"
)

// AWS Lineage constants
const (
	// LineageExtractionError indicates extraction failed; message still processes normally
	LineageExtractionError = -1
	// LineageNotPresent indicates no AWSTraceHeader (first-hop message, normal)
	LineageNotPresent = 0
)

// lineageRe matches the hop count in an AWS Lineage trace header.
var lineageRe = regexp.MustCompile(`Lineage=[^:]*:(\d+)`)

// Processor handles log processing and delivery
type Processor struct {
	s3Client         *s3.Client
	sqsClient        *sqs.Client
	tenantConfig     *tenant.ConfigManager
	cwDeliverer      *delivery.CloudWatchDeliverer
	s3Deliverer      *delivery.S3Deliverer
	metricsPublisher *awsmetrics.MetricsPublisher
	config           *models.Config
	logger           *slog.Logger
}

// NewProcessor creates a new log processor
func NewProcessor(
	s3Client *s3.Client,
	dynamoClient tenant.DynamoDBQueryAPI,
	sqsClient *sqs.Client,
	stsClient *sts.Client,
	cwClient *cloudwatch.Client,
	endpointURL string,
	config *models.Config,
	logger *slog.Logger,
) *Processor {
	return &Processor{
		s3Client:         s3Client,
		sqsClient:        sqsClient,
		tenantConfig:     tenant.NewConfigManager(dynamoClient, config.TenantConfigTable, logger),
		cwDeliverer:      delivery.NewCloudWatchDeliverer(stsClient, config.CentralLogDistributionRoleArn, endpointURL, logger),
		s3Deliverer:      delivery.NewS3Deliverer(stsClient, config.CentralLogDistributionRoleArn, config.S3UsePathStyle, endpointURL, logger),
		metricsPublisher: awsmetrics.NewMetricsPublisher(cwClient, logger),
		config:           config,
		logger:           logger,
	}
}

// isDestinationSucceeded checks if a destination has already succeeded via DestinationStates.
func isDestinationSucceeded(metadata *models.ProcessingMetadata, deliveryID string) bool {
	if len(metadata.DestinationStates) == 0 {
		return false
	}
	state, exists := metadata.DestinationStates[deliveryID]
	return exists && state.Status == "success"
}

// buildDestinationStates creates a map of deliveryID -> DestinationState for successful completions.
func buildDestinationStates(completedDeliveries []string) map[string]models.DestinationState {
	states := make(map[string]models.DestinationState)
	for _, deliveryID := range completedDeliveries {
		states[deliveryID] = models.DestinationState{
			Status:    "success",
			UpdatedAt: time.Now().Format(time.RFC3339),
		}
	}
	return states
}

// checkHopThresholds logs warnings for suspicious hop counts without exposing sensitive destination data.
func checkHopThresholds(logger *slog.Logger, metadata *models.ProcessingMetadata) {
	// Count destination states by status (excludes sensitive bucket/log-group names and error text)
	destStatusCounts := make(map[string]int)
	for _, state := range metadata.DestinationStates {
		destStatusCounts[state.Status]++
	}

	if metadata.Hops >= 2 && !metadata.FromRetryQueue {
		logger.Warn("main queue message with elevated hop count - monitor for patterns",
			"hops", metadata.Hops,
			"hop_reason", metadata.HopReason,
			"destination_count", len(metadata.DestinationStates),
			"destination_status_counts", destStatusCounts)
	}
	if metadata.Hops >= 3 && metadata.FromRetryQueue {
		logger.Warn("retry queue message with elevated hop count - monitor for patterns",
			"hops", metadata.Hops,
			"hop_reason", metadata.HopReason,
			"destination_count", len(metadata.DestinationStates),
			"destination_status_counts", destStatusCounts)
	}
}

// extractAWSLineage safely extracts the AWS Lambda Lineage hop count from SQS record attributes.
// Returns (hopCount, err): LineageNotPresent (0) if no lineage, hopCount (>0) if found,
// or LineageExtractionError (-1) if extraction fails (should log but not block processing).
func extractAWSLineage(record *events.SQSMessage) (int, error) {
	if record == nil {
		return LineageNotPresent, nil
	}

	traceHeader, ok := record.Attributes["AWSTraceHeader"]
	if !ok {
		// Missing AWSTraceHeader is normal for non-recursive messages
		return LineageNotPresent, nil
	}

	if traceHeader == "" {
		// Empty header - indicates an issue
		return LineageExtractionError, fmt.Errorf("empty AWSTraceHeader")
	}

	// Parse regex: Lineage=[hash]:(\d+)
	// Example: "Root=1-...-...; Sampled=1; Lineage=43e12f0f:5"
	matches := lineageRe.FindStringSubmatch(traceHeader)
	if len(matches) < 2 {
		// Header exists but no Lineage key found - malformed
		return LineageExtractionError, fmt.Errorf("lineage key not found in trace header")
	}

	hopCount, err := strconv.Atoi(matches[1])
	if err != nil {
		// Parsing error
		return LineageExtractionError, fmt.Errorf("failed to parse lineage value: %w", err)
	}

	return hopCount, nil
}

// shouldDLQForLineageOverflow checks if message should be sent to DLQ due to AWS Lineage approaching the 16-hop limit.
func shouldDLQForLineageOverflow(logger *slog.Logger, awsLineage int, messageID string) bool {
	if awsLineage >= 15 {
		logger.Error("message approaching AWS Lambda 16-hop lineage limit - sending to DLQ",
			"aws_lineage", awsLineage,
			"message_id", messageID,
			"warning", "this indicates a recursive loop or deep service chain")
		return true
	}

	if awsLineage >= 12 {
		logger.Warn("message approaching AWS Lambda lineage limit",
			"aws_lineage", awsLineage,
			"message_id", messageID,
			"threshold_error", 15)
	}

	return false
}

// HandleLambdaEvent processes SQS messages from Lambda, extracting lineage and routing high-lineage messages to DLQ.
func (p *Processor) HandleLambdaEvent(ctx context.Context, event events.SQSEvent) (events.SQSEventResponse, error) {
	var (
		batchItemFailures = []events.SQSBatchItemFailure{}

		successfulRecords         = 0
		failedRecords             = 0
		undeliverableRecords      = 0
		totalSuccessfulDeliveries = 0
		totalFailedDeliveries     = 0
	)

	p.logger.Info("processing SQS messages", "message_count", len(event.Records))

	for _, record := range event.Records {
		// Extract AWS Lineage hop count for observability and safety
		awsLineage, err := extractAWSLineage(&record)
		if err != nil {
			p.logger.Warn("failed to extract AWS lineage from trace header",
				"message_id", record.MessageId,
				"error", err)
			// Continue processing despite lineage extraction failure (awsLineage = -1)
		}

		if awsLineage > LineageNotPresent && awsLineage != LineageExtractionError {
			p.logger.Info("processing message with AWS lineage",
				"aws_lineage", awsLineage,
				"message_id", record.MessageId)
		}

		// Circuit breaker: send to DLQ if approaching AWS 16-hop limit
		// Only check DLQ threshold if lineage was successfully extracted (not -1)
		if awsLineage != LineageExtractionError && shouldDLQForLineageOverflow(p.logger, awsLineage, record.MessageId) {
			p.logger.Error("lineage overflow detected - routing to DLQ for inspection",
				"aws_lineage", awsLineage,
				"message_id", record.MessageId)
			// TODO: evaluate if this is a reliable check, and messages should be sent to dlq
			// batchItemFailures = append(batchItemFailures, events.SQSBatchItemFailure{ItemIdentifier: record.MessageId})
			// undeliverableRecords++
			// continue
		}

		deliveryStats, err := p.ProcessSQSRecord(ctx, record.Body, record.MessageId, record.ReceiptHandle)

		if models.IsNonRecoverable(err) {
			// Non-recoverable errors should not be retried
			p.logger.Warn("non-recoverable error processing record, message will be removed from queue",
				"message_id", record.MessageId,
				"error", err)
			undeliverableRecords++
		} else if err != nil {
			// Recoverable errors should be retried
			p.logger.Error("recoverable error processing record, message will be retried",
				"message_id", record.MessageId,
				"error", err)
			failedRecords++

			batchItemFailures = append(batchItemFailures, events.SQSBatchItemFailure{
				ItemIdentifier: record.MessageId,
			})
		} else {
			successfulRecords++
			if deliveryStats != nil {
				totalSuccessfulDeliveries += deliveryStats.SuccessfulDeliveries
				totalFailedDeliveries += deliveryStats.FailedDeliveries
			}
		}
	}

	p.logger.Info("processing complete",
		"successful_records", successfulRecords,
		"failed_records", failedRecords,
		"undeliverable_records", undeliverableRecords,
		"successful_deliveries", totalSuccessfulDeliveries,
		"failed_deliveries", totalFailedDeliveries)

	return events.SQSEventResponse{
		BatchItemFailures: batchItemFailures,
	}, nil
}

// ProcessSQSRecord processes a single SQS record containing S3 event notification.
func (p *Processor) ProcessSQSRecord(ctx context.Context, messageBody, messageID, receiptHandle string) (*models.DeliveryStats, error) {
	deliveryStats := &models.DeliveryStats{}

	// Parse the SQS message body (SNS message)
	var snsMessage models.SNSMessage
	if err := json.Unmarshal([]byte(messageBody), &snsMessage); err != nil {
		return nil, models.NewInvalidS3NotificationError(fmt.Sprintf("invalid SQS message format: %v", err))
	}

	// Parse S3 event from SNS message
	var s3Event models.S3Event
	if err := json.Unmarshal([]byte(snsMessage.Message), &s3Event); err != nil {
		return nil, models.NewInvalidS3NotificationError(fmt.Sprintf("invalid S3 event format: %v", err))
	}

	// Extract the processing metadata from message body
	metadata, err := ExtractProcessingMetadata(messageBody)
	if err != nil {
		// Classify metadata extraction as a recoverable error: we wouldn't expect this to ever happen,
		// so, if it fails on automatic retry, should end up in the dead-letter queue for examination
		return deliveryStats, fmt.Errorf("failed to extract metadata from SQS message body: %w", err)
	}

	// Process each S3 record
	for _, s3Record := range s3Event.Records {
		bucketName := s3Record.S3.Bucket.Name
		objectKey, err := url.QueryUnescape(s3Record.S3.Object.Key)
		if err != nil {
			return nil, models.NewInvalidS3NotificationError(fmt.Sprintf("failed to unescape object key: %v", err))
		}

		p.logger.Info("processing S3 object",
			"bucket", bucketName,
			"key", objectKey)

		if err := p.processS3Object(ctx, bucketName, objectKey, messageBody, receiptHandle, metadata, deliveryStats); err != nil {
			// Check if error is non-recoverable
			if models.IsNonRecoverable(err) {
				p.logger.Warn("non-recoverable error processing S3 object, continuing",
					"object_key", objectKey,
					"error", err)
				continue
			}
			return deliveryStats, err
		}
	}

	return deliveryStats, nil
}

// processS3Object processes a single S3 object from a source bucket and delivers logs to tenant destinations.
func (p *Processor) processS3Object(ctx context.Context, bucketName, objectKey, messageBody, receiptHandle string, metadata *models.ProcessingMetadata, deliveryStats *models.DeliveryStats) error {
	// Check for suspicious hop counts
	checkHopThresholds(p.logger, metadata)

	// Extract tenant information from object key
	tenantInfo, err := ExtractTenantInfoFromKey(objectKey, p.logger)
	if err != nil {
		return err
	}

	// Get all enabled delivery configurations for this tenant
	deliveryConfigs, err := p.tenantConfig.GetEnabledDeliveryConfigs(ctx, tenantInfo.TenantID)
	if err != nil {
		return err
	}

	completedDeliveries := slices.Clone(metadata.CompletedDeliveries)
	var repairableErr error // Customer can fix (IAM, missing resources they can recreate)
	var transientErr error

	for _, deliveryConfig := range deliveryConfigs {
		deliveryType := deliveryConfig.Type

		if !deliveryConfig.ApplicationEnabled(tenantInfo.Application) {
			p.logger.Info("skipping delivery for application due to desired_logs filtering",
				"delivery_type", deliveryType,
				"application", tenantInfo.Application)
			continue
		}

		// Check if delivery already succeeded (either from CompletedDeliveries or DestinationStates)
		deliveryID := deliveryConfig.DeliveryID()
		if metadata.IsDeliveryCompleted(deliveryID) || isDestinationSucceeded(metadata, deliveryID) {
			// tenant_id and delivery_id are operational identifiers (namespace, bucket name),
			// not PII — logged throughout the codebase for observability.
			p.logger.Info("skipping already-completed delivery",
				"delivery_id", deliveryID,
				"tenant_id", tenantInfo.TenantID)
			deliveryStats.SuccessfulDeliveries++
			continue
		}

		p.logger.Info("processing delivery",
			"tenant_id", tenantInfo.TenantID,
			"delivery_type", deliveryType,
			"application", tenantInfo.Application)

		if err := p.deliverLogs(ctx, bucketName, objectKey, deliveryType, deliveryConfig, tenantInfo, metadata); err != nil {
			p.logger.Error("failed to deliver logs",
				"tenant_id", tenantInfo.TenantID,
				"delivery_type", deliveryType,
				"error", err)
			deliveryStats.FailedDeliveries++

			if models.IsNonRecoverable(err) {
				p.logger.Warn("non-recoverable delivery error, skipping",
					"delivery_type", deliveryType,
					"error", err)
				continue
			}

			if models.IsCustomerRepairableError(err) {
				repairableErr = err
			} else {
				transientErr = err
			}
			continue
		}

		completedDeliveries = append(completedDeliveries, deliveryConfig.DeliveryID())
		deliveryStats.SuccessfulDeliveries++
	}

	// Performance-optimized error routing:
	// Only call SendMessage when metadata needs updating OR first permission error from main queue.
	// Otherwise use native SQS retry (return error, stays in same queue).
	// This eliminates ~150ms SendMessage overhead for "no progress" retries.

	// Check if any new deliveries succeeded (metadata changed)
	metadataChanged := len(completedDeliveries) > len(metadata.CompletedDeliveries)

	if metadataChanged {
		// Partial success - metadata needs updating
		if repairableErr != nil {
			// Has permission errors - route to retry queue with updated metadata
			if receiptHandle != "" {
				if p.config.RetryQueueURL == "" {
					p.logger.Warn("permission error but no retry queue configured, returning error for native retry",
						"completed_deliveries", completedDeliveries)
					return fmt.Errorf("permission error with no retry queue configured: %w", repairableErr)
				}
				p.logger.Info("partial success with permission errors, updating retry queue metadata",
					"completed_deliveries", completedDeliveries)
				// Use WithMetadata variant to preserve hop counter for messages from retry queue
				if err := SendToRetryQueueWithMetadata(ctx, p.sqsClient, p.config.RetryQueueURL, messageBody, completedDeliveries, metadata.Hops, "partial_success_permission_error", nil, p.logger); err != nil {
					// Critical: SendMessage failed after successful delivery - duplicates possible!
					p.logger.Error("CRITICAL: failed to requeue after partial success, duplicates possible",
						"completed_deliveries", completedDeliveries,
						"error", err)
					return fmt.Errorf("failed to requeue after partial success: %w", err)
				}
				return nil
			}
		}
		// Partial success with only transient errors (or no errors on remaining targets)
		// Transient errors should retry quickly, but we need to preserve delivery progress.
		// Send updated message to main queue to preserve completedDeliveries - ONLY on first error.
		// CRITICAL: Never send messages from retry queue back to main queue - use native SQS retry instead
		if transientErr != nil && !metadata.FromRetryQueue {
			p.logger.Info("partial success with transient errors, persisting progress",
				"completed_deliveries", completedDeliveries)

			// Update message metadata with completed deliveries and destination states
			var messageData map[string]interface{}
			if err := json.Unmarshal([]byte(messageBody), &messageData); err != nil {
				p.logger.Error("failed to parse message for metadata update", "error", err)
				// Fall back to native retry - metadata will be lost but message will retry
				return fmt.Errorf("transient error after partial success: %w", transientErr)
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
			// Clear retry queue metadata when sending back to main queue
			// This ensures future permission errors can route to retry queue
			procMetadata["from_retry_queue"] = false
			delete(procMetadata, "sent_to_retry_queue_at")

			// Populate destination states to track which destinations succeeded/failed
			destinationStates := buildDestinationStates(completedDeliveries)
			procMetadata["destination_states"] = destinationStates
			procMetadata["hops"] = metadata.Hops + 1
			procMetadata["hop_reason"] = "transient_error_partial_success"

			updatedBody, err := json.Marshal(messageData)
			if err != nil {
				p.logger.Error("failed to marshal updated message", "error", err)
				return fmt.Errorf("transient error after partial success: %w", transientErr)
			}

			// Send to main queue with updated metadata
			_, err = p.sqsClient.SendMessage(ctx, &sqs.SendMessageInput{
				QueueUrl:    aws.String(p.config.SQSQueueURL),
				MessageBody: aws.String(string(updatedBody)),
			})
			if err != nil {
				// Critical: Failed to persist progress - duplicates possible!
				p.logger.Error("CRITICAL: failed to send to main queue after partial success, duplicates possible",
					"completed_deliveries", completedDeliveries,
					"error", err)
				return fmt.Errorf("failed to persist progress after partial success: %w", err)
			}

			// Successfully persisted progress - return success to delete original message
			p.logger.Info("persisted progress to main queue, original message will be deleted",
				"completed_deliveries", completedDeliveries,
				"hops", metadata.Hops+1)
			return nil
		}
		// Transient error from retry queue - use native SQS retry (stays in retry queue)
		if transientErr != nil && metadata.FromRetryQueue {
			p.logger.Info("partial success with transient errors from retry queue, using native SQS retry (2hr visibility)")
			return fmt.Errorf("transient error on delivery (retry queue, partial success): %w", transientErr)
		}
		// Any remaining transient error that wasn't persisted must be retried
		if transientErr != nil {
			p.logger.Info("unpersisted transient error after partial success, using native SQS retry")
			return fmt.Errorf("transient error on delivery (unpersisted, partial success): %w", transientErr)
		}
		// Partial success with no remaining errors
		return nil
	}

	// No metadata change (no new successes)
	if repairableErr != nil {
		if !metadata.FromRetryQueue {
			// First permission error from main queue - route to retry queue for 2hr visibility
			if receiptHandle != "" && p.config.RetryQueueURL != "" {
				p.logger.Info("first permission error from main queue, routing to retry queue")
				if err := SendToRetryQueue(ctx, p.sqsClient, p.config.RetryQueueURL, messageBody, completedDeliveries, p.logger); err != nil {
					p.logger.Error("failed to send to retry queue, falling back to native retry", "error", err)
					return fmt.Errorf("permission error on delivery: %w", repairableErr)
				}
				return nil
			}
			p.logger.Warn("permission error with no retry queue configured, using native retry")
			return fmt.Errorf("permission error on delivery: %w", repairableErr)
		}
		// Permission error from retry queue, no progress - use native SQS retry (stays in retry queue)
		p.logger.Info("permission error from retry queue with no progress, using native SQS retry (2hr visibility)")
		return fmt.Errorf("permission error on delivery (retry queue, no progress): %w", repairableErr)
	}

	if transientErr != nil {
		// Transient error, no progress - use native SQS retry (stays in current queue)
		p.logger.Info("transient error with no progress, using native SQS retry")
		return fmt.Errorf("transient error on delivery: %w", transientErr)
	}

	// No errors - success
	return nil
}

// deliverLogs handles log delivery based on type
func (p *Processor) deliverLogs(ctx context.Context, bucketName, objectKey, deliveryType string, deliveryConfig *models.DeliveryConfig, tenantInfo *models.TenantInfo, metadata *models.ProcessingMetadata) error {
	s3Obj, uploadTime, err := GetS3Object(ctx, p.s3Client, bucketName, objectKey, p.logger)
	if err != nil {
		return fmt.Errorf("failed to retrieve object %q from S3 bucket %q: %w", objectKey, bucketName, err)
	}
	p.logger.Info("downloaded S3 object", "unix_ts_obj_creation_time", uploadTime)

	switch deliveryType {
	case "cloudwatch":
		// CloudWatch requires downloading and processing log events
		logEvents, err := ProcessLogFile(ctx, objectKey, s3Obj, p.logger)
		if err != nil {
			p.metricsPublisher.PushCloudWatchDeliveryMetrics(ctx, tenantInfo.TenantID, 0, 1)
			return err
		}

		if metadata.Offset > 0 {
			p.logger.Info("found processing offset, skipping already processed events", "offset", metadata.Offset)
			logEvents = ShouldSkipProcessedEvents(logEvents, metadata.Offset, p.logger)
		}

		if len(logEvents) == 0 {
			p.logger.Info("all events already processed, skipping delivery")
			return nil
		}

		// Deliver to CloudWatch
		stats, err := p.cwDeliverer.DeliverLogs(ctx, logEvents, deliveryConfig, tenantInfo, uploadTime)
		if err != nil {
			p.metricsPublisher.PushCloudWatchDeliveryMetrics(ctx, tenantInfo.TenantID, 0, len(logEvents))
			return err
		}

		latency := (time.Now().UnixMilli() - uploadTime)
		p.metricsPublisher.PushCloudWatchLatencyMetrics(ctx, tenantInfo.TenantID, latency)
		p.metricsPublisher.PushCloudWatchDeliveryMetrics(ctx, tenantInfo.TenantID, stats.SuccessfulEvents, stats.FailedEvents)

	case "s3":
		// S3 delivery uses direct S3-to-S3 copy, no download needed
		if err := p.s3Deliverer.DeliverLogs(ctx, bucketName, objectKey, deliveryConfig, tenantInfo); err != nil {
			p.metricsPublisher.PushS3DeliveryMetrics(ctx, tenantInfo.TenantID, false)
			return err
		}
		latency := (time.Now().UnixMilli() - uploadTime)
		p.metricsPublisher.PushS3LatencyMetrics(ctx, tenantInfo.TenantID, latency)
		p.metricsPublisher.PushS3DeliveryMetrics(ctx, tenantInfo.TenantID, true)

	default:
		p.logger.Error("unknown delivery type, skipping",
			"tenant_id", tenantInfo.TenantID,
			"delivery_type", deliveryType)
		return nil
	}

	return nil
}
