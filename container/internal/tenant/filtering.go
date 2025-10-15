package tenant

import (
	"log/slog"
	"strings"

	"github.com/openshift/rosa-log-router/internal/models"
)

// ExpandGroupsToApplications expands group names to their corresponding application lists
func ExpandGroupsToApplications(groups []string, logger *slog.Logger) []string {
	var expandedApplications []string

	for _, group := range groups {
		// Skip non-string values (shouldn't happen with proper typing, but defensive)
		if group == "" {
			logger.Warn("empty group name in groups list, skipping")
			continue
		}

		// Case-insensitive group lookup
		groupFound := false
		for key, applications := range models.ApplicationGroups {
			if strings.EqualFold(key, group) {
				expandedApplications = append(expandedApplications, applications...)
				logger.Info("expanded group to applications",
					"group", group,
					"applications", applications)
				groupFound = true
				break
			}
		}

		if !groupFound {
			availableGroups := make([]string, 0, len(models.ApplicationGroups))
			for k := range models.ApplicationGroups {
				availableGroups = append(availableGroups, k)
			}
			logger.Warn("group not found in APPLICATION_GROUPS dictionary",
				"group", group,
				"available_groups", availableGroups)
		}
	}

	return expandedApplications
}

// ShouldProcessApplication checks if the application should be processed based on delivery config's desired_logs and groups
func ShouldProcessApplication(config *models.DeliveryConfig, applicationName string, logger *slog.Logger) bool {
	// If neither desired_logs nor groups specified, process all applications (backward compatibility)
	if len(config.DesiredLogs) == 0 && len(config.Groups) == 0 {
		return true
	}

	// Collect all allowed applications from both desired_logs and groups
	allowedApplications := make(map[string]bool)

	// Process desired_logs field
	for _, app := range config.DesiredLogs {
		if app != "" {
			allowedApplications[app] = true
		}
	}

	// Process groups field
	if len(config.Groups) > 0 {
		expandedApps := ExpandGroupsToApplications(config.Groups, logger)
		for _, app := range expandedApps {
			allowedApplications[app] = true
		}
	}

	// If we still have no allowed applications after processing, process all applications
	if len(allowedApplications) == 0 {
		logger.Warn("no valid applications found in desired_logs or groups, processing all applications")
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
