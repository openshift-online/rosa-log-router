package tenant

import (
	"testing"

	"github.com/openshift/rosa-log-router/internal/models"
	"github.com/stretchr/testify/assert"
)

func TestShouldProcessApplicationWithDesiredLogsOnly(t *testing.T) {
	logger := models.NewDefaultLogger()

	config := &models.DeliveryConfig{
		TenantID:    "test-tenant",
		Type:        "cloudwatch",
		DesiredLogs: []string{"payment-service", "user-service"},
	}

	assert.True(t, ShouldProcessApplication(config, "payment-service", logger))
	assert.True(t, ShouldProcessApplication(config, "user-service", logger))
	assert.False(t, ShouldProcessApplication(config, "admin-service", logger))
}

func TestShouldProcessApplicationCaseSensitive(t *testing.T) {
	logger := models.NewDefaultLogger()

	config := &models.DeliveryConfig{
		TenantID:    "test-tenant",
		Type:        "cloudwatch",
		DesiredLogs: []string{"payment-service", "user-service"},
	}

	// Should match exact case
	assert.True(t, ShouldProcessApplication(config, "payment-service", logger))
	assert.True(t, ShouldProcessApplication(config, "user-service", logger))

	// Should NOT match different case
	assert.False(t, ShouldProcessApplication(config, "Payment-Service", logger))
	assert.False(t, ShouldProcessApplication(config, "USER-SERVICE", logger))
}

func TestShouldProcessApplicationNoFiltering(t *testing.T) {
	logger := models.NewDefaultLogger()

	// Config without desired_logs - should allow all applications
	config := &models.DeliveryConfig{
		TenantID: "test-tenant",
		Type:     "cloudwatch",
	}

	assert.True(t, ShouldProcessApplication(config, "any-service", logger))
	assert.True(t, ShouldProcessApplication(config, "another-service", logger))
	assert.True(t, ShouldProcessApplication(config, "random-app", logger))
}

func TestShouldProcessApplicationEmptyDesiredLogs(t *testing.T) {
	logger := models.NewDefaultLogger()

	// Empty desired_logs list
	config := &models.DeliveryConfig{
		TenantID:    "test-tenant",
		Type:        "cloudwatch",
		DesiredLogs: []string{},
	}
	assert.True(t, ShouldProcessApplication(config, "any-app", logger))
}

func TestShouldProcessDeliveryConfigEnabled(t *testing.T) {
	config := &models.DeliveryConfig{
		TenantID: "test-tenant",
		Type:     "cloudwatch",
		Enabled:  true,
	}

	assert.True(t, ShouldProcessDeliveryConfig(config))
}

func TestShouldProcessDeliveryConfigDisabled(t *testing.T) {
	config := &models.DeliveryConfig{
		TenantID: "test-tenant",
		Type:     "cloudwatch",
		Enabled:  false,
	}

	assert.False(t, ShouldProcessDeliveryConfig(config))
}
