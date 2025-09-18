# Container-based Lambda functions for multi-tenant log distribution

terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

# Data sources
data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

# Local values
locals {
  common_tags = merge(var.tags, {
    Project     = var.project_name
    Environment = var.environment
    ManagedBy   = "terraform"
    StackType   = "lambda-functions"
  })
}


# CloudWatch Log Group for Lambda functions
resource "aws_cloudwatch_log_group" "log_distributor_log_group" {
  name              = "/aws/lambda/${var.project_name}-${var.environment}-log-distributor"
  retention_in_days = 14

  tags = local.common_tags
}

# Container-based Lambda function for log distribution
resource "aws_lambda_function" "log_distributor_function" {
  function_name    = "${var.project_name}-${var.environment}-log-distributor"
  role             = var.lambda_execution_role_arn
  filename         = "../../modules/regional/modules/lambda-stack/log-processor.zip"
  handler          = "log_processor.lambda_handler"
  runtime          = "python3.11"
  source_code_hash = filebase64sha256("../../modules/regional/modules/lambda-stack/log-processor.zip")

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

  tags = merge(local.common_tags, {
    Name = "${var.project_name}-${var.environment}-log-distributor"
  })

  depends_on = [aws_cloudwatch_log_group.log_distributor_log_group]
}

# Event Source Mapping for SQS to Lambda
resource "aws_lambda_event_source_mapping" "log_delivery_event_source_mapping" {
  event_source_arn                   = var.sqs_queue_arn
  function_name                      = aws_lambda_function.log_distributor_function.arn
  batch_size                         = 10
  maximum_batching_window_in_seconds = 5
  function_response_types            = ["ReportBatchItemFailures"]
}