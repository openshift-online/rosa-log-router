// Package processor implements the core log processing logic for SQS, Lambda, and S3 scan modes.
package processor

import (
	"context"
	"encoding/json"
	"fmt"
	"log/slog"
	"net/url"
	"time"

	"github.com/aws/aws-lambda-go/events"
	"github.com/aws/aws-sdk-go-v2/service/cloudwatch"
	"github.com/aws/aws-sdk-go-v2/service/s3"
	"github.com/aws/aws-sdk-go-v2/service/sqs"
	"github.com/aws/aws-sdk-go-v2/service/sts"
	awsmetrics "github.com/openshift/rosa-log-router/internal/aws"
	"github.com/openshift/rosa-log-router/internal/delivery"
	"github.com/openshift/rosa-log-router/internal/models"
	"github.com/openshift/rosa-log-router/internal/tenant"
)

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

// HandleLambdaEvent processes SQS messages from Lambda
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

// ProcessSQSRecord processes a single SQS record containing S3 event notification
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
		return deliveryStats, models.NewInvalidS3NotificationError(fmt.Sprintf("failed to extract metadata from SQS message body: %v", err))
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

// processS3Object processes a single S3 object
func (p *Processor) processS3Object(ctx context.Context, bucketName, objectKey, messageBody, receiptHandle string, metadata *models.ProcessingMetadata, deliveryStats *models.DeliveryStats) error {
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

	// Process each delivery configuration independently with its own filtering
	for _, deliveryConfig := range deliveryConfigs {
		deliveryType := deliveryConfig.Type

		// Check if this application should be processed based on this config's desired_logs filtering
		if !deliveryConfig.ApplicationEnabled(tenantInfo.Application) {
			p.logger.Info("skipping delivery for application due to desired_logs filtering",
				"delivery_type", deliveryType,
				"application", tenantInfo.Application)
			continue
		}

		// This specific delivery config should process this application
		p.logger.Info("processing delivery",
			"tenant_id", tenantInfo.TenantID,
			"delivery_type", deliveryType,
			"application", tenantInfo.Application)

		// Deliver logs based on delivery type
		if err := p.deliverLogs(ctx, bucketName, objectKey, deliveryType, deliveryConfig, tenantInfo, metadata); err != nil {
			p.logger.Error("failed to deliver logs",
				"tenant_id", tenantInfo.TenantID,
				"delivery_type", deliveryType,
				"error", err)
			deliveryStats.FailedDeliveries++

			// For CloudWatch failures, try to re-queue with offset if possible
			if deliveryType == "cloudwatch" && receiptHandle != "" && p.config.SQSQueueURL != "" {
				if err := RequeueSQSMessageWithOffset(ctx, p.sqsClient, p.config.SQSQueueURL, messageBody, receiptHandle, metadata.Offset, 3, p.logger); err != nil {
					p.logger.Error("failed to re-queue message", "error", err)
				} else {
					p.logger.Info("re-queued message for retry", "offset", metadata.Offset)
				}
			}

			// Continue with other delivery types even if one fails
			continue
		}

		deliveryStats.SuccessfulDeliveries++
	}

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
