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
