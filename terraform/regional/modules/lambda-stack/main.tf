# Container-based Lambda functions for multi-tenant log distribution

terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

# Local values
locals {
  common_tags = merge(var.tags, {
    Project     = var.project_name
    Environment = var.environment
    ManagedBy   = "terraform"
    StackType   = "lambda-functions"
  })
}

# Lambda Execution Role
resource "aws_iam_role" "lambda_execution_role" {
  name = "${var.project_name}-${var.environment}-lambda-execution-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          Service = "lambda.amazonaws.com"
        }
        Action = "sts:AssumeRole"
      }
    ]
  })

  tags = local.common_tags
}

resource "aws_iam_role_policy_attachment" "lambda_basic_execution" {
  role       = aws_iam_role.lambda_execution_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_role_policy_attachment" "lambda_sqs_execution" {
  role       = aws_iam_role.lambda_execution_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaSQSQueueExecutionRole"
}

resource "aws_iam_role_policy" "log_processor_policy" {
  name = "LogProcessorPolicy"
  role = aws_iam_role.lambda_execution_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      # DynamoDB access for tenant configurations
      {
        Effect = "Allow"
        Action = [
          "dynamodb:GetItem",
          "dynamodb:Query",
          "dynamodb:BatchGetItem"
        ]
        Resource = var.tenant_config_table_arn
      },
      # S3 access for reading log files
      {
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:GetBucketLocation",
          "s3:ListBucket"
        ]
        Resource = [
          var.central_logging_bucket_arn,
          "${var.central_logging_bucket_arn}/*"
        ]
      },
      # Assume the central log distribution role
      {
        Effect = "Allow"
        Action = "sts:AssumeRole"
        Resource = var.central_log_distribution_role_arn
      },
      # KMS access for encrypted S3 buckets
      {
        Effect = "Allow"
        Action = [
          "kms:Decrypt",
          "kms:DescribeKey"
        ]
        Resource = "*"
      }
    ]
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
  function_name = "${var.project_name}-${var.environment}-log-distributor"
  package_type  = "Image"
  image_uri     = var.ecr_image_uri
  role          = aws_iam_role.lambda_execution_role.arn

  environment {
    variables = {
      TENANT_CONFIG_TABLE               = var.tenant_config_table_name
      MAX_BATCH_SIZE                   = "1000"
      RETRY_ATTEMPTS                   = "3"
      CENTRAL_LOG_DISTRIBUTION_ROLE_ARN = var.central_log_distribution_role_arn
      EXECUTION_MODE                   = "lambda"
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