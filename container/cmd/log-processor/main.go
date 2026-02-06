package main

import (
	"context"
	"encoding/json"
	"flag"
	"fmt"
	"io"
	"log/slog"
	"os"
	"strconv"
	"time"

	"github.com/aws/aws-lambda-go/lambda"
	"github.com/aws/aws-sdk-go-v2/config"
	"github.com/aws/aws-sdk-go-v2/service/cloudwatch"
	"github.com/aws/aws-sdk-go-v2/service/dynamodb"
	"github.com/aws/aws-sdk-go-v2/service/s3"
	"github.com/aws/aws-sdk-go-v2/service/sqs"
	"github.com/aws/aws-sdk-go-v2/service/sts"
	"github.com/openshift/rosa-log-router/internal/models"
	"github.com/openshift/rosa-log-router/internal/processor"
)

func main() {
	// Parse command-line flags
	mode := flag.String("mode", "", "Execution mode: sqs, manual, or scan (default: lambda)")
	flag.Parse()

	// Setup logger with LOG_LEVEL environment variable support
	logLevel := parseLogLevel()
	logger := slog.New(slog.NewJSONHandler(os.Stdout, &slog.HandlerOptions{
		Level: logLevel,
	}))
	slog.SetDefault(logger)

	logger.Info("log processor starting", "log_level", logLevel.String())

	// Load configuration from environment
	cfg, err := loadConfig()
	if err != nil {
		logger.Error("failed to load configuration", "error", err)
		os.Exit(99)
	}

	// Determine execution mode
	executionMode := cfg.ExecutionMode
	if *mode != "" {
		executionMode = *mode
	}

	// Load AWS config
	ctx := context.Background()
	awsCfg, err := config.LoadDefaultConfig(ctx, config.WithRegion(cfg.AWSRegion))
	if err != nil {
		logger.Error("failed to load AWS config", "error", err)
		os.Exit(1)
	}

	// Create AWS clients
	// Configure S3 path-style if needed (for LocalStack compatibility)
	s3Client := s3.NewFromConfig(awsCfg, func(o *s3.Options) {
		o.UsePathStyle = cfg.S3UsePathStyle
	})
	dynamoClient := dynamodb.NewFromConfig(awsCfg)
	sqsClient := sqs.NewFromConfig(awsCfg)
	stsClient := sts.NewFromConfig(awsCfg)
	cwClient := cloudwatch.NewFromConfig(awsCfg)

	// Create processor
	// Pass endpoint URL (if configured) to deliverers for LocalStack support
	proc := processor.NewProcessor(s3Client, dynamoClient, sqsClient, stsClient, cwClient, cfg.AWSEndpointURL, cfg, logger)

	// Execute based on mode
	switch executionMode {
	case "lambda", "":
		// Lambda mode
		logger.Info("starting in Lambda mode")
		lambda.Start(proc.HandleLambdaEvent)

	case "sqs":
		// SQS polling mode for local testing
		logger.Info("starting in SQS polling mode")
		if err := sqsPollingMode(ctx, proc, sqsClient, cfg, logger); err != nil {
			logger.Error("SQS polling mode failed", "error", err)
			os.Exit(1)
		}

	case "manual":
		// Manual input mode for development/testing
		logger.Info("starting in manual input mode")
		if err := manualInputMode(ctx, proc, logger); err != nil {
			logger.Error("manual input mode failed", "error", err)
			os.Exit(1)
		}

	case "scan":
		// Scan mode for integration testing
		logger.Info("starting in scan mode")
		if err := scanMode(ctx, proc, s3Client, cfg, logger); err != nil {
			logger.Error("scan mode failed", "error", err)
			os.Exit(1)
		}

	default:
		logger.Error("invalid execution mode", "mode", executionMode)
		os.Exit(1)
	}
}

// loadConfig loads configuration from environment variables
func loadConfig() (*models.Config, error) {
	cfg := models.DefaultConfig()

	if v := os.Getenv("TENANT_CONFIG_TABLE"); v != "" {
		cfg.TenantConfigTable = v
	}
	if v := os.Getenv("MAX_BATCH_SIZE"); v != "" {
		i, err := strconv.Atoi(v)
		if err != nil {
			return nil, fmt.Errorf("failed to convert value of 'MAX_BATCH_SIZE' to integer: %w", err)
		}
		cfg.MaxBatchSize = i
	}
	if v := os.Getenv("RETRY_ATTEMPTS"); v != "" {
		i, err := strconv.Atoi(v)
		if err != nil {
			return nil, fmt.Errorf("failed to convert value of 'RETRY_ATTEMPTS' to integer: %w", err)
		}
		cfg.RetryAttempts = i
	}
	if v := os.Getenv("CENTRAL_LOG_DISTRIBUTION_ROLE_ARN"); v != "" {
		cfg.CentralLogDistributionRoleArn = v
	}
	if v := os.Getenv("SQS_QUEUE_URL"); v != "" {
		cfg.SQSQueueURL = v
	}
	if v := os.Getenv("AWS_REGION"); v != "" {
		cfg.AWSRegion = v
	}
	if v := os.Getenv("EXECUTION_MODE"); v != "" {
		cfg.ExecutionMode = v
	}
	if v := os.Getenv("SOURCE_BUCKET"); v != "" {
		cfg.SourceBucket = v
	}
	if v := os.Getenv("SCAN_INTERVAL"); v != "" {
		i, err := strconv.Atoi(v)
		if err != nil {
			return nil, fmt.Errorf("failed to convert value of 'SCAN_INTERVAL' to integer: %w", err)
		}
		cfg.ScanInterval = i
	}
	if v := os.Getenv("AWS_S3_USE_PATH_STYLE"); v != "" {
		cfg.S3UsePathStyle = v == "true" || v == "1"
	}
	if v := os.Getenv("AWS_ENDPOINT_URL"); v != "" {
		cfg.AWSEndpointURL = v
	}

	return cfg, nil
}

// sqsPollingMode continuously polls SQS queue and processes messages
func sqsPollingMode(ctx context.Context, proc *processor.Processor, sqsClient *sqs.Client, cfg *models.Config, logger *slog.Logger) error {
	if cfg.SQSQueueURL == "" {
		return fmt.Errorf("SQS_QUEUE_URL environment variable not set")
	}

	logger.Info("starting SQS polling", "queue_url", cfg.SQSQueueURL)

	for {
		// Poll for messages
		resp, err := sqsClient.ReceiveMessage(ctx, &sqs.ReceiveMessageInput{
			QueueUrl:            &cfg.SQSQueueURL,
			MaxNumberOfMessages: 10,
			WaitTimeSeconds:     20, // Long polling
			VisibilityTimeout:   300,
		})

		if err != nil {
			logger.Error("failed to receive messages from SQS", "error", err)
			time.Sleep(5 * time.Second)
			continue
		}

		if len(resp.Messages) == 0 {
			logger.Info("no messages received, continuing to poll...")
			continue
		}

		logger.Info("received messages from SQS", "count", len(resp.Messages))

		for _, message := range resp.Messages {
			shouldDelete := false

			deliveryStats, err := proc.ProcessSQSRecord(ctx, *message.Body, *message.MessageId, *message.ReceiptHandle)

			if models.IsNonRecoverable(err) {
				logger.Warn("non-recoverable error, deleting message to prevent infinite retries",
					"message_id", *message.MessageId,
					"error", err)
				shouldDelete = true
			} else if err != nil {
				logger.Error("recoverable error, message will be retried",
					"message_id", *message.MessageId,
					"error", err)
				shouldDelete = false
			} else {
				shouldDelete = true
				if deliveryStats != nil {
					logger.Info("message processed successfully",
						"successful_deliveries", deliveryStats.SuccessfulDeliveries,
						"failed_deliveries", deliveryStats.FailedDeliveries)
				}
			}

			// Delete message if processing succeeded or error is non-recoverable
			if shouldDelete {
				_, err := sqsClient.DeleteMessage(ctx, &sqs.DeleteMessageInput{
					QueueUrl:      &cfg.SQSQueueURL,
					ReceiptHandle: message.ReceiptHandle,
				})
				if err != nil {
					logger.Error("failed to delete message", "message_id", *message.MessageId, "error", err)
				} else {
					logger.Info("successfully deleted message", "message_id", *message.MessageId)
				}
			}
		}
	}
}

// manualInputMode reads JSON input from stdin and processes it
func manualInputMode(ctx context.Context, proc *processor.Processor, logger *slog.Logger) error {
	logger.Info("reading JSON from stdin")
	logger.Info("expected format: SQS message body containing SNS message with S3 event")

	inputData, err := io.ReadAll(os.Stdin)
	if err != nil {
		return fmt.Errorf("failed to read stdin: %w", err)
	}

	if len(inputData) == 0 {
		return fmt.Errorf("no input data provided")
	}

	// Process as SQS record
	// TODO: Need to check on sending data as python has different
	deliveryStats, err := proc.ProcessSQSRecord(ctx, string(inputData), "manual-input", "manual")
	if err != nil {
		return fmt.Errorf("failed to process manual input: %w", err)
	}

	if deliveryStats != nil {
		logger.Info("successfully processed manual input",
			"successful_deliveries", deliveryStats.SuccessfulDeliveries,
			"failed_deliveries", deliveryStats.FailedDeliveries)
	} else {
		logger.Info("successfully processed manual input")
	}

	return nil
}

// scanMode continuously scans S3 bucket for new files and processes them
func scanMode(ctx context.Context, proc *processor.Processor, s3Client *s3.Client, cfg *models.Config, logger *slog.Logger) error {
	logger.Info("starting scan mode",
		"source_bucket", cfg.SourceBucket,
		"scan_interval", cfg.ScanInterval)

	processedObjects := make(map[string]bool)

	for {
		// List objects in source bucket
		resp, err := s3Client.ListObjectsV2(ctx, &s3.ListObjectsV2Input{
			Bucket: &cfg.SourceBucket,
		})

		if err != nil {
			logger.Error("failed to list objects in bucket", "error", err)
			time.Sleep(time.Duration(cfg.ScanInterval) * time.Second)
			continue
		}

		newObjectsFound := 0
		for _, obj := range resp.Contents {
			objectKey := *obj.Key

			// Only process .json.gz files that haven't been processed yet
			if processedObjects[objectKey] || !endsWithJSONGZ(objectKey) {
				continue
			}

			logger.Info("processing new object", "key", objectKey)
			newObjectsFound++

			// Create simulated SQS record
			s3Event := models.S3Event{
				Records: []models.S3EventRecord{
					{
						S3: models.S3Info{
							Bucket: models.S3BucketInfo{Name: cfg.SourceBucket},
							Object: models.S3ObjectInfo{Key: objectKey},
						},
					},
				},
			}

			s3EventJSON, _ := json.Marshal(s3Event)
			snsMessage := models.SNSMessage{Message: string(s3EventJSON)}
			snsMessageJSON, _ := json.Marshal(snsMessage)

			deliveryStats, err := proc.ProcessSQSRecord(ctx, string(snsMessageJSON), fmt.Sprintf("scan-%s", objectKey), "")
			if err != nil {
				logger.Error("failed to process object", "key", objectKey, "error", err)
				continue
			}

			processedObjects[objectKey] = true
			if deliveryStats != nil {
				logger.Info("successfully processed object",
					"key", objectKey,
					"successful_deliveries", deliveryStats.SuccessfulDeliveries,
					"failed_deliveries", deliveryStats.FailedDeliveries)
			}
		}

		if newObjectsFound > 0 {
			logger.Info("processed new objects in scan", "count", newObjectsFound)
		}

		logger.Debug("waiting before next scan", "interval_seconds", cfg.ScanInterval)
		time.Sleep(time.Duration(cfg.ScanInterval) * time.Second)
	}
}

func endsWithJSONGZ(s string) bool {
	return len(s) >= 8 && s[len(s)-8:] == ".json.gz"
}

// parseLogLevel parses LOG_LEVEL environment variable and returns corresponding slog.Level
func parseLogLevel() slog.Level {
	logLevel := os.Getenv("LOG_LEVEL")
	if logLevel == "" {
		return slog.LevelInfo // Default to INFO
	}

	switch logLevel {
	case "DEBUG", "debug":
		return slog.LevelDebug
	case "INFO", "info":
		return slog.LevelInfo
	case "WARN", "warn", "WARNING", "warning":
		return slog.LevelWarn
	case "ERROR", "error":
		return slog.LevelError
	default:
		fmt.Fprintf(os.Stderr, "Invalid LOG_LEVEL '%s', defaulting to INFO. Valid values: DEBUG, INFO, WARN, ERROR\n", logLevel)
		return slog.LevelInfo
	}
}
