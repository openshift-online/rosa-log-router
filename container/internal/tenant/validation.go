package tenant

import (
	"fmt"
	"strings"

	"github.com/openshift/rosa-log-router/internal/models"
)

// ValidateTenantDeliveryConfig validates that a delivery configuration contains all required fields
func ValidateTenantDeliveryConfig(config *models.DeliveryConfig, tenantID string) error {
	if config.Type == "" {
		return models.NewTenantNotFoundError(tenantID, "delivery configuration missing 'type' field")
	}

	switch config.Type {
	case "cloudwatch":
		return validateCloudWatchConfig(config, tenantID)
	case "s3":
		return validateS3Config(config, tenantID)
	default:
		return models.NewTenantNotFoundError(tenantID, fmt.Sprintf("invalid delivery type: %s", config.Type))
	}
}

// validateCloudWatchConfig validates CloudWatch-specific configuration fields
func validateCloudWatchConfig(config *models.DeliveryConfig, tenantID string) error {
	requiredFields := map[string]string{
		"log_distribution_role_arn": config.LogDistributionRoleArn,
		"log_group_name":            config.LogGroupName,
	}

	for fieldName, fieldValue := range requiredFields {
		if fieldValue == "" || strings.TrimSpace(fieldValue) == "" {
			return models.NewTenantNotFoundError(tenantID,
				fmt.Sprintf("CloudWatch delivery config missing or has empty value for required field: %s", fieldName))
		}
	}

	return nil
}

// validateS3Config validates S3-specific configuration fields
func validateS3Config(config *models.DeliveryConfig, tenantID string) error {
	if config.BucketName == "" || strings.TrimSpace(config.BucketName) == "" {
		return models.NewTenantNotFoundError(tenantID,
			"S3 delivery config missing or has empty value for required field: bucket_name")
	}

	return nil
}
