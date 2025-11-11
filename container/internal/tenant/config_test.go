package tenant

import (
	"context"
	"testing"

	"github.com/aws/aws-sdk-go-v2/service/dynamodb"
	"github.com/aws/aws-sdk-go-v2/service/dynamodb/types"
	"github.com/openshift/rosa-log-router/internal/models"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

// Mock DynamoDB client for testing
type mockDynamoDBClient struct {
	queryFunc func(ctx context.Context, params *dynamodb.QueryInput, optFns ...func(*dynamodb.Options)) (*dynamodb.QueryOutput, error)
}

func (m *mockDynamoDBClient) Query(ctx context.Context, params *dynamodb.QueryInput, optFns ...func(*dynamodb.Options)) (*dynamodb.QueryOutput, error) {
	if m.queryFunc != nil {
		return m.queryFunc(ctx, params, optFns...)
	}
	return &dynamodb.QueryOutput{}, nil
}

func TestGetTenantDeliveryConfigsSuccess(t *testing.T) {
	mockClient := &mockDynamoDBClient{
		queryFunc: func(ctx context.Context, params *dynamodb.QueryInput, optFns ...func(*dynamodb.Options)) (*dynamodb.QueryOutput, error) {
			// Return a valid CloudWatch config
			return &dynamodb.QueryOutput{
				Items: []map[string]types.AttributeValue{
					{
						"tenant_id":                 &types.AttributeValueMemberS{Value: "acme-corp"},
						"type":                      &types.AttributeValueMemberS{Value: "cloudwatch"},
						"log_distribution_role_arn": &types.AttributeValueMemberS{Value: "arn:aws:iam::987654321098:role/LogRole"},
						"log_group_name":            &types.AttributeValueMemberS{Value: "/aws/logs/acme-corp"},
						"target_region":             &types.AttributeValueMemberS{Value: "us-east-1"},
						"enabled":                   &types.AttributeValueMemberBOOL{Value: true},
						"desired_logs": &types.AttributeValueMemberL{Value: []types.AttributeValue{
							&types.AttributeValueMemberS{Value: "payment-service"},
							&types.AttributeValueMemberS{Value: "user-service"},
						}},
					},
				},
			}, nil
		},
	}

	logger := models.NewDefaultLogger()
	manager := &ConfigManager{
		client:    mockClient,
		tableName: "test-tenant-configs",
		logger:    logger,
	}

	ctx := context.Background()
	configs, err := manager.GetTenantDeliveryConfigs(ctx, "acme-corp")

	require.NoError(t, err)
	assert.Len(t, configs, 1)

	config := configs[0]
	assert.Equal(t, "acme-corp", config.TenantID)
	assert.Equal(t, "cloudwatch", config.Type)
	assert.Equal(t, "arn:aws:iam::987654321098:role/LogRole", config.LogDistributionRoleArn)
	assert.Equal(t, "/aws/logs/acme-corp", config.LogGroupName)
	assert.Equal(t, "us-east-1", config.TargetRegion)
	assert.True(t, config.Enabled)
	assert.Contains(t, config.DesiredLogs, "payment-service")
	assert.Contains(t, config.DesiredLogs, "user-service")
}

func TestGetTenantDeliveryConfigsNotFound(t *testing.T) {
	mockClient := &mockDynamoDBClient{
		queryFunc: func(ctx context.Context, params *dynamodb.QueryInput, optFns ...func(*dynamodb.Options)) (*dynamodb.QueryOutput, error) {
			// Return empty result
			return &dynamodb.QueryOutput{
				Items: []map[string]types.AttributeValue{},
			}, nil
		},
	}

	logger := models.NewDefaultLogger()
	manager := &ConfigManager{
		client:    mockClient,
		tableName: "test-tenant-configs",
		logger:    logger,
	}

	ctx := context.Background()
	_, err := manager.GetTenantDeliveryConfigs(ctx, "nonexistent-tenant")

	require.Error(t, err)
	assert.IsType(t, &models.TenantNotFoundError{}, err)
	assert.Contains(t, err.Error(), "no delivery configurations found for tenant")
}

func TestGetTenantDeliveryConfigsMissingRequiredFields(t *testing.T) {
	mockClient := &mockDynamoDBClient{
		queryFunc: func(ctx context.Context, params *dynamodb.QueryInput, optFns ...func(*dynamodb.Options)) (*dynamodb.QueryOutput, error) {
			// Return config missing required fields (but enabled so validation runs)
			return &dynamodb.QueryOutput{
				Items: []map[string]types.AttributeValue{
					{
						"tenant_id":                 &types.AttributeValueMemberS{Value: "missing-fields"},
						"type":                      &types.AttributeValueMemberS{Value: "cloudwatch"},
						"log_distribution_role_arn": &types.AttributeValueMemberS{Value: "arn:aws:iam::987654321098:role/LogRole"},
						"enabled":                   &types.AttributeValueMemberBOOL{Value: true},
						// Missing log_group_name and target_region
					},
				},
			}, nil
		},
	}

	logger := models.NewDefaultLogger()
	manager := &ConfigManager{
		client:    mockClient,
		tableName: "test-tenant-configs",
		logger:    logger,
	}

	ctx := context.Background()
	_, err := manager.GetTenantDeliveryConfigs(ctx, "missing-fields")

	require.Error(t, err)
	assert.IsType(t, &models.TenantNotFoundError{}, err)
	assert.Contains(t, err.Error(), "missing or has empty value for required field")
}

func TestGetTenantDeliveryConfigsDisabledFiltered(t *testing.T) {
	mockClient := &mockDynamoDBClient{
		queryFunc: func(ctx context.Context, params *dynamodb.QueryInput, optFns ...func(*dynamodb.Options)) (*dynamodb.QueryOutput, error) {
			// Return disabled config
			return &dynamodb.QueryOutput{
				Items: []map[string]types.AttributeValue{
					{
						"tenant_id":                 &types.AttributeValueMemberS{Value: "disabled-tenant"},
						"type":                      &types.AttributeValueMemberS{Value: "cloudwatch"},
						"log_distribution_role_arn": &types.AttributeValueMemberS{Value: "arn:aws:iam::987654321098:role/LogRole"},
						"log_group_name":            &types.AttributeValueMemberS{Value: "/aws/logs/disabled"},
						"target_region":             &types.AttributeValueMemberS{Value: "us-east-1"},
						"enabled":                   &types.AttributeValueMemberBOOL{Value: false},
					},
				},
			}, nil
		},
	}

	logger := models.NewDefaultLogger()
	manager := &ConfigManager{
		client:    mockClient,
		tableName: "test-tenant-configs",
		logger:    logger,
	}

	ctx := context.Background()
	_, err := manager.GetTenantDeliveryConfigs(ctx, "disabled-tenant")

	require.Error(t, err)
	assert.IsType(t, &models.TenantNotFoundError{}, err)
	assert.Contains(t, err.Error(), "no enabled delivery configurations found for tenant")
}

func TestGetTenantDeliveryConfigsEmptyTenantID(t *testing.T) {
	mockClient := &mockDynamoDBClient{
		queryFunc: func(ctx context.Context, params *dynamodb.QueryInput, optFns ...func(*dynamodb.Options)) (*dynamodb.QueryOutput, error) {
			// This should not be called for empty tenant_id
			t.Fatal("Query should not be called for empty tenant_id")
			return nil, nil
		},
	}

	logger := models.NewDefaultLogger()
	manager := &ConfigManager{
		client:    mockClient,
		tableName: "test-tenant-configs",
		logger:    logger,
	}

	ctx := context.Background()
	_, err := manager.GetTenantDeliveryConfigs(ctx, "")

	require.Error(t, err)
	assert.IsType(t, &models.TenantNotFoundError{}, err)
	assert.Contains(t, err.Error(), "invalid tenant_id (empty string)")
}

func TestGetTenantDeliveryConfigsMultipleConfigs(t *testing.T) {
	mockClient := &mockDynamoDBClient{
		queryFunc: func(ctx context.Context, params *dynamodb.QueryInput, optFns ...func(*dynamodb.Options)) (*dynamodb.QueryOutput, error) {
			// Return both CloudWatch and S3 configs
			return &dynamodb.QueryOutput{
				Items: []map[string]types.AttributeValue{
					{
						"tenant_id":                 &types.AttributeValueMemberS{Value: "multi-tenant"},
						"type":                      &types.AttributeValueMemberS{Value: "cloudwatch"},
						"log_distribution_role_arn": &types.AttributeValueMemberS{Value: "arn:aws:iam::123456789012:role/CloudWatchRole"},
						"log_group_name":            &types.AttributeValueMemberS{Value: "/aws/logs/multi-tenant"},
						"target_region":             &types.AttributeValueMemberS{Value: "us-east-1"},
						"enabled":                   &types.AttributeValueMemberBOOL{Value: true},
					},
					{
						"tenant_id":                 &types.AttributeValueMemberS{Value: "multi-tenant"},
						"type":                      &types.AttributeValueMemberS{Value: "s3"},
						"log_distribution_role_arn": &types.AttributeValueMemberS{Value: "arn:aws:iam::123456789012:role/S3Role"},
						"bucket_name":               &types.AttributeValueMemberS{Value: "multi-tenant-logs"},
						"bucket_prefix":             &types.AttributeValueMemberS{Value: "logs/"},
						"target_region":             &types.AttributeValueMemberS{Value: "us-east-1"},
						"enabled":                   &types.AttributeValueMemberBOOL{Value: true},
					},
				},
			}, nil
		},
	}

	logger := models.NewDefaultLogger()
	manager := &ConfigManager{
		client:    mockClient,
		tableName: "test-tenant-configs",
		logger:    logger,
	}

	ctx := context.Background()
	configs, err := manager.GetTenantDeliveryConfigs(ctx, "multi-tenant")

	require.NoError(t, err)
	assert.Len(t, configs, 2)

	// Verify both configs are present
	var cwConfig, s3Config *models.DeliveryConfig
	for i := range configs {
		switch configs[i].Type {
		case "cloudwatch":
			cwConfig = configs[i]
		case "s3":
			s3Config = configs[i]
		}
	}

	require.NotNil(t, cwConfig)
	require.NotNil(t, s3Config)

	assert.Equal(t, "/aws/logs/multi-tenant", cwConfig.LogGroupName)
	assert.Equal(t, "multi-tenant-logs", s3Config.BucketName)
}

func TestGetTenantDeliveryConfigsDefaultEnabled(t *testing.T) {
	mockClient := &mockDynamoDBClient{
		queryFunc: func(ctx context.Context, params *dynamodb.QueryInput, optFns ...func(*dynamodb.Options)) (*dynamodb.QueryOutput, error) {
			// Return config without enabled field (should default to false)
			return &dynamodb.QueryOutput{
				Items: []map[string]types.AttributeValue{
					{
						"tenant_id":                 &types.AttributeValueMemberS{Value: "default-disabled"},
						"type":                      &types.AttributeValueMemberS{Value: "cloudwatch"},
						"log_distribution_role_arn": &types.AttributeValueMemberS{Value: "arn:aws:iam::987654321098:role/LogRole"},
						"log_group_name":            &types.AttributeValueMemberS{Value: "/aws/logs/default-disabled"},
						"target_region":             &types.AttributeValueMemberS{Value: "us-east-1"},
						// enabled field not present - should default to false (safe default)
					},
				},
			}, nil
		},
	}

	logger := models.NewDefaultLogger()
	manager := &ConfigManager{
		client:    mockClient,
		tableName: "test-tenant-configs",
		logger:    logger,
	}

	ctx := context.Background()
	_, err := manager.GetTenantDeliveryConfigs(ctx, "default-disabled")

	// Should return error because config defaults to disabled
	require.Error(t, err)
	assert.IsType(t, &models.TenantNotFoundError{}, err)
	assert.Contains(t, err.Error(), "no enabled delivery configurations found for tenant")
}
