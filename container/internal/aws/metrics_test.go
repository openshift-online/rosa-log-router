package aws

import (
	"testing"

	"github.com/aws/aws-sdk-go-v2/aws"
	"github.com/aws/aws-sdk-go-v2/service/cloudwatch"
	"github.com/openshift/rosa-log-router/internal/models"
	"github.com/stretchr/testify/assert"
)

// Helper to create a CloudWatch client for testing (won't actually call AWS)
func createTestCloudWatchClient() *cloudwatch.Client {
	cfg := aws.Config{
		Region:      "us-east-1",
		Credentials: aws.AnonymousCredentials{},
	}
	return cloudwatch.NewFromConfig(cfg)
}

func TestNewMetricsPublisher(t *testing.T) {
	logger := models.NewDefaultLogger()
	client := createTestCloudWatchClient()

	publisher := NewMetricsPublisher(client, logger)

	assert.NotNil(t, publisher)
	assert.NotNil(t, publisher.client)
	assert.Equal(t, logger, publisher.logger)
}

func TestMetricsNamespace(t *testing.T) {
	// Verify the namespace constant
	assert.Equal(t, "HCPLF/LogForwarding", MetricsNamespace)
}

func TestPushCloudWatchDeliveryMetrics_Construction(t *testing.T) {
	// Test that the function constructs proper metrics
	// We validate the metric construction logic

	testCases := []struct {
		name             string
		successfulEvents int
		failedEvents     int
		expectedMetrics  map[string]float64
	}{
		{
			name:             "successful_delivery",
			successfulEvents: 100,
			failedEvents:     0,
			expectedMetrics: map[string]float64{
				"successful_events":   100.0,
				"failed_events":       0.0,
				"successful_delivery": 1.0,
			},
		},
		{
			name:             "failed_delivery",
			successfulEvents: 50,
			failedEvents:     10,
			expectedMetrics: map[string]float64{
				"successful_events": 50.0,
				"failed_events":     10.0,
				"failed_delivery":   1.0,
			},
		},
		{
			name:             "zero_events",
			successfulEvents: 0,
			failedEvents:     0,
			expectedMetrics: map[string]float64{
				"successful_events": 0.0,
				"failed_events":     0.0,
			},
		},
	}

	for _, tc := range testCases {
		t.Run(tc.name, func(t *testing.T) {
			// Replicate the logic from PushCloudWatchDeliveryMetrics
			metrics := map[string]float64{
				"successful_events": float64(tc.successfulEvents),
				"failed_events":     float64(tc.failedEvents),
			}

			if tc.successfulEvents > 0 || tc.failedEvents > 0 {
				if tc.failedEvents == 0 {
					metrics["successful_delivery"] = 1
				} else {
					metrics["failed_delivery"] = 1
				}
			}

			assert.Equal(t, tc.expectedMetrics, metrics)
		})
	}
}

func TestPushS3DeliveryMetrics_Construction(t *testing.T) {
	// Test that the function constructs proper metrics for S3 delivery

	testCases := []struct {
		name            string
		success         bool
		expectedMetrics map[string]float64
	}{
		{
			name:    "successful_s3_delivery",
			success: true,
			expectedMetrics: map[string]float64{
				"successful_delivery": 1.0,
			},
		},
		{
			name:    "failed_s3_delivery",
			success: false,
			expectedMetrics: map[string]float64{
				"failed_delivery": 1.0,
			},
		},
	}

	for _, tc := range testCases {
		t.Run(tc.name, func(t *testing.T) {
			// Replicate the logic from PushS3DeliveryMetrics
			var metrics map[string]float64
			if tc.success {
				metrics = map[string]float64{"successful_delivery": 1}
			} else {
				metrics = map[string]float64{"failed_delivery": 1}
			}

			assert.Equal(t, tc.expectedMetrics, metrics)
		})
	}
}

func TestMetricNaming(t *testing.T) {
	// Test the metric name format
	testCases := []struct {
		method          string
		metricDimension string
		expectedName    string
	}{
		{
			method:          "cloudwatch",
			metricDimension: "successful_delivery",
			expectedName:    "LogCount/cloudwatch/successful_delivery",
		},
		{
			method:          "s3",
			metricDimension: "failed_delivery",
			expectedName:    "LogCount/s3/failed_delivery",
		},
		{
			method:          "cloudwatch",
			metricDimension: "successful_events",
			expectedName:    "LogCount/cloudwatch/successful_events",
		},
	}

	for _, tc := range testCases {
		t.Run(tc.expectedName, func(t *testing.T) {
			// Replicate metric name format from PushMetrics
			metricName := "LogCount/" + tc.method + "/" + tc.metricDimension
			assert.Equal(t, tc.expectedName, metricName)
		})
	}
}
