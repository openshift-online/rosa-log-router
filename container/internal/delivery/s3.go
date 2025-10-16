package delivery

import (
	"context"
	"fmt"
	"log/slog"
	"strings"
	"time"

	"github.com/aws/aws-sdk-go-v2/aws"
	"github.com/aws/aws-sdk-go-v2/service/s3"
	"github.com/aws/aws-sdk-go-v2/service/s3/types"
	"github.com/aws/aws-sdk-go-v2/service/sts"
	"github.com/openshift/rosa-log-router/internal/models"
)

// S3Deliverer handles S3-to-S3 log delivery
type S3Deliverer struct {
	stsClient      *sts.Client
	centralRoleArn string
	usePathStyle   bool
	endpointURL    string
	logger         *slog.Logger
}

// NewS3Deliverer creates a new S3 deliverer
func NewS3Deliverer(stsClient *sts.Client, centralRoleArn string, usePathStyle bool, endpointURL string, logger *slog.Logger) *S3Deliverer {
	return &S3Deliverer{
		stsClient:      stsClient,
		centralRoleArn: centralRoleArn,
		usePathStyle:   usePathStyle,
		endpointURL:    endpointURL,
		logger:         logger,
	}
}

// DeliverLogs delivers a log file from the central S3 bucket to a customer's S3 bucket using direct S3-to-S3 copy
func (d *S3Deliverer) DeliverLogs(ctx context.Context, sourceBucket, sourceKey string, deliveryConfig *models.DeliveryConfig, tenantInfo *models.TenantInfo) error {
	d.logger.Info("starting S3-to-S3 copy for tenant",
		"tenant_id", tenantInfo.TenantID,
		"source_bucket", sourceBucket,
		"source_key", sourceKey)

	// Step 1: Assume the central log distribution role
	// For S3 delivery, we use single-hop: central role writes directly to customer bucket
	// (Customer bucket policy grants central role PutObject permissions)
	sessionName := fmt.Sprintf("S3LogDelivery-%d", time.Now().UnixNano())
	centralRoleResp, err := d.stsClient.AssumeRole(ctx, &sts.AssumeRoleInput{
		RoleArn:         aws.String(d.centralRoleArn),
		RoleSessionName: aws.String(sessionName),
	})
	if err != nil {
		return fmt.Errorf("failed to assume central log distribution role: %w", err)
	}

	d.logger.Debug("assumed central role for S3 delivery",
		"role_arn", d.centralRoleArn,
		"tenant_id", tenantInfo.TenantID)

	// Step 2: Create S3 client with central role credentials
	targetRegion := deliveryConfig.TargetRegion
	if targetRegion == "" {
		targetRegion = "us-east-1"
	}

	s3Config, err := buildConfigWithEndpoint(ctx, targetRegion, aws.Credentials{
		AccessKeyID:     *centralRoleResp.Credentials.AccessKeyId,
		SecretAccessKey: *centralRoleResp.Credentials.SecretAccessKey,
		SessionToken:    *centralRoleResp.Credentials.SessionToken,
	}, d.endpointURL)
	if err != nil {
		return fmt.Errorf("failed to create S3 config: %w", err)
	}

	s3Client := s3.NewFromConfig(s3Config, func(o *s3.Options) {
		// Configure S3 path-style if needed (for LocalStack compatibility)
		o.UsePathStyle = d.usePathStyle
	})

	// Step 3: Prepare destination S3 details
	destinationBucket := deliveryConfig.BucketName
	bucketPrefix := deliveryConfig.BucketPrefix
	if bucketPrefix == "" {
		bucketPrefix = "ROSA/cluster-logs/"
	}

	// Normalize prefix (ensure trailing slash)
	bucketPrefix = normalizeBucketPrefix(bucketPrefix)

	// Create destination key maintaining directory structure
	// Format: {prefix}{tenant_id}/{application}/{pod_name}/{filename}
	// This excludes cluster_id to avoid exposing MC cluster ID to destination
	sourceFilename := sourceKey[strings.LastIndex(sourceKey, "/")+1:]
	destinationKey := fmt.Sprintf("%s%s/%s/%s/%s",
		bucketPrefix,
		tenantInfo.TenantID,
		tenantInfo.Application,
		tenantInfo.PodName,
		sourceFilename)

	d.logger.Info("S3 copy details",
		"source", fmt.Sprintf("s3://%s/%s", sourceBucket, sourceKey),
		"destination", fmt.Sprintf("s3://%s/%s", destinationBucket, destinationKey))

	// Step 4: Prepare copy source
	copySource := fmt.Sprintf("%s/%s", sourceBucket, sourceKey)

	// Step 5: Additional metadata for traceability
	metadata := map[string]string{
		"source-bucket":        sourceBucket,
		"source-key":           sourceKey,
		"tenant-id":            tenantInfo.TenantID,
		"application":          tenantInfo.Application,
		"pod-name":             tenantInfo.PodName,
		"delivery-timestamp":   fmt.Sprintf("%d", time.Now().Unix()),
	}

	// Step 6: Perform S3-to-S3 copy with bucket-owner-full-control ACL
	_, err = s3Client.CopyObject(ctx, &s3.CopyObjectInput{
		Bucket:            aws.String(destinationBucket),
		Key:               aws.String(destinationKey),
		CopySource:        aws.String(copySource),
		ACL:               types.ObjectCannedACLBucketOwnerFullControl,
		Metadata:          metadata,
		MetadataDirective: types.MetadataDirectiveReplace,
	})

	if err != nil {
		// Handle specific S3 errors
		errMsg := err.Error()
		if strings.Contains(errMsg, "NoSuchBucket") {
			return models.NewNonRecoverableError(fmt.Sprintf("destination S3 bucket '%s' does not exist", destinationBucket))
		} else if strings.Contains(errMsg, "AccessDenied") {
			return models.NewNonRecoverableError(fmt.Sprintf("access denied to S3 bucket '%s'. Check bucket policy and Central Role permissions", destinationBucket))
		} else if strings.Contains(errMsg, "NoSuchKey") {
			return models.NewNonRecoverableError(fmt.Sprintf("source S3 object s3://%s/%s not found", sourceBucket, sourceKey))
		}

		// For other errors, treat as recoverable (temporary issues)
		d.logger.Error("S3 copy operation failed", "error", err)
		return fmt.Errorf("S3 copy failed: %w", err)
	}

	d.logger.Info("successfully copied log file to S3",
		"tenant_id", tenantInfo.TenantID,
		"destination", fmt.Sprintf("s3://%s/%s", destinationBucket, destinationKey))

	return nil
}

// normalizeBucketPrefix ensures bucket prefix ends with a slash
func normalizeBucketPrefix(prefix string) string {
	if prefix == "" {
		return prefix
	}
	if !strings.HasSuffix(prefix, "/") {
		return prefix + "/"
	}
	return prefix
}
