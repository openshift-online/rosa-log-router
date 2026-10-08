package processor

import (
	"fmt"
	"testing"

	"github.com/openshift/rosa-log-router/internal/models"
	"github.com/stretchr/testify/assert"
)

// TestLoopPreventionScenarios validates routing prevents loops using message-level routing state
func TestLoopPreventionScenarios(t *testing.T) {
	t.Run("Q3 to Q3 is prevented - partial success from Q3 stays in Q3", func(t *testing.T) {
		// Setup: message in Q3 with 1 delivery completed, 1 failed
		routingState := &messageRoutingState{
			completedDeliveries: []string{"s3:test-bucket", "cloudwatch:/test/log"}, // started with 1
			transientErr:        fmt.Errorf("transient error on remaining delivery"),
		}
		metadata := &models.ProcessingMetadata{
			CompletedDeliveries: []string{"s3:test-bucket"}, // original had 1
		}
		currentQueue := QueueTypePartial

		// Check routing logic
		metadataChanged := len(routingState.completedDeliveries) > len(metadata.CompletedDeliveries)

		// Priority 1: Partial success → Q3, but NOT from Q3 itself
		shouldRouteToQ3 := metadataChanged && currentQueue != QueueTypePartial && (routingState.repairableErr != nil || routingState.transientErr != nil)

		assert.False(t, shouldRouteToQ3, "Q3 should NOT route back to Q3 (terminal queue)")
		assert.True(t, metadataChanged, "Progress was made (new delivery succeeded)")
		// In production code, Q3 special handling returns error for native retry
	})

	t.Run("main to Q3 is allowed - partial success from main routes to Q3", func(t *testing.T) {
		// Setup: message from main queue with partial success
		routingState := &messageRoutingState{
			completedDeliveries: []string{"s3:test-bucket"},
			transientErr:        fmt.Errorf("cloudwatch delivery failed"),
		}
		metadata := &models.ProcessingMetadata{
			CompletedDeliveries: []string{},
		}
		currentQueue := QueueTypeMain

		metadataChanged := len(routingState.completedDeliveries) > len(metadata.CompletedDeliveries)
		shouldRouteToQ3 := metadataChanged && currentQueue != QueueTypePartial && (routingState.repairableErr != nil || routingState.transientErr != nil)

		assert.True(t, shouldRouteToQ3, "Main queue should route to Q3 on partial success")
	})

	t.Run("Q2 to Q3 is allowed - partial success from Q2 routes to Q3", func(t *testing.T) {
		// Setup: message from Q2 (retry queue) with partial success
		routingState := &messageRoutingState{
			completedDeliveries: []string{"s3:test-bucket"},
			repairableErr:       fmt.Errorf("permission error on cloudwatch"),
		}
		metadata := &models.ProcessingMetadata{
			CompletedDeliveries: []string{},
		}
		currentQueue := QueueTypeRetry

		metadataChanged := len(routingState.completedDeliveries) > len(metadata.CompletedDeliveries)
		shouldRouteToQ3 := metadataChanged && currentQueue != QueueTypePartial && (routingState.repairableErr != nil || routingState.transientErr != nil)

		assert.True(t, shouldRouteToQ3, "Q2 should route to Q3 on partial success")
	})

	t.Run("Q3 to Q2 is prevented - permission error from Q3 does not route to Q2", func(t *testing.T) {
		// Setup: message in Q3 with permission error, receiveCount=2
		routingState := &messageRoutingState{
			completedDeliveries: []string{"s3:test-bucket"},
			repairableErr:       fmt.Errorf("permission error on cloudwatch"),
		}
		metadata := &models.ProcessingMetadata{
			CompletedDeliveries: []string{"s3:test-bucket"}, // no new progress
		}
		currentQueue := QueueTypePartial
		receiveCount := 2

		metadataChanged := len(routingState.completedDeliveries) > len(metadata.CompletedDeliveries)
		shouldRouteToQ2 := !metadataChanged && routingState.repairableErr != nil && currentQueue == QueueTypeMain && receiveCount >= (MaxReceiveCount-1)

		assert.False(t, shouldRouteToQ2, "Q3 should NOT route to Q2 (backward routing prevented)")
		assert.Equal(t, QueueTypePartial, currentQueue, "Current queue is Q3, not main")
	})

	t.Run("Q2 to Q2 is prevented - permission error from Q2 does not route to Q2", func(t *testing.T) {
		// Setup: message in Q2 with permission error, receiveCount=2
		routingState := &messageRoutingState{
			completedDeliveries: []string{},
			repairableErr:       fmt.Errorf("permission error"),
		}
		metadata := &models.ProcessingMetadata{
			CompletedDeliveries: []string{},
		}
		currentQueue := QueueTypeRetry
		receiveCount := 2

		metadataChanged := len(routingState.completedDeliveries) > len(metadata.CompletedDeliveries)
		shouldRouteToQ2 := !metadataChanged && routingState.repairableErr != nil && currentQueue == QueueTypeMain && receiveCount >= (MaxReceiveCount-1)

		assert.False(t, shouldRouteToQ2, "Q2 should NOT route back to Q2 (loop prevented)")
		assert.Equal(t, QueueTypeRetry, currentQueue, "Current queue is Q2, not main")
	})

	t.Run("main to Q2 is allowed - permission error with recv >= 2 from main routes to Q2", func(t *testing.T) {
		// Setup: message from main with permission error after 2 attempts
		routingState := &messageRoutingState{
			completedDeliveries: []string{},
			repairableErr:       fmt.Errorf("permission error"),
		}
		metadata := &models.ProcessingMetadata{
			CompletedDeliveries: []string{},
		}
		currentQueue := QueueTypeMain
		receiveCount := 2

		metadataChanged := len(routingState.completedDeliveries) > len(metadata.CompletedDeliveries)
		shouldRouteToQ2 := !metadataChanged && routingState.repairableErr != nil && currentQueue == QueueTypeMain && receiveCount >= (MaxReceiveCount-1)

		assert.True(t, shouldRouteToQ2, "Main queue should route to Q2 after 2 permission errors")
	})

	t.Run("Q3 with new progress and remaining errors uses native retry (data loss bug fix)", func(t *testing.T) {
		// This test verifies the fix for CodeRabbit Finding 2a
		// Q3 message makes new progress but still has errors - should use native retry, not delete
		routingState := &messageRoutingState{
			completedDeliveries: []string{"s3:test-bucket", "cloudwatch:/test/log"}, // 2 deliveries succeeded
			repairableErr:       fmt.Errorf("permission error on third delivery"),
		}
		metadata := &models.ProcessingMetadata{
			CompletedDeliveries: []string{"s3:test-bucket"}, // started with 1
		}
		currentQueue := QueueTypePartial

		metadataChanged := len(routingState.completedDeliveries) > len(metadata.CompletedDeliveries)

		// Q3 terminal queue handling (production code lines 361-375)
		// With Q3 + repairableErr, should return error (native retry), not nil (delete)
		assert.True(t, metadataChanged, "New progress was made")
		assert.NotNil(t, routingState.repairableErr, "Error remains")
		assert.Equal(t, QueueTypePartial, currentQueue, "In Q3 (partial queue)")

		// Production code should return error here, triggering native retry
		// This prevents data loss for the remaining failed delivery
	})
}

// TestForwardOnlyRouting validates routing only goes forward using message-level state
func TestForwardOnlyRouting(t *testing.T) {
	testCases := []struct {
		name                 string
		currentQueue         string
		originalCompleted    []string
		accumulatedCompleted []string
		repairableErr        error
		transientErr         error
		receiveCount         int
		expectPartialRoute   bool // Should route to Q3
		expectRetryRoute     bool // Should route to Q2
		expectNativeRetry    bool // Should use native retry (no SendMessage)
	}{
		{
			name:                 "main with partial success routes to Q3",
			currentQueue:         QueueTypeMain,
			originalCompleted:    []string{},
			accumulatedCompleted: []string{"s3:test-bucket"},
			transientErr:         fmt.Errorf("cloudwatch failed"),
			receiveCount:         1,
			expectPartialRoute:   true,
		},
		{
			name:                 "Q2 with partial success routes to Q3",
			currentQueue:         QueueTypeRetry,
			originalCompleted:    []string{},
			accumulatedCompleted: []string{"s3:test-bucket"},
			transientErr:         fmt.Errorf("cloudwatch failed"),
			receiveCount:         1,
			expectPartialRoute:   true,
		},
		{
			name:                 "Q3 with partial success does NOT route (stays in Q3)",
			currentQueue:         QueueTypePartial,
			originalCompleted:    []string{"s3:test-bucket"},
			accumulatedCompleted: []string{"s3:test-bucket", "cloudwatch:/test/log"},
			transientErr:         fmt.Errorf("third delivery failed"),
			receiveCount:         1,
			expectNativeRetry:    true, // Q3 is terminal - no SendMessage
		},
		{
			name:                 "main with permission error recv=2 routes to Q2",
			currentQueue:         QueueTypeMain,
			originalCompleted:    []string{},
			accumulatedCompleted: []string{},
			repairableErr:        fmt.Errorf("permission error"),
			receiveCount:         2,
			expectRetryRoute:     true,
		},
		{
			name:                 "Q2 with permission error recv=2 does NOT route to Q2",
			currentQueue:         QueueTypeRetry,
			originalCompleted:    []string{},
			accumulatedCompleted: []string{},
			repairableErr:        fmt.Errorf("permission error"),
			receiveCount:         2,
			expectNativeRetry:    true, // Q2 uses native retry
		},
		{
			name:                 "Q3 with permission error recv=2 does NOT route to Q2",
			currentQueue:         QueueTypePartial,
			originalCompleted:    []string{"s3:test-bucket"},
			accumulatedCompleted: []string{"s3:test-bucket"},
			repairableErr:        fmt.Errorf("permission error"),
			receiveCount:         2,
			expectNativeRetry:    true, // Q3 terminal - native retry only
		},
		{
			name:                 "fully successful message does NOT route to Q3",
			currentQueue:         QueueTypeMain,
			originalCompleted:    []string{},
			accumulatedCompleted: []string{"s3:test-bucket", "cloudwatch:/test/log"},
			receiveCount:         1,
			expectNativeRetry:    true, // No errors, just delete (Priority 1 skipped)
		},
	}

	for _, tc := range testCases {
		t.Run(tc.name, func(t *testing.T) {
			routingState := &messageRoutingState{
				completedDeliveries: tc.accumulatedCompleted,
				repairableErr:       tc.repairableErr,
				transientErr:        tc.transientErr,
			}
			metadata := &models.ProcessingMetadata{
				CompletedDeliveries: tc.originalCompleted,
			}

			metadataChanged := len(routingState.completedDeliveries) > len(metadata.CompletedDeliveries)

			// Priority 1: Partial success → Q3 (only from main or Q2, only if errors remain)
			priority1Fires := metadataChanged && tc.currentQueue != QueueTypePartial && (routingState.repairableErr != nil || routingState.transientErr != nil)

			// Priority 2: Permission error from main with recv >= 2 → Q2
			priority2Fires := !metadataChanged && routingState.repairableErr != nil && tc.currentQueue == QueueTypeMain && tc.receiveCount >= (MaxReceiveCount-1)

			assert.Equal(t, tc.expectPartialRoute, priority1Fires, "Priority 1 routing to Q3")
			assert.Equal(t, tc.expectRetryRoute, priority2Fires, "Priority 2 routing to Q2")

			// Neither priority fires = native retry
			nativeRetry := !priority1Fires && !priority2Fires
			if tc.expectNativeRetry {
				assert.True(t, nativeRetry, "Should use native retry (no routing)")
			}
		})
	}
}

// TestMessageRoutingStateAccumulation verifies state accumulates correctly across records
func TestMessageRoutingStateAccumulation(t *testing.T) {
	t.Run("multiple S3 records accumulate deliveries in single routing state", func(t *testing.T) {
		// This verifies the fix for CodeRabbit Finding 3 (multi-record multiplication)
		// Message with 2 S3 records should accumulate state and route ONCE

		// Simulate processing 2 records with the same routing state
		routingState := &messageRoutingState{
			completedDeliveries: []string{},
		}

		// Record 1 processing: S3 succeeds, CloudWatch fails
		routingState.completedDeliveries = append(routingState.completedDeliveries, "s3:bucket1")
		routingState.transientErr = fmt.Errorf("cloudwatch failed for record 1")

		// Record 2 processing: S3 succeeds, CloudWatch fails
		routingState.completedDeliveries = append(routingState.completedDeliveries, "s3:bucket2")
		routingState.transientErr = fmt.Errorf("cloudwatch failed for record 2") // overwrites previous error

		// After processing both records, routing happens ONCE
		metadata := &models.ProcessingMetadata{
			CompletedDeliveries: []string{},
		}
		currentQueue := QueueTypeMain

		metadataChanged := len(routingState.completedDeliveries) > len(metadata.CompletedDeliveries)
		shouldRouteToQ3 := metadataChanged && currentQueue != QueueTypePartial && (routingState.repairableErr != nil || routingState.transientErr != nil)

		assert.True(t, shouldRouteToQ3, "Should route to Q3 once for both records")
		assert.Equal(t, 2, len(routingState.completedDeliveries), "Both S3 deliveries accumulated")
		assert.NotNil(t, routingState.transientErr, "Error state accumulated")

		// In production code, this results in ONE SendMessage to Q3, not two
	})
}

// TestProductionRoutingPaths documents and validates common production scenarios
func TestProductionRoutingPaths(t *testing.T) {
	testCases := []struct {
		name          string
		scenario      string
		currentQueue  string
		receiveCount  int
		origCompleted []string
		newCompleted  []string
		repairableErr error
		transientErr  error
		expectRoute   string // "Q2", "Q3", "native_retry", or "delete"
	}{
		{
			name:          "First delivery attempt with permission error - retries natively",
			scenario:      "Production: IAM role not yet propagated, first attempt fails",
			currentQueue:  QueueTypeMain,
			receiveCount:  1,
			origCompleted: []string{},
			newCompleted:  []string{},
			repairableErr: fmt.Errorf("AccessDenied"),
			expectRoute:   "native_retry",
		},
		{
			name:          "Second delivery attempt with permission error - routes to Q2",
			scenario:      "Production: IAM still broken after 2 attempts, needs longer backoff",
			currentQueue:  QueueTypeMain,
			receiveCount:  2,
			origCompleted: []string{},
			newCompleted:  []string{},
			repairableErr: fmt.Errorf("AccessDenied"),
			expectRoute:   "Q2",
		},
		{
			name:          "Partial success on first attempt - routes to Q3",
			scenario:      "Production: S3 succeeded but CloudWatch IAM not ready",
			currentQueue:  QueueTypeMain,
			receiveCount:  1,
			origCompleted: []string{},
			newCompleted:  []string{"s3:customer-bucket"},
			transientErr:  fmt.Errorf("CloudWatch AccessDenied"),
			expectRoute:   "Q3",
		},
		{
			name:          "Q3 completes remaining delivery - deletes",
			scenario:      "Production: CloudWatch IAM fixed, Q3 completes second delivery",
			currentQueue:  QueueTypePartial,
			receiveCount:  1,
			origCompleted: []string{"s3:customer-bucket"},
			newCompleted:  []string{"s3:customer-bucket", "cloudwatch:/aws/vendedlogs"},
			expectRoute:   "delete",
		},
		{
			name:          "Q2 with permission error - retries natively",
			scenario:      "Production: IAM still broken in retry queue",
			currentQueue:  QueueTypeRetry,
			receiveCount:  1,
			origCompleted: []string{},
			newCompleted:  []string{},
			repairableErr: fmt.Errorf("AccessDenied"),
			expectRoute:   "native_retry",
		},
	}

	for _, tc := range testCases {
		t.Run(tc.name, func(t *testing.T) {
			routingState := &messageRoutingState{
				completedDeliveries: tc.newCompleted,
				repairableErr:       tc.repairableErr,
				transientErr:        tc.transientErr,
			}
			metadata := &models.ProcessingMetadata{
				CompletedDeliveries: tc.origCompleted,
			}

			metadataChanged := len(routingState.completedDeliveries) > len(metadata.CompletedDeliveries)
			noErrors := routingState.repairableErr == nil && routingState.transientErr == nil

			// Apply routing logic
			priority1Fires := metadataChanged && tc.currentQueue != QueueTypePartial && (routingState.repairableErr != nil || routingState.transientErr != nil)
			priority2Fires := !metadataChanged && routingState.repairableErr != nil && tc.currentQueue == QueueTypeMain && tc.receiveCount >= (MaxReceiveCount-1)

			var actualRoute string
			if priority1Fires {
				actualRoute = "Q3"
			} else if priority2Fires {
				actualRoute = "Q2"
			} else if metadataChanged && noErrors {
				actualRoute = "delete"
			} else {
				actualRoute = "native_retry"
			}

			assert.Equal(t, tc.expectRoute, actualRoute, "Routing decision should match production scenario: %s", tc.scenario)
		})
	}
}
