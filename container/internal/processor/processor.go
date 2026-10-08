// Package processor implements the core log processing logic for SQS, Lambda, and S3 scan modes.
package processor

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"log/slog"
	"net/url"
	"slices"
	"strings"
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

// Queue type constants
const (
	QueueTypeMain    = "main"
	QueueTypeRetry   = "retry"
	QueueTypePartial = "partial"
	QueueTypeUnknown = "unknown"
)

// SQS receive count constants
// These align with the maxReceiveCount configured in Terraform for each queue
const (
	MaxReceiveCount = 3 // All queues use maxReceiveCount=3
)

// messageRoutingState holds accumulated routing state for all records in a message
type messageRoutingState struct {
	completedDeliveries []string // All deliveries that succeeded across all records
	repairableErr       error    // Any end-user-fixable error (IAM permissions, missing resources in their account)
	transientErr        error    // Any transient error encountered
}

// getReceiveCount extracts ApproximateReceiveCount from SQS message attributes
func getReceiveCount(record events.SQSMessage) int {
	if countStr, ok := record.Attributes["ApproximateReceiveCount"]; ok {
		var count int
		if _, err := fmt.Sscanf(countStr, "%d", &count); err == nil {
			return count
		}
	}
	return 0
}

// getCurrentQueue detects which queue the message came from using eventSourceARN
func getCurrentQueue(eventSourceARN string) string {
	if eventSourceARN == "" {
		return QueueTypeUnknown
	}

	// Check for partial queue first (most specific suffix)
	// Example ARN: arn:aws:sqs:us-east-1:123456789012:hcp-log-int-log-delivery-partial-queue
	if strings.HasSuffix(eventSourceARN, "log-delivery-partial-queue") {
		return QueueTypePartial
	}

	// Check for retry queue
	// Example ARN: arn:aws:sqs:us-east-1:123456789012:hcp-log-int-log-delivery-retry-queue
	if strings.HasSuffix(eventSourceARN, "log-delivery-retry-queue") {
		return QueueTypeRetry
	}

	// Check for main queue (base name - must be last check to avoid false positives)
	// Example ARN: arn:aws:sqs:us-east-1:123456789012:hcp-log-int-log-delivery-queue
	// Must check this last because "log-delivery-queue" is a suffix of both retry and partial queues
	if strings.HasSuffix(eventSourceARN, "log-delivery-queue") {
		return QueueTypeMain
	}

	return QueueTypeUnknown
}

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
		// Extract receive count and current queue for routing decisions
		receiveCount := getReceiveCount(record)
		currentQueue := getCurrentQueue(record.EventSourceARN)

		deliveryStats, err := p.ProcessSQSRecord(ctx, record.Body, record.MessageId, record.ReceiptHandle, receiveCount, currentQueue)

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
func (p *Processor) ProcessSQSRecord(ctx context.Context, messageBody, messageID, receiptHandle string, receiveCount int, currentQueue string) (*models.DeliveryStats, error) {
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
		return nil, fmt.Errorf("failed to extract metadata from SQS message body: %w", err)
	}

	// Initialize message-level routing state (accumulates across all S3 records in this message)
	routingState := &messageRoutingState{
		completedDeliveries: slices.Clone(metadata.CompletedDeliveries),
	}

	// Process each S3 record
	// CRITICAL: Continue processing all records even if some fail (preserves partial progress)
	// Returning early would lose successful deliveries from already-processed records
	var recordErrors []error
	for _, s3Record := range s3Event.Records {
		bucketName := s3Record.S3.Bucket.Name
		objectKey, err := url.QueryUnescape(s3Record.S3.Object.Key)
		if err != nil {
			return nil, models.NewInvalidS3NotificationError(fmt.Sprintf("failed to unescape object key: %v", err))
		}

		p.logger.Info("processing S3 object",
			"bucket", bucketName,
			"key", objectKey)

		if err := p.processS3Object(ctx, bucketName, objectKey, metadata, deliveryStats, routingState); err != nil {
			// Check if error is non-recoverable
			if models.IsNonRecoverable(err) {
				p.logger.Warn("non-recoverable error processing S3 object, continuing",
					"object_key", objectKey,
					"error", err)
				continue
			}
			// Recoverable error: accumulate and continue processing remaining records
			// This preserves successful deliveries from earlier records
			p.logger.Warn("recoverable error processing S3 object, continuing to preserve partial progress",
				"object_key", objectKey,
				"error", err)
			recordErrors = append(recordErrors, fmt.Errorf("record %s: %w", objectKey, err))

			// Classify infrastructure error for routing logic
			// (processS3Object only sets routingState errors for delivery failures,
			// not for infrastructure errors like GetS3Object/HeadObject failures)
			if models.IsCustomerRepairableError(err) {
				routingState.repairableErr = err
			} else {
				routingState.transientErr = err
			}
			continue
		}
	}

	// If any record-level errors occurred, they're already accumulated in routingState
	// (transientErr/repairableErr set by processS3Object's delivery failures)
	// No need to return early - routing logic below will handle them
	if len(recordErrors) > 0 {
		p.logger.Info("completed processing with record-level errors, proceeding to routing",
			"record_error_count", len(recordErrors),
			"successful_deliveries", len(routingState.completedDeliveries))
	}

	// State-based 3-queue routing logic (executes once per message after processing all records)
	//
	// Architecture note:
	// Production has 2 destinations (S3 + CloudWatch). The 3-queue architecture supports
	// N destinations via DestinationStates metadata. Queue parameters (maxReceiveCount=3)
	// assume partial success resolves quickly (typical when N is small).
	//
	// Queue behaviors:
	// - Main queue: Initial processing, routes to Q2 (permission errors recv≥2) or Q3 (partial success)
	// - Retry queue (Q2): Permission errors with longer backoff, can route to Q3 (partial success)
	// - Partial queue (Q3): Terminal queue for partial success (≥1 succeeded, ≥1 failed)
	//                       Messages deleted only when ALL destinations succeed
	//                       No SendMessage routing from Q3 (loop prevention)

	// Unknown queue safety check: disable routing if we can't determine source queue
	// CRITICAL: Cannot route when queue is unknown - could create loops (Q2→Q2, Q3→Q3)
	// and trigger RecursiveInvocationsDropped via lineage hop inheritance.
	// Use native retry only (safer than guessing).
	if currentQueue == QueueTypeUnknown {
		p.logger.Error("unable to determine source queue, routing disabled - using native retry only",
			"completed_delivery_count", len(routingState.completedDeliveries))
		// Return errors to trigger native retry in actual queue (wherever it is)
		// If this persists, message goes to source queue's DLQ for investigation
		if routingState.repairableErr != nil {
			return nil, fmt.Errorf("permission error with unknown source queue: %w", routingState.repairableErr)
		}
		if routingState.transientErr != nil {
			return nil, fmt.Errorf("transient error with unknown source queue: %w", routingState.transientErr)
		}
		// All deliveries succeeded - delete message
		return deliveryStats, nil
	}

	// Check if any new deliveries succeeded (metadata changed)
	metadataChanged := len(routingState.completedDeliveries) > len(metadata.CompletedDeliveries)

	// Priority 1: Partial success → Q3 (partial queue) - only from main or Q2
	// Preserves progress by tracking completed deliveries in metadata
	// Production: typically 1 of 2 destinations succeeded, 1 failed
	// Only route to Q3 if errors remain - fully successful messages just return nil (delete)
	//
	// Duplicate delivery trade-off:
	//   Risk: If SendMessage succeeds but Lambda fails before deleting original message,
	//         the message reappears in source queue → duplicate delivery to Q3
	//   Mitigation: Bounded by maxReceiveCount (3 attempts max) → moves to DLQ
	//   Alternative: Native retry loses completed delivery progress → worse user experience
	//   Rationale: Bounded duplicates < unbounded data loss from RecursiveInvocationsDropped
	if metadataChanged && currentQueue != QueueTypePartial && (routingState.repairableErr != nil || routingState.transientErr != nil) {
		// At least one delivery succeeded - route to partial queue to preserve progress
		if p.config.PartialQueueURL == "" {
			p.logger.Warn("partial success but no partial queue configured, using native retry (may lose progress)",
				"completed_delivery_count", len(routingState.completedDeliveries))
			if routingState.repairableErr != nil {
				return nil, fmt.Errorf("permission error after partial success: %w", routingState.repairableErr)
			}
			if routingState.transientErr != nil {
				return nil, fmt.Errorf("transient error after partial success: %w", routingState.transientErr)
			}
			return deliveryStats, nil
		}

		p.logger.Info("partial success detected, routing to partial queue",
			"completed_delivery_count", len(routingState.completedDeliveries),
			"receive_count", receiveCount,
			"current_queue", currentQueue)

		if err := SendToPartialQueueWithMetadata(ctx, p.sqsClient, p.config.PartialQueueURL, messageBody, routingState.completedDeliveries, metadata.Hops, "partial_success", p.logger); err != nil {
			// Critical: SendMessage failed after successful delivery - duplicates possible!
			p.logger.Error("CRITICAL: failed to send to partial queue after partial success, duplicates possible",
				"completed_delivery_count", len(routingState.completedDeliveries),
				"error", err)
			return nil, fmt.Errorf("failed to route to partial queue after partial success: %w", err)
		}
		return deliveryStats, nil
	}

	// Priority 2: Total failure + retryable + main queue + recv >= 2 → Q2 (retry queue)
	if !metadataChanged && routingState.repairableErr != nil && currentQueue == QueueTypeMain && receiveCount >= (MaxReceiveCount-1) {
		// Permission error from main queue after 2 attempts - route to retry queue for longer backoff
		if p.config.RetryQueueURL == "" {
			p.logger.Warn("retryable error after 2 attempts but no retry queue configured, using native retry",
				"receive_count", receiveCount)
			return nil, fmt.Errorf("permission error on delivery: %w", routingState.repairableErr)
		}

		p.logger.Info("retryable error from main queue after 2 attempts, routing to retry queue",
			"receive_count", receiveCount,
			"error_type", "permission")

		if err := SendToRetryQueue(ctx, p.sqsClient, p.config.RetryQueueURL, messageBody, routingState.completedDeliveries, p.logger); err != nil {
			p.logger.Error("failed to send to retry queue, falling back to native retry", "error", err)
			return nil, fmt.Errorf("permission error on delivery: %w", routingState.repairableErr)
		}
		return deliveryStats, nil
	}

	// Priority 3: All other cases → Native retry (stay in current queue)

	// Partial queue (Q3) special handling:
	// Q3 is a terminal queue for partial success - no SendMessage routing, only native retry
	// Assumption: Production has 2 destinations (S3 + CloudWatch)
	// - Message entered Q3 because ≥1 delivery succeeded, ≥1 delivery failed
	// - DestinationStates tracks which deliveries succeeded (skipped on retry)
	// - Message deleted ONLY when ALL destinations succeed
	// - Any remaining error → native retry in Q3 until maxReceiveCount → DLQ
	//
	// KNOWN LIMITATION (accepted trade-off):
	// If NEW progress is made in Q3 (rare: multi-record message + mixed success), native retry
	// uses original message body → new completions lost → possible duplicates on next retry.
	// This is RARE because:
	//   1. Most messages have 1 S3 record (Vector batches per file)
	//   2. Same destination type fails/succeeds together (IAM-based)
	//   3. End user fixes IAM → all pending S3 succeed → no new partial state
	// Trade-off: Bounded duplicates (maxReceiveCount=3) < RecursiveInvocationsDropped data loss
	// Alternative (SendMessage Q3→Q3) would increment X-Ray hops → hit 16-hop limit → data loss
	if currentQueue == QueueTypePartial {
		if routingState.repairableErr != nil {
			p.logger.Info("permission error in partial queue, using native retry",
				"receive_count", receiveCount,
				"completed_delivery_count", len(routingState.completedDeliveries))
			return nil, fmt.Errorf("permission error in partial queue: %w", routingState.repairableErr)
		}
		if routingState.transientErr != nil {
			p.logger.Info("transient error in partial queue, using native retry",
				"receive_count", receiveCount,
				"completed_delivery_count", len(routingState.completedDeliveries))
			return nil, fmt.Errorf("transient error in partial queue: %w", routingState.transientErr)
		}
		// All deliveries succeeded - delete message
		p.logger.Info("all deliveries succeeded in partial queue, deleting message",
			"completed_delivery_count", len(routingState.completedDeliveries))
		return deliveryStats, nil
	}

	// Retryable error from main queue, recv < (MaxReceiveCount-1): native retry in main queue
	if !metadataChanged && routingState.repairableErr != nil && currentQueue == QueueTypeMain && receiveCount < (MaxReceiveCount-1) {
		p.logger.Info("retryable error from main queue, using native retry",
			"receive_count", receiveCount,
			"error_type", "permission")
		return nil, fmt.Errorf("permission error on delivery: %w", routingState.repairableErr)
	}

	// Retry queue (Q2) with permission error: native retry
	// (Q3 already handled above, so currentQueue != QueueTypeMain means Q2 here)
	if !metadataChanged && routingState.repairableErr != nil && currentQueue != QueueTypeMain {
		p.logger.Info("permission error in retry queue, using native retry",
			"receive_count", receiveCount,
			"current_queue", currentQueue)
		return nil, fmt.Errorf("permission error in retry queue: %w", routingState.repairableErr)
	}

	// Transient error: always native retry (stay in current queue)
	if routingState.transientErr != nil {
		p.logger.Info("transient error, using native retry",
			"receive_count", receiveCount,
			"current_queue", currentQueue,
			"metadata_changed", metadataChanged)
		return nil, fmt.Errorf("transient error on delivery: %w", routingState.transientErr)
	}

	// No errors - success
	return deliveryStats, nil
}

// processS3Object processes a single S3 object from a source bucket and delivers logs to tenant destinations.
// Accumulates routing state in routingState (completed deliveries and errors) without executing routing.
func (p *Processor) processS3Object(ctx context.Context, bucketName, objectKey string, metadata *models.ProcessingMetadata, deliveryStats *models.DeliveryStats, routingState *messageRoutingState) error {
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

	// Check if any CloudWatch deliveries are pending (not already completed)
	// CloudWatch deliveries require downloading the S3 object to parse log events
	// S3 deliveries use direct S3-to-S3 copy and don't need the object in memory
	needsDownload := false
	for _, config := range deliveryConfigs {
		if config.Type == "cloudwatch" {
			baseDeliveryID := config.DeliveryID()
			if baseDeliveryID == "" {
				// No deliveryID - can't check completion, must download
				needsDownload = true
				break
			}

			// Scope by objectKey to match completion tracking (Finding #5 fix)
			// Without this, lazy download check uses base ID but metadata has scoped ID,
			// causing unnecessary downloads of already-completed records
			scopedDeliveryID := fmt.Sprintf("%s:%s", baseDeliveryID, objectKey)

			// Check BOTH scoped and legacy formats for backward compatibility
			// Legacy metadata uses base format, new metadata uses scoped format
			isCompleted := metadata.IsDeliveryCompleted(scopedDeliveryID) || isDestinationSucceeded(metadata, scopedDeliveryID) ||
				metadata.IsDeliveryCompleted(baseDeliveryID) || isDestinationSucceeded(metadata, baseDeliveryID)

			if !isCompleted {
				needsDownload = true
				break
			}
		}
	}

	var objData []byte
	var uploadTime int64

	if needsDownload {
		// Download S3 object for CloudWatch deliveries
		// LimitReader protects against OOM by capping read at MaxReadBytes
		s3Obj, objUploadTime, err := GetS3Object(ctx, p.s3Client, bucketName, objectKey, p.logger)
		if err != nil {
			return fmt.Errorf("failed to retrieve object %q from S3 bucket %q: %w", objectKey, bucketName, err)
		}
		uploadTime = objUploadTime

		// Read with size limit to prevent OOM crashes
		// LimitReader stops at MaxReadBytes+1 to detect oversized objects
		objData, err = io.ReadAll(io.LimitReader(s3Obj, p.config.MaxReadBytes+1))
		s3Obj.Close()
		if err != nil {
			return fmt.Errorf("failed to read object data: %w", err)
		}

		// Detect oversized objects (should be rare - Vector batches max 64MB)
		if int64(len(objData)) > p.config.MaxReadBytes {
			// Best-effort HeadObject to get actual size for better error reporting
			// Don't fail if HeadObject fails - we already know the object is too large
			actualSize := int64(-1)
			if headResult, err := p.s3Client.HeadObject(ctx, &s3.HeadObjectInput{
				Bucket: aws.String(bucketName),
				Key:    aws.String(objectKey),
			}); err == nil && headResult.ContentLength != nil {
				actualSize = *headResult.ContentLength
			}

			// Log error without sensitive info (no object key, bucket name, or ARNs)
			// tenant_id is operational identifier (namespace), safe to log per existing patterns
			p.logger.Error("S3 object exceeds size limit",
				"tenant_id", tenantInfo.TenantID,
				"actual_size_bytes", actualSize,
				"max_allowed_bytes", p.config.MaxReadBytes,
				"read_bytes", len(objData))

			return models.NewNonRecoverableError(
				fmt.Sprintf("S3 object size exceeds maximum allowed %d bytes (Vector batches 64MB max)", p.config.MaxReadBytes))
		}

		p.logger.Info("downloaded S3 object for CloudWatch delivery",
			"size_bytes", len(objData),
			"unix_ts_obj_creation_time", uploadTime)
	} else {
		// Only S3 deliveries pending - use HeadObject to get metadata without downloading
		headResult, err := p.s3Client.HeadObject(ctx, &s3.HeadObjectInput{
			Bucket: aws.String(bucketName),
			Key:    aws.String(objectKey),
		})
		if err != nil {
			return fmt.Errorf("failed to get S3 object metadata for %q: %w", objectKey, err)
		}
		// Safely handle nil LastModified (shouldn't happen, but prevents panic)
		if headResult.LastModified != nil {
			uploadTime = headResult.LastModified.UnixMilli()
		} else {
			uploadTime = time.Now().UnixMilli()
			p.logger.Warn("S3 HeadObject returned nil LastModified, using current time")
		}

		p.logger.Info("skipped S3 object download (only S3 deliveries pending)",
			"unix_ts_obj_creation_time", uploadTime)
	}

	for _, deliveryConfig := range deliveryConfigs {
		deliveryType := deliveryConfig.Type

		if !deliveryConfig.ApplicationEnabled(tenantInfo.Application) {
			p.logger.Info("skipping delivery for application due to desired_logs filtering",
				"delivery_type", deliveryType,
				"application", tenantInfo.Application)
			continue
		}

		// Get deliveryID for metadata tracking
		// Scope deliveryID by objectKey to distinguish deliveries across multiple S3 records
		// in the same SQS message (e.g., 3 log files from same cluster = 3 records)
		// Without this, only the first record gets delivered on retry (other records see
		// "s3:bucket" as completed and skip, even though they're different files)
		baseDeliveryID := deliveryConfig.DeliveryID()
		var deliveryID string
		if baseDeliveryID != "" {
			// Make deliveryID unique per S3 object to support multi-record messages
			deliveryID = fmt.Sprintf("%s:%s", baseDeliveryID, objectKey)
		}

		if baseDeliveryID == "" {
			p.logger.Warn("delivery config has empty ID, will attempt delivery but skip metadata tracking",
				"tenant_id", tenantInfo.TenantID,
				"delivery_type", deliveryType)
			// Don't skip delivery - attempt it anyway (might succeed in edge cases)
			// Just don't use empty ID for skip checks or metadata tracking
		} else {
			// Check completion using BOTH object-scoped AND legacy format for backward compatibility
			// Legacy metadata (in retry queue) uses base format: "s3:bucket", "cloudwatch:/aws/logs/group"
			// New metadata uses scoped format: "s3:bucket:file.json.gz", "cloudwatch:/aws/logs/group:file.json.gz"
			// Check both to avoid re-delivering already-completed destinations from legacy messages
			isCompleted := metadata.IsDeliveryCompleted(deliveryID) || isDestinationSucceeded(metadata, deliveryID) ||
				metadata.IsDeliveryCompleted(baseDeliveryID) || isDestinationSucceeded(metadata, baseDeliveryID)

			if isCompleted {
				// Already completed - skip without incrementing stats (not new work performed)
				// Note: Don't log deliveryID values (contain end-user bucket/log group names)
				continue
			}
		}

		p.logger.Info("processing delivery",
			"tenant_id", tenantInfo.TenantID,
			"delivery_type", deliveryType,
			"application", tenantInfo.Application)

		if err := p.deliverLogs(ctx, bucketName, objectKey, objData, uploadTime, deliveryType, deliveryConfig, tenantInfo, metadata); err != nil {
			p.logger.Error("failed to deliver logs",
				"tenant_id", tenantInfo.TenantID,
				"delivery_type", deliveryType,
				"error", err)
			deliveryStats.FailedDeliveries++

			// Defensive check for non-recoverable errors (currently unused).
			// deliverLogs() returns AWS SDK errors wrapped in fmt.Errorf, never NonRecoverableError types.
			// If activated, `continue` would skip this delivery entirely (silent data loss without DLQ tooling).
			// Current behavior (all errors → normal classification → routing/DLQ) is safer.
			// Retained for potential future use if delivery functions need to signal unrecoverable conditions.
			if models.IsNonRecoverable(err) {
				p.logger.Warn("non-recoverable delivery error, skipping",
					"delivery_type", deliveryType,
					"error", err)
				continue
			}
			// Accumulate errors in routing state for message-level routing decision
			if models.IsCustomerRepairableError(err) {
				routingState.repairableErr = err
			} else {
				routingState.transientErr = err
			}
			continue
		}

		// Only track successful delivery if we have a valid deliveryID
		if deliveryID != "" {
			routingState.completedDeliveries = append(routingState.completedDeliveries, deliveryID)
		}
		deliveryStats.SuccessfulDeliveries++
	}

	// Return nil - routing will happen at message level in ProcessSQSRecord
	return nil
}

// deliverLogs handles log delivery based on type
func (p *Processor) deliverLogs(ctx context.Context, bucketName, objectKey string, objData []byte, uploadTime int64, deliveryType string, deliveryConfig *models.DeliveryConfig, tenantInfo *models.TenantInfo, metadata *models.ProcessingMetadata) error {
	switch deliveryType {
	case "cloudwatch":
		// CloudWatch requires processing log events from the pre-downloaded object
		logEvents, err := ProcessLogFile(ctx, objectKey, objData, p.logger, p.config.MaxReadBytes)
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
