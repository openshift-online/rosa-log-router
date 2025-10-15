package tenant

import (
	"context"
	"fmt"
	"log/slog"
	"strings"

	"github.com/aws/aws-sdk-go-v2/aws"
	"github.com/aws/aws-sdk-go-v2/feature/dynamodb/attributevalue"
	"github.com/aws/aws-sdk-go-v2/service/dynamodb"
	"github.com/aws/aws-sdk-go-v2/service/dynamodb/types"
	"github.com/openshift/rosa-log-router/internal/models"
)

// DynamoDBQueryAPI defines the interface for DynamoDB query operations
type DynamoDBQueryAPI interface {
	Query(ctx context.Context, params *dynamodb.QueryInput, optFns ...func(*dynamodb.Options)) (*dynamodb.QueryOutput, error)
}

// ConfigManager handles tenant configuration retrieval from DynamoDB
type ConfigManager struct {
	client    DynamoDBQueryAPI
	tableName string
	logger    *slog.Logger
}

// NewConfigManager creates a new tenant configuration manager
func NewConfigManager(client DynamoDBQueryAPI, tableName string, logger *slog.Logger) *ConfigManager {
	return &ConfigManager{
		client:    client,
		tableName: tableName,
		logger:    logger,
	}
}

// GetTenantDeliveryConfigs retrieves all enabled delivery configurations for a tenant
func (cm *ConfigManager) GetTenantDeliveryConfigs(ctx context.Context, tenantID string) ([]*models.DeliveryConfig, error) {
	// Handle empty tenant ID (from malformed S3 paths)
	if tenantID == "" {
		cm.logger.Warn("invalid tenant_id (empty string) for DynamoDB lookup - indicates malformed S3 path")
		return nil, models.NewTenantNotFoundError(tenantID, "invalid tenant_id (empty string) from malformed S3 path")
	}

	// Query all delivery configurations for this tenant
	input := &dynamodb.QueryInput{
		TableName:              aws.String(cm.tableName),
		KeyConditionExpression: aws.String("tenant_id = :tenant_id"),
		ExpressionAttributeValues: map[string]types.AttributeValue{
			":tenant_id": &types.AttributeValueMemberS{Value: tenantID},
		},
	}

	result, err := cm.client.Query(ctx, input)
	if err != nil {
		// Check for ValidationException with empty string
		if strings.Contains(err.Error(), "ValidationException") && strings.Contains(err.Error(), "empty string value") {
			cm.logger.Warn("DynamoDB ValidationException for empty string tenant_id",
				"tenant_id", tenantID)
			return nil, models.NewTenantNotFoundError(tenantID, "invalid tenant_id (empty string) from malformed S3 path")
		}

		cm.logger.Error("failed to query DynamoDB for tenant configs",
			"tenant_id", tenantID,
			"error", err)
		return nil, fmt.Errorf("failed to get tenant delivery configurations for %s: %w", tenantID, err)
	}

	if len(result.Items) == 0 {
		return nil, models.NewTenantNotFoundError(tenantID, "no delivery configurations found for tenant")
	}

	// Unmarshal DynamoDB items to DeliveryConfig structs
	var configs []*models.DeliveryConfig
	for _, item := range result.Items {
		var config models.DeliveryConfig
		err := attributevalue.UnmarshalMap(item, &config)
		if err != nil {
			cm.logger.Error("failed to unmarshal delivery config",
				"tenant_id", tenantID,
				"error", err)
			continue
		}

		// Set enabled to true if not present (backward compatibility)
		if item["enabled"] == nil {
			config.Enabled = true
		}

		configs = append(configs, &config)
	}

	// Filter for enabled configurations
	enabledConfigs := make([]*models.DeliveryConfig, 0, len(configs))
	for _, config := range configs {
		if config.Enabled {
			// Validate required fields for each delivery type
			if err := ValidateTenantDeliveryConfig(config, tenantID); err != nil {
				return nil, err
			}
			enabledConfigs = append(enabledConfigs, config)
		}
	}

	if len(enabledConfigs) == 0 {
		return nil, models.NewTenantNotFoundError(tenantID, "no enabled delivery configurations found for tenant")
	}

	// Log configuration details
	configTypes := make([]string, len(enabledConfigs))
	for i, config := range enabledConfigs {
		configTypes[i] = config.Type
	}

	cm.logger.Info("retrieved enabled delivery configs for tenant",
		"tenant_id", tenantID,
		"count", len(enabledConfigs),
		"types", configTypes)

	for _, config := range enabledConfigs {
		if len(config.DesiredLogs) > 0 || len(config.Groups) > 0 {
			cm.logger.Info("delivery config with filtering",
				"type", config.Type,
				"desired_logs", config.DesiredLogs,
				"groups", config.Groups)
		} else {
			cm.logger.Info("delivery config without filtering (all applications will be processed)",
				"type", config.Type)
		}
	}

	return enabledConfigs, nil
}
