package aws

import (
	"context"
	"fmt"
	"log/slog"

	"github.com/aws/aws-sdk-go-v2/aws"
	"github.com/aws/aws-sdk-go-v2/service/cloudwatch"
	"github.com/aws/aws-sdk-go-v2/service/cloudwatch/types"
)

const (
	// MetricsNamespace is the CloudWatch namespace for log forwarding metrics
	MetricsNamespace = "HCPLF/LogForwarding"
)

// MetricsPublisher handles publishing metrics to CloudWatch
type MetricsPublisher struct {
	client *cloudwatch.Client
	logger *slog.Logger
}

// NewMetricsPublisher creates a new metrics publisher
func NewMetricsPublisher(client *cloudwatch.Client, logger *slog.Logger) *MetricsPublisher {
	return &MetricsPublisher{
		client: client,
		logger: logger,
	}
}

// PushMetrics publishes metrics to CloudWatch
// method is either "cloudwatch" or "s3"
// metricsData is a map of metric names to values (e.g., {"successful_delivery": 1, "failed_delivery": 0})
func (p *MetricsPublisher) PushMetrics(ctx context.Context, tenantID, method string, metricsData map[string]float64) error {
	if len(metricsData) == 0 {
		p.logger.Debug("no metrics to push")
		return nil
	}

	metricData := make([]types.MetricDatum, 0, len(metricsData))

	for metricDimension, value := range metricsData {
		metricName := fmt.Sprintf("LogCount/%s/%s", method, metricDimension)

		metricData = append(metricData, types.MetricDatum{
			MetricName: aws.String(metricName),
			Dimensions: []types.Dimension{
				{
					Name:  aws.String("Tenant"),
					Value: aws.String(tenantID),
				},
			},
			Value: aws.Float64(value),
			Unit:  types.StandardUnitCount,
		})
	}

	_, err := p.client.PutMetricData(ctx, &cloudwatch.PutMetricDataInput{
		Namespace:  aws.String(MetricsNamespace),
		MetricData: metricData,
	})

	if err != nil {
		p.logger.Error("failed to publish metric to CloudWatch",
			"tenant_id", tenantID,
			"method", method,
			"error", err)
		return fmt.Errorf("failed to publish metrics: %w", err)
	}

	p.logger.Debug("successfully published metrics to CloudWatch",
		"tenant_id", tenantID,
		"method", method,
		"metric_count", len(metricData))

	return nil
}

// PushCloudWatchDeliveryMetrics is a convenience method for CloudWatch delivery metrics
func (p *MetricsPublisher) PushCloudWatchDeliveryMetrics(ctx context.Context, tenantID string, successfulEvents, failedEvents int) {
	metrics := map[string]float64{
		"successful_events": float64(successfulEvents),
		"failed_events":     float64(failedEvents),
	}

	// Only add successful_delivery if there were events
	if successfulEvents > 0 || failedEvents > 0 {
		if failedEvents == 0 {
			metrics["successful_delivery"] = 1
		} else {
			metrics["failed_delivery"] = 1
		}
	}

	if err := p.PushMetrics(ctx, tenantID, "cloudwatch", metrics); err != nil {
		p.logger.Error("failed to write metrics to CloudWatch for CloudWatch delivery",
			"tenant_id", tenantID,
			"error", err)
	}
}

// PushS3DeliveryMetrics is a convenience method for S3 delivery metrics
func (p *MetricsPublisher) PushS3DeliveryMetrics(ctx context.Context, tenantID string, success bool) {
	var metrics map[string]float64
	if success {
		metrics = map[string]float64{"successful_delivery": 1}
	} else {
		metrics = map[string]float64{"failed_delivery": 1}
	}

	if err := p.PushMetrics(ctx, tenantID, "s3", metrics); err != nil {
		p.logger.Error("failed to write metrics to CloudWatch for S3 delivery",
			"tenant_id", tenantID,
			"error", err)
	}
}
