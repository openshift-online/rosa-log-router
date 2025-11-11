package tenant

import (
	"testing"

	"github.com/openshift/rosa-log-router/internal/models"
	"github.com/stretchr/testify/assert"
)

func TestExpandGroupsToApplicationsValidGroups(t *testing.T) {
	logger := models.NewDefaultLogger()

	// Test single group
	result := ExpandGroupsToApplications([]string{"API"}, logger)
	expected := []string{"kube-apiserver", "openshift-apiserver"}
	assert.ElementsMatch(t, expected, result)

	// Test multiple groups
	result = ExpandGroupsToApplications([]string{"API", "Authentication"}, logger)
	expected = []string{"kube-apiserver", "openshift-apiserver", "oauth-openshift", "openshift-oauth-apiserver"}
	assert.ElementsMatch(t, expected, result)
}

func TestExpandGroupsToApplicationsCaseInsensitive(t *testing.T) {
	logger := models.NewDefaultLogger()

	// Test lowercase
	result := ExpandGroupsToApplications([]string{"api"}, logger)
	expected := []string{"kube-apiserver", "openshift-apiserver"}
	assert.ElementsMatch(t, expected, result)

	// Test mixed case
	result = ExpandGroupsToApplications([]string{"Api", "authentication"}, logger)
	expected = []string{"kube-apiserver", "openshift-apiserver", "oauth-openshift", "openshift-oauth-apiserver"}
	assert.ElementsMatch(t, expected, result)
}

func TestExpandGroupsToApplicationsInvalidGroup(t *testing.T) {
	logger := models.NewDefaultLogger()

	// Single invalid group
	result := ExpandGroupsToApplications([]string{"INVALID_GROUP"}, logger)
	assert.Empty(t, result)

	// Mix of valid and invalid groups
	result = ExpandGroupsToApplications([]string{"API", "INVALID_GROUP", "Authentication"}, logger)
	expected := []string{"kube-apiserver", "openshift-apiserver", "oauth-openshift", "openshift-oauth-apiserver"}
	assert.ElementsMatch(t, expected, result)
}

func TestExpandGroupsToApplicationsEmptyList(t *testing.T) {
	logger := models.NewDefaultLogger()

	result := ExpandGroupsToApplications([]string{}, logger)
	assert.Empty(t, result)
}

func TestShouldProcessApplicationWithGroupsOnly(t *testing.T) {
	logger := models.NewDefaultLogger()

	config := &models.DeliveryConfig{
		TenantID: "test-tenant",
		Type:     "cloudwatch",
		Groups:   []string{"API", "Authentication"},
	}

	// Should match applications in API group
	assert.True(t, ShouldProcessApplication(config, "kube-apiserver", logger))
	assert.True(t, ShouldProcessApplication(config, "openshift-apiserver", logger))

	// Should match applications in Authentication group
	assert.True(t, ShouldProcessApplication(config, "oauth-openshift", logger))
	assert.True(t, ShouldProcessApplication(config, "openshift-oauth-apiserver", logger))

	// Should not match applications not in groups
	assert.False(t, ShouldProcessApplication(config, "kube-scheduler", logger))
	assert.False(t, ShouldProcessApplication(config, "some-random-app", logger))
}

func TestShouldProcessApplicationWithGroupsAndDesiredLogs(t *testing.T) {
	logger := models.NewDefaultLogger()

	config := &models.DeliveryConfig{
		TenantID:    "test-tenant",
		Type:        "cloudwatch",
		DesiredLogs: []string{"custom-app-1", "custom-app-2"},
		Groups:      []string{"API"},
	}

	// Should match applications from desired_logs
	assert.True(t, ShouldProcessApplication(config, "custom-app-1", logger))
	assert.True(t, ShouldProcessApplication(config, "custom-app-2", logger))

	// Should match applications from groups
	assert.True(t, ShouldProcessApplication(config, "kube-apiserver", logger))
	assert.True(t, ShouldProcessApplication(config, "openshift-apiserver", logger))

	// Should not match applications not in either list
	assert.False(t, ShouldProcessApplication(config, "kube-scheduler", logger))
	assert.False(t, ShouldProcessApplication(config, "random-app", logger))
}

func TestShouldProcessApplicationGroupsCaseInsensitiveButApplicationCaseSensitive(t *testing.T) {
	logger := models.NewDefaultLogger()

	config := &models.DeliveryConfig{
		TenantID: "test-tenant",
		Type:     "cloudwatch",
		Groups:   []string{"api"}, // lowercase group name
	}

	// Should match exact application names from the group (case-sensitive)
	assert.True(t, ShouldProcessApplication(config, "kube-apiserver", logger))
	assert.True(t, ShouldProcessApplication(config, "openshift-apiserver", logger))

	// Should NOT match different case (application matching is case-sensitive)
	assert.False(t, ShouldProcessApplication(config, "KUBE-APISERVER", logger))
	assert.False(t, ShouldProcessApplication(config, "OpenShift-ApiServer", logger))
}

func TestShouldProcessApplicationDuplicateFiltering(t *testing.T) {
	logger := models.NewDefaultLogger()

	config := &models.DeliveryConfig{
		TenantID:    "test-tenant",
		Type:        "cloudwatch",
		DesiredLogs: []string{"kube-apiserver", "custom-app"}, // kube-apiserver also in API group
		Groups:      []string{"API"},
	}

	// Should work correctly despite kube-apiserver being in both lists
	assert.True(t, ShouldProcessApplication(config, "kube-apiserver", logger))
	assert.True(t, ShouldProcessApplication(config, "custom-app", logger))
	assert.True(t, ShouldProcessApplication(config, "openshift-apiserver", logger))
	assert.False(t, ShouldProcessApplication(config, "kube-scheduler", logger))
}

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

	// Config without desired_logs or groups - should allow all applications
	config := &models.DeliveryConfig{
		TenantID: "test-tenant",
		Type:     "cloudwatch",
	}

	assert.True(t, ShouldProcessApplication(config, "any-service", logger))
	assert.True(t, ShouldProcessApplication(config, "another-service", logger))
	assert.True(t, ShouldProcessApplication(config, "random-app", logger))
}

func TestShouldProcessApplicationEmptyGroupsAndDesiredLogs(t *testing.T) {
	logger := models.NewDefaultLogger()

	// Both empty lists
	config := &models.DeliveryConfig{
		TenantID:    "test-tenant",
		Type:        "cloudwatch",
		DesiredLogs: []string{},
		Groups:      []string{},
	}
	assert.True(t, ShouldProcessApplication(config, "any-app", logger))
}

func TestShouldProcessApplicationGroupsWithInvalidGroupNames(t *testing.T) {
	logger := models.NewDefaultLogger()

	config := &models.DeliveryConfig{
		TenantID: "test-tenant",
		Type:     "cloudwatch",
		Groups:   []string{"API", "INVALID_GROUP", "Authentication", "ANOTHER_INVALID"},
	}

	// Should still work with valid groups, ignoring invalid ones
	assert.True(t, ShouldProcessApplication(config, "kube-apiserver", logger))  // from API
	assert.True(t, ShouldProcessApplication(config, "oauth-openshift", logger)) // from Authentication
	assert.False(t, ShouldProcessApplication(config, "kube-scheduler", logger)) // not in any valid group
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

func TestAllApplicationGroups(t *testing.T) {
	logger := models.NewDefaultLogger()

	// Test all defined groups to ensure they're properly configured
	testCases := []struct {
		group        string
		expectedApps []string
	}{
		{
			group:        "API",
			expectedApps: []string{"kube-apiserver", "openshift-apiserver"},
		},
		{
			group:        "Authentication",
			expectedApps: []string{"oauth-openshift", "openshift-oauth-apiserver"},
		},
		{
			group:        "Scheduler",
			expectedApps: []string{"kube-scheduler"},
		},
		{
			group:        "Controller Manager",
			expectedApps: []string{"kube-controller-manager", "openshift-controller-manager", "openshift-route-controller-manager"},
		},
	}

	for _, tc := range testCases {
		t.Run(tc.group, func(t *testing.T) {
			result := ExpandGroupsToApplications([]string{tc.group}, logger)
			assert.ElementsMatch(t, tc.expectedApps, result, "Group %s should expand to expected applications", tc.group)
		})
	}
}
