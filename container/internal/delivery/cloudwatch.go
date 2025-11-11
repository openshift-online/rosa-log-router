// Package delivery handles log delivery to various destinations (CloudWatch Logs, S3).
package delivery

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"log/slog"
	"math"
	"sort"
	"time"

	"github.com/aws/aws-sdk-go-v2/aws"
	"github.com/aws/aws-sdk-go-v2/service/cloudwatchlogs"
	"github.com/aws/aws-sdk-go-v2/service/cloudwatchlogs/types"
	"github.com/aws/aws-sdk-go-v2/service/sts"
	stypes "github.com/aws/aws-sdk-go-v2/service/sts/types"
	"github.com/openshift/rosa-log-router/internal/models"
)

// CloudWatchLogsAPI defines the interface for CloudWatch Logs operations
type CloudWatchLogsAPI interface {
	CreateLogGroup(ctx context.Context, params *cloudwatchlogs.CreateLogGroupInput, optFns ...func(*cloudwatchlogs.Options)) (*cloudwatchlogs.CreateLogGroupOutput, error)
	CreateLogStream(ctx context.Context, params *cloudwatchlogs.CreateLogStreamInput, optFns ...func(*cloudwatchlogs.Options)) (*cloudwatchlogs.CreateLogStreamOutput, error)
	PutLogEvents(ctx context.Context, params *cloudwatchlogs.PutLogEventsInput, optFns ...func(*cloudwatchlogs.Options)) (*cloudwatchlogs.PutLogEventsOutput, error)
	DescribeLogGroups(ctx context.Context, params *cloudwatchlogs.DescribeLogGroupsInput, optFns ...func(*cloudwatchlogs.Options)) (*cloudwatchlogs.DescribeLogGroupsOutput, error)
	DescribeLogStreams(ctx context.Context, params *cloudwatchlogs.DescribeLogStreamsInput, optFns ...func(*cloudwatchlogs.Options)) (*cloudwatchlogs.DescribeLogStreamsOutput, error)
}

// CloudWatchDeliverer handles CloudWatch Logs delivery
type CloudWatchDeliverer struct {
	stsClient         *sts.Client
	centralRoleArn    string
	endpointURL       string
	logger            *slog.Logger
	maxEventsPerBatch int
	maxBytesPerBatch  int64
	timeoutSeconds    int
}

// NewCloudWatchDeliverer creates a new CloudWatch Logs deliverer
func NewCloudWatchDeliverer(stsClient *sts.Client, centralRoleArn string, endpointURL string, logger *slog.Logger) *CloudWatchDeliverer {
	return &CloudWatchDeliverer{
		stsClient:         stsClient,
		centralRoleArn:    centralRoleArn,
		endpointURL:       endpointURL,
		logger:            logger,
		maxEventsPerBatch: 1000,    // CloudWatch limit
		maxBytesPerBatch:  1037576, // ~1MB CloudWatch limit
		timeoutSeconds:    5,       // Match Vector's timeout
	}
}

// DeliverLogs delivers log events to customer's CloudWatch Logs
func (d *CloudWatchDeliverer) DeliverLogs(ctx context.Context, logEvents []*models.LogEvent, deliveryConfig *models.DeliveryConfig, tenantInfo *models.TenantInfo, s3Timestamp int64) (*models.DeliveryStats, error) {
	d.logger.Info("starting CloudWatch delivery",
		"event_count", len(logEvents),
		"tenant_id", tenantInfo.TenantID,
		"log_group", deliveryConfig.LogGroupName)

	// Step 1: Assume the central log distribution role
	sessionName := fmt.Sprintf("CentralLogDistribution-%d", time.Now().UnixNano())
	centralRoleResp, err := d.stsClient.AssumeRole(ctx, &sts.AssumeRoleInput{
		RoleArn:         aws.String(d.centralRoleArn),
		RoleSessionName: aws.String(sessionName),
	})
	if err != nil {
		return nil, fmt.Errorf("failed to assume central log distribution role: %w", err)
	}

	// Step 2: Get current account ID for ExternalId
	callerIdentity, err := d.stsClient.GetCallerIdentity(ctx, &sts.GetCallerIdentityInput{})
	if err != nil {
		return nil, fmt.Errorf("failed to get caller identity: %w", err)
	}

	// Step 3: Assume customer role using central role credentials (double-hop)
	targetRegion := deliveryConfig.TargetRegion
	if targetRegion == "" {
		targetRegion = "us-east-1"
	}

	stats, err := d.deliverLogsNative(ctx, logEvents, centralRoleResp.Credentials, deliveryConfig.LogDistributionRoleArn, *callerIdentity.Account, targetRegion, deliveryConfig.LogGroupName, tenantInfo.PodName, s3Timestamp)
	if err != nil {
		return nil, err
	}

	d.logger.Info("successfully delivered logs to CloudWatch",
		"tenant_id", tenantInfo.TenantID,
		"successful_events", stats.SuccessfulEvents,
		"failed_events", stats.FailedEvents)

	return stats, nil
}

// deliverLogsNative uses pure Go implementation to deliver logs to CloudWatch
func (d *CloudWatchDeliverer) deliverLogsNative(ctx context.Context, logEvents []*models.LogEvent, centralCreds *stypes.Credentials, customerRoleArn, externalID, region, logGroup, logStream string, s3Timestamp int64) (*models.DeliveryStats, error) {
	d.logger.Info("starting native CloudWatch delivery",
		"event_count", len(logEvents),
		"log_group", logGroup,
		"log_stream", logStream,
		"region", region)

	// Create STS client with central credentials
	centralConfig, err := buildConfigWithEndpoint(ctx, region, aws.Credentials{
		AccessKeyID:     *centralCreds.AccessKeyId,
		SecretAccessKey: *centralCreds.SecretAccessKey,
		SessionToken:    *centralCreds.SessionToken,
	}, d.endpointURL)
	if err != nil {
		return nil, fmt.Errorf("failed to create STS config: %w", err)
	}

	centralSTS := sts.NewFromConfig(centralConfig)

	// Assume customer role
	d.logger.Info("assuming customer role", "role_arn", customerRoleArn)
	customerRoleResp, err := centralSTS.AssumeRole(ctx, &sts.AssumeRoleInput{
		RoleArn:         aws.String(customerRoleArn),
		RoleSessionName: aws.String(fmt.Sprintf("CloudWatchLogDelivery-%d", time.Now().UnixNano())),
		ExternalId:      aws.String(externalID),
	})
	if err != nil {
		return nil, fmt.Errorf("failed to assume customer role: %w", err)
	}

	d.logger.Info("successfully assumed customer role")

	// Create CloudWatch Logs client with customer credentials
	customerConfig, err := buildConfigWithEndpoint(ctx, region, aws.Credentials{
		AccessKeyID:     *customerRoleResp.Credentials.AccessKeyId,
		SecretAccessKey: *customerRoleResp.Credentials.SecretAccessKey,
		SessionToken:    *customerRoleResp.Credentials.SessionToken,
	}, d.endpointURL)
	if err != nil {
		return nil, fmt.Errorf("failed to create CloudWatch config: %w", err)
	}

	logsClient := cloudwatchlogs.NewFromConfig(customerConfig)

	// Process events with Vector-equivalent timestamp handling
	processedEvents := make([]types.InputLogEvent, 0, len(logEvents))
	for _, event := range logEvents {
		timestamp := event.Timestamp
		if timestamp == 0 {
			timestamp = s3Timestamp
		}

		// Process timestamp like Vector does
		processedTimestamp := processTimestampLikeVector(timestamp)

		// Convert message to string
		var messageStr string
		switch msg := event.Message.(type) {
		case string:
			messageStr = msg
		default:
			// Convert to JSON
			jsonBytes, err := json.Marshal(msg)
			if err != nil {
				d.logger.Warn("failed to marshal message to JSON", "error", err)
				messageStr = fmt.Sprintf("%v", msg)
			} else {
				messageStr = string(jsonBytes)
			}
		}

		processedEvents = append(processedEvents, types.InputLogEvent{
			Timestamp: aws.Int64(processedTimestamp),
			Message:   aws.String(messageStr),
		})
	}

	// Sort events chronologically (CloudWatch requirement)
	sort.Slice(processedEvents, func(i, j int) bool {
		return *processedEvents[i].Timestamp < *processedEvents[j].Timestamp
	})

	// Ensure log group and stream exist
	if err := ensureLogGroupAndStreamExist(ctx, logsClient, logGroup, logStream, d.logger); err != nil {
		return nil, err
	}

	// Deliver events in batches
	stats, err := deliverEventsInBatches(ctx, logsClient, logGroup, logStream, processedEvents, d.maxEventsPerBatch, d.maxBytesPerBatch, d.timeoutSeconds, d.logger)
	if err != nil {
		return nil, err
	}

	d.logger.Info("CloudWatch delivery complete",
		"successful_events", stats.SuccessfulEvents,
		"failed_events", stats.FailedEvents)

	// If there were failures, raise an error to trigger re-queuing
	if stats.FailedEvents > 0 {
		return stats, fmt.Errorf("failed to deliver %d out of %d events to CloudWatch", stats.FailedEvents, stats.TotalProcessed)
	}

	return stats, nil
}

// processTimestampLikeVector processes timestamp exactly like Vector's extract_timestamp transform
func processTimestampLikeVector(timestamp int64) int64 {
	// If timestamp is in seconds (< 1000000000000), convert to milliseconds
	if timestamp < 1000000000000 {
		return timestamp * 1000
	}
	// Already in milliseconds
	return timestamp
}

// ensureLogGroupAndStreamExist ensures log group and log stream exist
func ensureLogGroupAndStreamExist(ctx context.Context, client CloudWatchLogsAPI, logGroup, logStream string, logger *slog.Logger) error {
	// Check if log group exists
	groupsResp, err := client.DescribeLogGroups(ctx, &cloudwatchlogs.DescribeLogGroupsInput{
		LogGroupNamePrefix: aws.String(logGroup),
	})
	if err != nil {
		var alreadyExists *types.ResourceAlreadyExistsException
		if errors.As(err, &alreadyExists) {
			// Group created concurrently, continue
			logger.Info("log group already exists (concurrent creation)", "log_group", logGroup)
		} else {
			return fmt.Errorf("failed to describe log groups: %w", err)
		}
	}

	if err == nil {
		groupExists := false
		for _, group := range groupsResp.LogGroups {
			if *group.LogGroupName == logGroup {
				groupExists = true
				break
			}
		}

		if !groupExists {
			logger.Info("creating log group", "log_group", logGroup)
			_, err = client.CreateLogGroup(ctx, &cloudwatchlogs.CreateLogGroupInput{
				LogGroupName: aws.String(logGroup),
			})
			if err != nil {
				var alreadyExists *types.ResourceAlreadyExistsException
				if errors.As(err, &alreadyExists) {
					// Group created concurrently, continue
					logger.Info("log group already exists (concurrent creation)", "log_group", logGroup)
				} else {
					return fmt.Errorf("failed to create log group: %w", err)
				}
			}
		}
	}

	// Check if log stream exists
	streamsResp, err := client.DescribeLogStreams(ctx, &cloudwatchlogs.DescribeLogStreamsInput{
		LogGroupName:        aws.String(logGroup),
		LogStreamNamePrefix: aws.String(logStream),
	})
	if err != nil {
		return fmt.Errorf("failed to describe log streams: %w", err)
	}

	streamExists := false
	for _, stream := range streamsResp.LogStreams {
		if *stream.LogStreamName == logStream {
			streamExists = true
			break
		}
	}

	if !streamExists {
		logger.Info("creating log stream",
			"log_group", logGroup,
			"log_stream", logStream)
		_, err = client.CreateLogStream(ctx, &cloudwatchlogs.CreateLogStreamInput{
			LogGroupName:  aws.String(logGroup),
			LogStreamName: aws.String(logStream),
		})
		if err != nil {
			var alreadyExists *types.ResourceAlreadyExistsException
			if errors.As(err, &alreadyExists) {
				// Stream created concurrently, continue
				logger.Info("log stream already exists (concurrent creation)", "log_stream", logStream)
			} else {
				return fmt.Errorf("failed to create log stream: %w", err)
			}
		}
	}

	return nil
}

// deliverEventsInBatches delivers events in batches with Vector-equivalent retry logic
func deliverEventsInBatches(ctx context.Context, client CloudWatchLogsAPI, logGroup, logStream string, events []types.InputLogEvent, maxEventsPerBatch int, maxBytesPerBatch int64, timeoutSeconds int, logger *slog.Logger) (*models.DeliveryStats, error) {
	stats := &models.DeliveryStats{}

	// Handle empty events list
	if len(events) == 0 {
		return stats, nil
	}

	batchStartTime := time.Now()
	currentBatch := make([]types.InputLogEvent, 0, maxEventsPerBatch)
	var currentBatchSize int64
	var lastError error

	sendBatch := func() {
		if len(currentBatch) == 0 {
			return
		}

		logger.Info("sending batch to CloudWatch", "batch_size", len(currentBatch))

		// Retry logic matching Vector: 3 attempts
		maxRetries := 3
		retryDelay := time.Second

		for attempt := 0; attempt < maxRetries; attempt++ {
			resp, err := client.PutLogEvents(ctx, &cloudwatchlogs.PutLogEventsInput{
				LogGroupName:  aws.String(logGroup),
				LogStreamName: aws.String(logStream),
				LogEvents:     currentBatch,
			})

			if err != nil {
				// Handle throttling and service unavailability with retry
				if attempt < maxRetries-1 {
					logger.Warn("CloudWatch API error, retrying",
						"attempt", attempt+1,
						"max_retries", maxRetries,
						"delay", retryDelay,
						"error", err)
					time.Sleep(retryDelay)
					retryDelay = time.Duration(math.Min(float64(retryDelay*2), float64(30*time.Second)))
					continue
				} else {
					logger.Error("failed after max retries", "error", err)
					stats.FailedEvents += len(currentBatch)
					lastError = fmt.Errorf("failed to deliver batch after %d attempts: %w", maxRetries, err)
					return
				}
			}

			// Check for rejected events
			rejectedCount := 0
			if resp.RejectedLogEventsInfo != nil {
				info := resp.RejectedLogEventsInfo
				if info.TooNewLogEventStartIndex != nil {
					rejectedCount += len(currentBatch) - int(*info.TooNewLogEventStartIndex)
					logger.Warn("some events were too new", "index", *info.TooNewLogEventStartIndex)
				}
				if info.TooOldLogEventEndIndex != nil {
					rejectedCount += int(*info.TooOldLogEventEndIndex) + 1
					logger.Warn("some events were too old", "index", *info.TooOldLogEventEndIndex)
				}
				if info.ExpiredLogEventEndIndex != nil {
					rejectedCount += int(*info.ExpiredLogEventEndIndex) + 1
					logger.Warn("some events were expired", "index", *info.ExpiredLogEventEndIndex)
				}
			}

			batchSuccessful := len(currentBatch) - rejectedCount
			stats.SuccessfulEvents += max(0, batchSuccessful)
			stats.FailedEvents += max(0, rejectedCount)

			logger.Info("successfully sent batch",
				"successful", batchSuccessful,
				"rejected", rejectedCount)

			return
		}
	}

	for _, event := range events {
		// Calculate event size (approximate)
		eventSize := int64(len(*event.Message)) + 26 // 26 bytes overhead per event

		// Add event to current batch
		currentBatch = append(currentBatch, event)
		currentBatchSize += eventSize
		stats.TotalProcessed++

		// Check if we need to send current batch
		shouldSend := len(currentBatch) >= maxEventsPerBatch ||
			currentBatchSize > maxBytesPerBatch ||
			time.Since(batchStartTime) >= time.Duration(timeoutSeconds)*time.Second

		if shouldSend {
			sendBatch()
			if lastError != nil {
				return stats, lastError
			}
			currentBatch = make([]types.InputLogEvent, 0, maxEventsPerBatch)
			currentBatchSize = 0
			batchStartTime = time.Now()
		}
	}

	// Send final batch
	if len(currentBatch) > 0 {
		sendBatch()
		if lastError != nil {
			return stats, lastError
		}
	}

	return stats, nil
}

func max(a, b int) int {
	if a > b {
		return a
	}
	return b
}
