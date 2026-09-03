package models

import (
	"testing"

	"github.com/stretchr/testify/assert"
)

func TestShouldProcessApplicationWithDesiredLogsOnly(t *testing.T) {
	config := &DeliveryConfig{
		TenantID:    "test-tenant",
		Type:        "cloudwatch",
		DesiredLogs: []string{"payment-service", "user-service"},
	}

	assert.True(t, config.ApplicationEnabled("payment-service"))
	assert.True(t, config.ApplicationEnabled("user-service"))
	assert.False(t, config.ApplicationEnabled("admin-service"))
}

func TestShouldProcessApplicationCaseSensitive(t *testing.T) {
	config := &DeliveryConfig{
		TenantID:    "test-tenant",
		Type:        "cloudwatch",
		DesiredLogs: []string{"payment-service", "user-service"},
	}

	// Should match exact case
	assert.True(t, config.ApplicationEnabled("payment-service"))
	assert.True(t, config.ApplicationEnabled("user-service"))

	// Should NOT match different case
	assert.False(t, config.ApplicationEnabled("Payment-Service"))
	assert.False(t, config.ApplicationEnabled("USER-SERVICE"))
}

func TestShouldProcessApplicationNoFiltering(t *testing.T) {
	// Config without desired_logs - should allow all applications
	config := &DeliveryConfig{
		TenantID: "test-tenant",
		Type:     "cloudwatch",
	}

	assert.True(t, config.ApplicationEnabled("any-service"))
	assert.True(t, config.ApplicationEnabled("another-service"))
	assert.True(t, config.ApplicationEnabled("random-app"))
}

func TestShouldProcessApplicationEmptyDesiredLogs(t *testing.T) {
	// Empty desired_logs list
	config := &DeliveryConfig{
		TenantID:    "test-tenant",
		Type:        "cloudwatch",
		DesiredLogs: []string{},
	}
	assert.True(t, config.ApplicationEnabled("any-app"))
}

func TestDeliveryID(t *testing.T) {
	t.Run("s3 with bucket", func(t *testing.T) {
		c := &DeliveryConfig{Type: "s3", BucketName: "my-bucket"}
		assert.Equal(t, "s3:my-bucket", c.DeliveryID())
	})

	t.Run("cloudwatch with log group", func(t *testing.T) {
		c := &DeliveryConfig{Type: "cloudwatch", LogGroupName: "/aws/logs/app"}
		assert.Equal(t, "cloudwatch:/aws/logs/app", c.DeliveryID())
	})

	t.Run("s3 with empty bucket falls back to type", func(t *testing.T) {
		c := &DeliveryConfig{Type: "s3"}
		assert.Equal(t, "s3", c.DeliveryID())
	})

	t.Run("cloudwatch with empty log group falls back to type", func(t *testing.T) {
		c := &DeliveryConfig{Type: "cloudwatch"}
		assert.Equal(t, "cloudwatch", c.DeliveryID())
	})

	t.Run("unknown type", func(t *testing.T) {
		c := &DeliveryConfig{Type: "kinesis"}
		assert.Equal(t, "kinesis", c.DeliveryID())
	})
}

func TestIsDeliveryCompleted(t *testing.T) {
	t.Run("nil CompletedDeliveries", func(t *testing.T) {
		m := &ProcessingMetadata{}
		assert.False(t, m.IsDeliveryCompleted("s3:my-bucket"))
	})

	t.Run("empty CompletedDeliveries", func(t *testing.T) {
		m := &ProcessingMetadata{CompletedDeliveries: []string{}}
		assert.False(t, m.IsDeliveryCompleted("cloudwatch:/aws/logs/app"))
	})

	t.Run("delivery ID present", func(t *testing.T) {
		m := &ProcessingMetadata{CompletedDeliveries: []string{"s3:my-bucket", "cloudwatch:/aws/logs/app"}}
		assert.True(t, m.IsDeliveryCompleted("s3:my-bucket"))
		assert.True(t, m.IsDeliveryCompleted("cloudwatch:/aws/logs/app"))
	})

	t.Run("delivery ID absent", func(t *testing.T) {
		m := &ProcessingMetadata{CompletedDeliveries: []string{"s3:my-bucket"}}
		assert.False(t, m.IsDeliveryCompleted("cloudwatch:/aws/logs/app"))
	})
}
