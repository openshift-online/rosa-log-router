// Package processor implements the core log processing logic for SQS, Lambda, and S3 scan modes.
package processor

import (
	"context"
	"encoding/json"
	"fmt"
	"log/slog"
	"net/url"
	"slices"
	"strconv"
	"time"

	"github.com/aws/aws-lambda-go/events"
	"github.com/aws/aws-sdk-go-v2/aws"
	"github.com/aws/aws-sdk-go-v2/service/cloudwatch"
	"github.com/aws/aws-sdk-go-v2/service/s3"
	"github.com/aws/aws-sdk-go-v2/service/sqs"
	"github.com/aws/aws-sdk-go-v2/service/sqs/types"
	"github.com/aws/aws-sdk-go-v2/service/sts"
	awsmetrics "github.com/openshift/rosa-log-router/internal/aws"
	"github.com/openshift/rosa-log-router/internal/delivery"
	"github.com/openshift/rosa-log-router/internal/models"
	"github.com/openshift/rosa-log-router/internal/tenant"
)

// AWS Lineage constants

// Processor handles log processing and delivery
type Processor struct {
	s3Client         *s3.Client
	sqsClient        SQSClientAPI
	tenantConfig     *tenant.ConfigManager
	cwDeliverer      *delivery.CloudWatchDeliverer
	s3Deliverer      *delivery.S3Deliverer
	metricsPublisher *awsmetrics.MetricsPublisher
	config           *models.Config
	logger           *slog.Logger

	// Queue visibility defaults (queried once at startup from AWS)
	mainQueueVisibility  int32
	retryQueueVisibility int32
}

// NewProcessor creates a new log processor
func NewProcessor(
	s3Client *s3.Client,
	dynamoClient tenant.DynamoDBQueryAPI,
	sqsClient SQSClientAPI,
	stsClient *sts.Client,
	cwClient *cloudwatch.Client,
	endpointURL string,
	config *models.Config,
	logger *slog.Logger,
) *Processor {
	// Query queue visibility timeouts from AWS at startup (single source of truth)
	mainVis, retryVis := queryQueueVisibilityDefaults(sqsClient, config, logger)

	return &Processor{
		s3Client:             s3Client,
		sqsClient:            sqsClient,
		tenantConfig:         tenant.NewConfigManager(dynamoClient, config.TenantConfigTable, logger),
		cwDeliverer:          delivery.NewCloudWatchDeliverer(stsClient, config.CentralLogDistributionRoleArn, endpointURL, logger),
		s3Deliverer:          delivery.NewS3Deliverer(stsClient, config.CentralLogDistributionRoleArn, config.S3UsePathStyle, endpointURL, logger),
		metricsPublisher:     awsmetrics.NewMetricsPublisher(cwClient, logger),
		config:               config,
		logger:               logger,
		mainQueueVisibility:  mainVis,
		retryQueueVisibility: retryVis,
	}
}

// queryQueueVisibilityDefaults queries AWS for queue visibility timeouts at startup.
// This ensures we have the actual configured values as our single source of truth.
func queryQueueVisibilityDefaults(sqsClient SQSClientAPI, config *models.Config, logger *slog.Logger) (mainVis, retryVis int32) {
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	// Cast to concrete type to access GetQueueAttributes (not in our interface)
	// If using mock in tests, return defaults
	concreteClient, ok := sqsClient.(*sqs.Client)
	if !ok {
		logger.Warn("SQS client is not *sqs.Client (likely mock), using default visibility timeouts",
			"main_default", 900,
			"retry_default", 7200)
		return 900, 7200
	}

	// Query main queue
	if config.SQSQueueURL != "" {
		mainAttrs, err := concreteClient.GetQueueAttributes(ctx, &sqs.GetQueueAttributesInput{
			QueueUrl:       aws.String(config.SQSQueueURL),
			AttributeNames: []types.QueueAttributeName{types.QueueAttributeNameVisibilityTimeout},
		})
		if err != nil {
			logger.Warn("failed to query main queue visibility, using default 900s", "error", err)
			mainVis = 900
		} else if visStr, exists := mainAttrs.Attributes["VisibilityTimeout"]; exists {
			if vis, err := strconv.ParseInt(visStr, 10, 32); err == nil {
				mainVis = int32(vis)
				logger.Info("queried main queue visibility timeout", "visibility_seconds", mainVis)
			} else {
				logger.Warn("failed to parse main queue visibility, using default 900s", "error", err)
				mainVis = 900
			}
		}
	} else {
		mainVis = 900 // Default if no main queue configured
	}

	// Query retry queue
	if config.RetryQueueURL != "" {
		retryAttrs, err := concreteClient.GetQueueAttributes(ctx, &sqs.GetQueueAttributesInput{
			QueueUrl:       aws.String(config.RetryQueueURL),
			AttributeNames: []types.QueueAttributeName{types.QueueAttributeNameVisibilityTimeout},
		})
		if err != nil {
			logger.Warn("failed to query retry queue visibility, using default 7200s", "error", err)
			retryVis = 7200
		} else if visStr, exists := retryAttrs.Attributes["VisibilityTimeout"]; exists {
			if vis, err := strconv.ParseInt(visStr, 10, 32); err == nil {
				retryVis = int32(vis)
				logger.Info("queried retry queue visibility timeout", "visibility_seconds", retryVis)
			} else {
				logger.Warn("failed to parse retry queue visibility, using default 7200s", "error", err)
				retryVis = 7200
			}
		}
	} else {
		retryVis = 7200 // Default if no retry queue configured
	}

	return mainVis, retryVis
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

// getReceiveCount extracts the approximate number of times this message has been received from the queue.
// This value is used for progressive backoff calculations in the retry queue.
//
// Returns:
//   - The receive count as an integer (1-based)
//   - Defaults to 1 if the attribute is not found or cannot be parsed
//
// Note: ApproximateReceiveCount is a system-managed SQS attribute that increments
// with each receive (including receives that result in visibility timeout expiration).
func getReceiveCount(record events.SQSMessage) int {
	if countStr, exists := record.Attributes["ApproximateReceiveCount"]; exists {
		if count, err := strconv.Atoi(countStr); err == nil {
			return count
		}
	}
	// Default to 1 for first receive
	return 1
}

// applyProgressiveBackoff implements progressive backoff for permission errors.
// Transient errors use queue defaults. Permission errors get progressive backoff tiers
// to give customers time to fix IAM permissions, API keys, etc.
//
// Backoff progression for permission errors:
//   - Receive 1: 30 minutes  (config: PermissionBackoffTier1, default 1800s)
//   - Receive 2: 60 minutes  (config: PermissionBackoffTier2, default 3600s)
//   - Receive 3+: 120 minutes (config: PermissionBackoffTier3, default 7200s)
//
// Transient errors always use queue default visibility (no ChangeMessageVisibility call).
//
// Optimization: Skips ChangeMessageVisibility if desired backoff == queue default.
//
// Parameters:
//   - ctx: Context for the API call
//   - queueURL: URL of the queue (main or retry)
//   - receiptHandle: Receipt handle of the message
//   - receiveCount: Number of times message has been received (from ApproximateReceiveCount)
//   - isPermissionError: true for permission errors, false for transient errors
//   - queueDefaultVisibility: Queue's configured default visibility timeout (queried at startup)
func (p *Processor) applyProgressiveBackoff(ctx context.Context, queueURL, receiptHandle string, receiveCount int, isPermissionError bool, queueDefaultVisibility int32) {
	if receiptHandle == "" {
		p.logger.Debug("cannot apply progressive backoff without receipt handle")
		return
	}

	// Transient errors: always use queue default (no CMV)
	if !isPermissionError {
		p.logger.Debug("transient error, using queue default visibility",
			"queue_default", queueDefaultVisibility)
		return
	}

	// Permission errors: calculate desired backoff
	var desiredTimeout int32
	switch receiveCount {
	case 1:
		desiredTimeout = p.config.PermissionBackoffTier1 // Default: 1800s (30 min)
	case 2:
		desiredTimeout = p.config.PermissionBackoffTier2 // Default: 3600s (60 min)
	default:
		desiredTimeout = p.config.PermissionBackoffTier3 // Default: 7200s (120 min)
	}

	// Optimization: skip CMV if desired equals queue default
	if desiredTimeout == queueDefaultVisibility {
		p.logger.Debug("desired backoff matches queue default, skipping CMV",
			"desired", desiredTimeout,
			"receive_count", receiveCount)
		return
	}

	// Override queue default with progressive backoff
	_, err := p.sqsClient.ChangeMessageVisibility(ctx, &sqs.ChangeMessageVisibilityInput{
		QueueUrl:          aws.String(queueURL),
		ReceiptHandle:     aws.String(receiptHandle),
		VisibilityTimeout: desiredTimeout,
	})

	if err != nil {
		p.logger.Warn("failed to apply progressive backoff, will use queue default",
			"error", err,
			"desired", desiredTimeout,
			"queue_default", queueDefaultVisibility,
			"receive_count", receiveCount)
		return
	}

	p.logger.Debug("applied progressive backoff",
		"timeout_seconds", desiredTimeout,
		"receive_count", receiveCount)
}

// HandleLambdaEvent processes SQS messages from Lambda.
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
		deliveryStats, err := p.ProcessSQSRecord(ctx, record.Body, record.MessageId, record.ReceiptHandle, getReceiveCount(record))

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
func (p *Processor) ProcessSQSRecord(ctx context.Context, messageBody, messageID, receiptHandle string, receiveCount int) (*models.DeliveryStats, error) {
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

		if err := p.processS3Object(ctx, bucketName, objectKey, messageBody, receiptHandle, receiveCount, metadata, deliveryStats); err != nil {
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
func (p *Processor) processS3Object(ctx context.Context, bucketName, objectKey, messageBody, receiptHandle string, receiveCount int, metadata *models.ProcessingMetadata, deliveryStats *models.DeliveryStats) error {
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

	// ============================================================================
	// RETRY STATE MACHINE - PARTIAL SUCCESS PATH
	// ============================================================================
	// Partial success means some log destinations succeeded while others failed.
	// This requires preserving metadata to prevent duplicate log deliveries.
	//
	// STATE TRANSITIONS:
	//   Main Queue (partial success) → Retry Queue: SendMessage with updated metadata
	//   Retry Queue (partial success) → Retry Queue: Native retry + progressive backoff
	//
	// CRITICAL: This is the ONLY scenario where we use SendMessage.
	// Both permission errors AND transient errors follow the same path when
	// partial success occurs - the error type doesn't matter, what matters is
	// preserving the list of successful deliveries in metadata.
	//
	// HOP COUNT SAFETY:
	//   - SendMessage increments hop count by +1 (bounded at hop=2)
	//   - Native retry increments hop count by +0
	//   - ChangeMessageVisibility increments hop count by +0
	// ============================================================================

	// Check if any new deliveries succeeded (metadata changed)
	metadataChanged := len(completedDeliveries) > len(metadata.CompletedDeliveries)

	if metadataChanged {
		// ========================================================================
		// PARTIAL SUCCESS DETECTED
		// Some destinations succeeded, some failed.
		// Must preserve successful deliveries to prevent duplicate log entries.
		// ========================================================================

		// Determine error type for logging/observability
		var errorType string
		var lastErr error
		if repairableErr != nil {
			errorType = "permission"
			lastErr = repairableErr
		} else if transientErr != nil {
			errorType = "transient"
			lastErr = transientErr
		}

		if !metadata.FromRetryQueue {
			// ====================================================================
			// FROM MAIN QUEUE: Send to retry queue to preserve metadata
			// ====================================================================
			// Partial success from main queue - ALWAYS send to retry queue.
			// This is the ONLY case where we use SendMessage.
			//
			// Why: We need to update message metadata with the list of successful
			// deliveries. Can't update metadata in the same queue without SendMessage.
			//
			// Error type doesn't matter: Whether remaining failures are permission
			// errors (customer needs to fix IAM) or transient errors (network issues),
			// we still need to preserve the progress already made.
			//
			// STATE TRANSITION: main → retry queue (SendMessage)
			// HOP INCREMENT: +1
			// COST: 1 SendMessage API call (~$0.0000004)
			// ====================================================================

			if receiptHandle != "" {
				if p.config.RetryQueueURL == "" {
					p.logger.Warn("partial success but no retry queue configured, using native retry (metadata may be lost)",
						"completed_delivery_count", len(completedDeliveries),
						"error_type", errorType)
					// Fall back to native retry - accept small duplicate risk
					return fmt.Errorf("partial success with %s error, no retry queue: %w", errorType, lastErr)
				}

				// Determine hop reason based on error type (for observability)
				hopReason := "partial_success"
				if errorType == "permission" {
					hopReason = "partial_success_permission_error"
				} else if errorType == "transient" {
					hopReason = "partial_success_transient_error"
				}

				p.logger.Info("partial success from main queue, sending to retry queue to preserve metadata",
					"completed_delivery_count", len(completedDeliveries),
					"error_type", errorType,
					"hop_reason", hopReason)

				// Use WithMetadata variant to preserve hop counter
				if err := SendToRetryQueueWithMetadata(ctx, p.sqsClient, p.config.RetryQueueURL, messageBody, completedDeliveries, metadata.Hops, hopReason, nil, p.logger); err != nil {
					// CRITICAL: SendMessage failed after successful delivery
					// Some destinations already received logs, but message still in main queue
					// Retrying from main queue will cause duplicate deliveries
					p.logger.Error("CRITICAL: failed to requeue after partial success, duplicates possible",
						"completed_delivery_count", len(completedDeliveries),
						"error_type", errorType,
						"error", err)
					return fmt.Errorf("failed to requeue after partial success: %w", err)
				}

				// Successfully sent to retry queue - delete original from main queue
				return nil
			}
		}

		// ====================================================================
		// FROM RETRY QUEUE: Native retry with progressive backoff
		// ====================================================================
		// Partial success from retry queue - use native retry.
		// Cannot update metadata without SendMessage, but we already have
		// the successful deliveries preserved from when we first moved to
		// retry queue.
		//
		// Progressive backoff gives customer time between retry attempts:
		//   Recv 1: 30 min (customer likely still fixing issues)
		//   Recv 2: 60 min (customer may need more time)
		//   Recv 3+: 2 hr (queue default - issue is persistent)
		//
		// STATE TRANSITION: retry queue → retry queue (native retry)
		// HOP INCREMENT: +0
		// COST: Up to 2 ChangeMessageVisibility API calls (~$0.0000008)
		// ====================================================================

		if metadata.FromRetryQueue {
			// ====================================================================
			// Partial success from retry queue - use native retry.
			//
			// NOTE: With 2 destinations (S3 + CloudWatch), partial success means
			// exactly 1 succeeded and 1 failed. On retry queue receive, we only
			// attempt the 1 failed destination. No duplicate risk because:
			// - If it succeeds: completedDeliveries = both, done
			// - If it fails: completedDeliveries unchanged, retry same state
			//
			// Future: If >2 destinations are added, this may need enhancement
			// (additional queues or external state persistence).
			// ====================================================================

			// Apply progressive backoff based on error type
			// Permission errors: 30min → 60min → 120min
			// Transient errors: use queue default (queried at startup)
			p.applyProgressiveBackoff(ctx, p.config.RetryQueueURL, receiptHandle, receiveCount, repairableErr != nil, p.retryQueueVisibility)

			// Return error to trigger native SQS retry (message stays in retry queue)
			if repairableErr != nil {
				p.logger.Info("partial success with permission errors from retry queue, using native retry",
					"receive_count", receiveCount,
					"completed_delivery_count", len(completedDeliveries))
				return fmt.Errorf("permission error (retry queue, partial success): %w", repairableErr)
			}
			if transientErr != nil {
				p.logger.Info("partial success with transient errors from retry queue, using native retry",
					"receive_count", receiveCount,
					"completed_delivery_count", len(completedDeliveries))
				return fmt.Errorf("transient error (retry queue, partial success): %w", transientErr)
			}
		}

		// Partial success with no remaining errors - all deliveries succeeded
		// BUT: if we still have errors and skipped all branches above, return the error
		if lastErr != nil {
			p.logger.Warn("partial success with errors but no receipt handle to requeue",
				"error_type", errorType,
				"completed_delivery_count", len(completedDeliveries))
			return fmt.Errorf("partial success with %s error: %w", errorType, lastErr)
		}
		return nil
	}

	// No metadata change (no new successes) - total failure
	// All destinations failed - use native retry in current queue
	if repairableErr != nil {
		// Permission errors get progressive backoff in both queues
		// (customer needs time to fix IAM permissions)
		queueURL := p.config.SQSQueueURL
		queueVisibility := p.mainQueueVisibility
		if metadata.FromRetryQueue {
			queueURL = p.config.RetryQueueURL
			queueVisibility = p.retryQueueVisibility
		}

		p.applyProgressiveBackoff(ctx, queueURL, receiptHandle, receiveCount, true, queueVisibility)
		p.logger.Info("permission error with no progress, using native retry",
			"receive_count", receiveCount,
			"from_retry_queue", metadata.FromRetryQueue)
		return fmt.Errorf("permission error on delivery: %w", repairableErr)
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
