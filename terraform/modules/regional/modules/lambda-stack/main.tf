# Container-based Lambda functions for multi-tenant log distribution

terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }
}

# Data sources
data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

# Local values
locals {
  common_tags = {
    Project     = var.project_name
    Environment = var.environment
    StackType   = "lambda-stack"
  }
}


# CloudWatch Log Group for Lambda functions
resource "aws_cloudwatch_log_group" "log_distributor_log_group" {
  name              = "/aws/lambda/${var.project_name}-${var.environment}-log-distributor"
  retention_in_days = 14
  tags              = local.common_tags
}

# Container-based Lambda function for log distribution
resource "aws_lambda_function" "log_distributor_function" {
  function_name = "${var.project_name}-${var.environment}-log-distributor"
  role          = var.lambda_execution_role_arn
  package_type  = "Image"
  image_uri     = "${data.aws_caller_identity.current.account_id}.dkr.ecr.${data.aws_region.current.id}.amazonaws.com/${var.processor_image}"

  environment {
    variables = {
      TENANT_CONFIG_TABLE               = var.tenant_config_table_name
      MAX_BATCH_SIZE                    = "1000"
      RETRY_ATTEMPTS                    = "3"
      CENTRAL_LOG_DISTRIBUTION_ROLE_ARN = var.central_log_distribution_role_arn
      SQS_QUEUE_URL                     = var.sqs_queue_url
    }
  }

  timeout     = 300
  memory_size = 512

  tags = local.common_tags

  depends_on = [aws_cloudwatch_log_group.log_distributor_log_group]
}

# SNS topic for delivery failure alerts — routes to PagerDuty when configured.
resource "aws_sns_topic" "delivery_failure_alerts" {
  name = "${var.project_name}-${var.environment}-delivery-failure-alerts"
  tags = local.common_tags
}

# PagerDuty subscription — only created when the integration URL is provided.
resource "aws_sns_topic_subscription" "pagerduty" {
  count     = var.pagerduty_integration_url != "" ? 1 : 0
  topic_arn = aws_sns_topic.delivery_failure_alerts.arn
  protocol  = "https"
  endpoint  = var.pagerduty_integration_url
}

# CloudWatch alarm: fires when any delivery failure occurs across all tenants.
# The Lambda publishes LogCount/{method}/failed_delivery metrics with and without
# a Tenant dimension. This alarm monitors the aggregate (no Tenant dimension)
# so a single alarm covers all tenants in the region.
resource "aws_cloudwatch_metric_alarm" "delivery_failure_alarm" {
  alarm_name          = "${var.project_name}-${var.environment}-delivery-failure"
  alarm_description   = "Log delivery failures detected. Check per-tenant metrics in HCPLF/LogForwarding namespace for affected tenants."
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  threshold           = 0
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.delivery_failure_alerts.arn]
  ok_actions          = [aws_sns_topic.delivery_failure_alerts.arn]

  metric_query {
    id          = "cw_failures"
    return_data = false

    metric {
      metric_name = "LogCount/cloudwatch/failed_delivery"
      namespace   = "HCPLF/LogForwarding"
      period      = 300
      stat        = "Sum"
    }
  }

  metric_query {
    id          = "s3_failures"
    return_data = false

    metric {
      metric_name = "LogCount/s3/failed_delivery"
      namespace   = "HCPLF/LogForwarding"
      period      = 300
      stat        = "Sum"
    }
  }

  metric_query {
    id          = "total_failures"
    expression  = "cw_failures + s3_failures"
    label       = "Total Delivery Failures"
    return_data = true
  }

  tags = local.common_tags
}

# Event Source Mapping for SQS to Lambda
resource "aws_lambda_event_source_mapping" "log_delivery_event_source_mapping" {
  event_source_arn                   = var.sqs_queue_arn
  function_name                      = aws_lambda_function.log_distributor_function.arn
  batch_size                         = 10
  maximum_batching_window_in_seconds = 5
  function_response_types            = ["ReportBatchItemFailures"]
}