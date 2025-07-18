# Main Terraform configuration for multi-tenant logging infrastructure

terraform {
  required_version = ">= 1.0"
  
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.1"
    }
  }

  # Recommended backend configuration (uncomment and configure)
  # backend "s3" {
  #   bucket         = "your-terraform-state-bucket"
  #   key            = "multi-tenant-logging/terraform.tfstate"
  #   region         = "us-east-1"
  #   dynamodb_table = "terraform-state-lock"
  #   encrypt        = true
  # }
}

# Configure the AWS Provider
provider "aws" {
  region = var.aws_region

  default_tags {
    tags = merge(var.common_tags, {
      TerraformManaged = "true"
      CostCenter      = var.cost_center
    })
  }
}

# Local values for computed configurations
locals {
  name_prefix = "${var.project_name}-${var.environment}"
  
  # Enhanced tags with computed values
  enhanced_tags = merge(var.common_tags, {
    TerraformManaged = "true"
    CostCenter      = var.cost_center
    Region          = var.aws_region
    Timestamp       = timestamp()
  })

  # Bucket names with random suffix to ensure uniqueness
  central_bucket_name = "${local.name_prefix}-central-${random_id.bucket_suffix.hex}"
  backup_bucket_name  = "${local.name_prefix}-backup-${random_id.bucket_suffix.hex}"
  
  # Firehose configuration
  firehose_name = "${local.name_prefix}-stream"
  
  # Lambda configuration
  lambda_function_name = "${local.name_prefix}-distributor"
  
  # DynamoDB configuration
  tenant_table_name = "${local.name_prefix}-tenant-configs"
  
  # SNS/SQS configuration
  sns_topic_name = "${local.name_prefix}-hub"
  sqs_queue_name = "${local.name_prefix}-delivery"
  
  # Conditional resource creation flags
  create_analytics_resources = var.enable_analytics
  create_vpc_endpoints      = var.enable_vpc_endpoints
  create_dlq_processor      = var.enable_dlq_processor
}

# Random ID for unique naming
resource "random_id" "bucket_suffix" {
  byte_length = 4
}

# Data sources for AWS account and region information
data "aws_caller_identity" "current" {}
data "aws_region" "current" {}
data "aws_availability_zones" "available" {
  state = "available"
}

# KMS key for encryption (optional)
resource "aws_kms_key" "logging_key" {
  count = var.kms_key_id == null ? 1 : 0
  
  description             = "KMS key for multi-tenant logging encryption"
  deletion_window_in_days = 7
  enable_key_rotation     = true

  tags = merge(local.enhanced_tags, {
    Name = "${local.name_prefix}-kms-key"
  })
}

resource "aws_kms_alias" "logging_key" {
  count         = var.kms_key_id == null ? 1 : 0
  name          = "alias/${local.name_prefix}-logging"
  target_key_id = aws_kms_key.logging_key[0].key_id
}

# CloudWatch dashboard for overall system monitoring
resource "aws_cloudwatch_dashboard" "main" {
  dashboard_name = "multi-tenant-logging-overview"

  dashboard_body = jsonencode({
    widgets = [
      {
        type   = "metric"
        x      = 0
        y      = 0
        width  = 12
        height = 6

        properties = {
          metrics = [
            ["AWS/Kinesis/Firehose", "DeliveryToS3.Records", "DeliveryStreamName", aws_kinesis_firehose_delivery_stream.central_logging.name],
            ["AWS/Kinesis/Firehose", "DeliveryToS3.Success", "DeliveryStreamName", aws_kinesis_firehose_delivery_stream.central_logging.name],
          ]
          view    = "timeSeries"
          stacked = false
          region  = var.aws_region
          title   = "Firehose Delivery Metrics"
          period  = 300
        }
      },
      {
        type   = "metric"
        x      = 12
        y      = 0
        width  = 12
        height = 6

        properties = {
          metrics = [
            ["AWS/Lambda", "Invocations", "FunctionName", aws_lambda_function.log_distributor.function_name],
            ["AWS/Lambda", "Errors", "FunctionName", aws_lambda_function.log_distributor.function_name],
            ["AWS/Lambda", "Duration", "FunctionName", aws_lambda_function.log_distributor.function_name],
          ]
          view    = "timeSeries"
          stacked = false
          region  = var.aws_region
          title   = "Lambda Function Metrics"
          period  = 300
        }
      },
      {
        type   = "metric"
        x      = 0
        y      = 6
        width  = 12
        height = 6

        properties = {
          metrics = [
            ["AWS/SQS", "ApproximateNumberOfVisibleMessages", "QueueName", aws_sqs_queue.log_delivery.name],
            ["AWS/SQS", "ApproximateAgeOfOldestMessage", "QueueName", aws_sqs_queue.log_delivery.name],
          ]
          view    = "timeSeries"
          stacked = false
          region  = var.aws_region
          title   = "SQS Queue Metrics"
          period  = 300
        }
      },
      {
        type   = "metric"
        x      = 12
        y      = 6
        width  = 12
        height = 6

        properties = {
          metrics = [
            ["AWS/DynamoDB", "ConsumedReadCapacityUnits", "TableName", aws_dynamodb_table.tenant_configurations.name],
            ["AWS/DynamoDB", "ConsumedWriteCapacityUnits", "TableName", aws_dynamodb_table.tenant_configurations.name],
          ]
          view    = "timeSeries"
          stacked = false
          region  = var.aws_region
          title   = "DynamoDB Metrics"
          period  = 300
        }
      }
    ]
  })

  tags = local.enhanced_tags
}

# Cost anomaly detection for the logging pipeline
resource "aws_ce_anomaly_detector" "logging_costs" {
  name         = "${local.name_prefix}-cost-anomaly"
  monitor_type = "DIMENSIONAL"

  specification = jsonencode({
    Dimension = "SERVICE"
    MatchOptions = ["EQUALS"]
    Values = [
      "Amazon Kinesis Firehose",
      "Amazon Simple Storage Service",
      "AWS Lambda",
      "Amazon Simple Queue Service",
      "Amazon DynamoDB"
    ]
  })

  tags = local.enhanced_tags
}

# Cost budget for the logging pipeline
resource "aws_budgets_budget" "logging_budget" {
  name         = "${local.name_prefix}-monthly-budget"
  budget_type  = "COST"
  limit_amount = "1000"  # Adjust based on expected costs
  limit_unit   = "USD"
  time_unit    = "MONTHLY"
  
  cost_filters = {
    Tag = [
      "Project:${var.project_name}",
      "Environment:${var.environment}"
    ]
  }

  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                 = 80
    threshold_type            = "PERCENTAGE"
    notification_type         = "ACTUAL"
    subscriber_email_addresses = var.alert_email_endpoints
  }

  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                 = 100
    threshold_type            = "PERCENTAGE"
    notification_type          = "FORECASTED"
    subscriber_email_addresses = var.alert_email_endpoints
  }

  tags = local.enhanced_tags
}

# Resource groups for easier management
resource "aws_resourcegroups_group" "logging_infrastructure" {
  name        = "${local.name_prefix}-infrastructure"
  description = "Resources for multi-tenant logging infrastructure"

  resource_query {
    query = jsonencode({
      ResourceTypeFilters = [
        "AWS::AllSupported"
      ]
      TagFilters = [
        {
          Key    = "Project"
          Values = [var.project_name]
        },
        {
          Key    = "Environment"
          Values = [var.environment]
        }
      ]
    })
  }

  tags = local.enhanced_tags
}