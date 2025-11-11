package tenant

import (
	"log/slog"

	"github.com/openshift/rosa-log-router/internal/models"
)

// ShouldProcessApplication checks if the application should be processed based on delivery config's desired_logs
func ShouldProcessApplication(config *models.DeliveryConfig, applicationName string, logger *slog.Logger) bool {
	// If desired_logs not specified, process all applications (backward compatibility)
	if len(config.DesiredLogs) == 0 {
		return true
	}

	// Collect all allowed applications from desired_logs
	allowedApplications := make(map[string]bool)

	// Process desired_logs field
	for _, app := range config.DesiredLogs {
		if app != "" {
			allowedApplications[app] = true
		}
	}

	// If we still have no allowed applications after processing, process all applications
	if len(allowedApplications) == 0 {
		logger.Warn("no valid applications found in desired_logs, processing all applications")
		return true
	}

	// Check if application is in the allowed set (case-sensitive matching)
	shouldProcess := allowedApplications[applicationName]

	if shouldProcess {
		logger.Info("application matches filtering criteria - will process",
			"application", applicationName)
	} else {
		logger.Info("application does NOT match filtering criteria - will skip processing",
			"application", applicationName)
	}

	return shouldProcess
}
