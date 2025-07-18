# Lambda function for log distribution
resource "aws_lambda_function" "log_distributor" {
  filename         = "log_distributor.zip"
  function_name    = "log-distributor"
  role            = aws_iam_role.log_distributor_role.arn
  handler         = "log_distributor.lambda_handler"
  runtime         = "python3.11"
  timeout         = 900  # 15 minutes
  memory_size     = 1024  # 1 GB

  # Environment variables
  environment {
    variables = {
      TENANT_CONFIG_TABLE                    = aws_dynamodb_table.tenant_configurations.name
      MAX_BATCH_SIZE                        = "1000"
      RETRY_ATTEMPTS                        = "3"
      LOG_LEVEL                             = "INFO"
      CENTRAL_LOG_DISTRIBUTION_ROLE_ARN     = aws_iam_role.central_log_distribution_role.arn
    }
  }

  # VPC configuration (if needed for security)
  dynamic "vpc_config" {
    for_each = var.lambda_vpc_config != null ? [var.lambda_vpc_config] : []
    content {
      subnet_ids         = vpc_config.value.subnet_ids
      security_group_ids = vpc_config.value.security_group_ids
    }
  }

  # Dead letter queue configuration
  dead_letter_config {
    target_arn = aws_sqs_queue.lambda_dlq.arn
  }

  # Reserved concurrency to prevent runaway costs
  reserved_concurrency = var.lambda_reserved_concurrency

  tags = {
    Name        = "log-distributor"
    Environment = "production"
    Purpose     = "multi-tenant-logging"
  }

  depends_on = [
    aws_iam_role_policy_attachment.log_distributor_basic,
    aws_iam_role_policy.log_distributor_policy,
    aws_cloudwatch_log_group.log_distributor,
  ]
}

# CloudWatch log group for Lambda
resource "aws_cloudwatch_log_group" "log_distributor" {
  name              = "/aws/lambda/log-distributor"
  retention_in_days = 30

  tags = {
    Name        = "log-distributor-logs"
    Environment = "production"
    Purpose     = "multi-tenant-logging"
  }
}

# Lambda event source mapping for SQS
resource "aws_lambda_event_source_mapping" "log_delivery_queue" {
  event_source_arn = aws_sqs_queue.log_delivery.arn
  function_name    = aws_lambda_function.log_distributor.arn
  
  # Batch configuration for cost optimization
  batch_size                         = 10
  maximum_batching_window_in_seconds = 5
  
  # Parallelization settings
  parallelization_factor = 2
  
  # Error handling
  function_response_types = ["ReportBatchItemFailures"]
  
  # Scaling configuration
  scaling_config {
    maximum_concurrency = var.lambda_max_concurrency
  }
}

# Dead letter queue for Lambda failures
resource "aws_sqs_queue" "lambda_dlq" {
  name = "log-distributor-dlq"

  message_retention_seconds = 1209600  # 14 days
  kms_master_key_id        = "alias/aws/sqs"

  tags = {
    Name        = "log-distributor-dlq"
    Environment = "production"
    Purpose     = "multi-tenant-logging"
  }
}

# Lambda alias for deployment management
resource "aws_lambda_alias" "log_distributor_live" {
  name             = "LIVE"
  description      = "Live version of log distributor"
  function_name    = aws_lambda_function.log_distributor.function_name
  function_version = "$LATEST"

  # Routing configuration for blue/green deployments
  dynamic "routing_config" {
    for_each = var.enable_lambda_canary ? [1] : []
    content {
      additional_version_weights = {
        (var.lambda_canary_version) = var.lambda_canary_weight
      }
    }
  }
}

# CloudWatch alarms for Lambda monitoring
resource "aws_cloudwatch_metric_alarm" "lambda_errors" {
  alarm_name          = "log-distributor-errors"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = "2"
  metric_name         = "Errors"
  namespace           = "AWS/Lambda"
  period              = "300"
  statistic           = "Sum"
  threshold           = "5"
  alarm_description   = "This metric monitors Lambda function errors"
  alarm_actions       = [aws_sns_topic.alerts.arn]
  ok_actions          = [aws_sns_topic.alerts.arn]

  dimensions = {
    FunctionName = aws_lambda_function.log_distributor.function_name
  }

  tags = {
    Name        = "log-distributor-errors"
    Environment = "production"
  }
}

resource "aws_cloudwatch_metric_alarm" "lambda_duration" {
  alarm_name          = "log-distributor-duration"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = "2"
  metric_name         = "Duration"
  namespace           = "AWS/Lambda"
  period              = "300"
  statistic           = "Average"
  threshold           = "300000"  # 5 minutes
  alarm_description   = "This metric monitors Lambda function duration"
  alarm_actions       = [aws_sns_topic.alerts.arn]

  dimensions = {
    FunctionName = aws_lambda_function.log_distributor.function_name
  }

  tags = {
    Name        = "log-distributor-duration"
    Environment = "production"
  }
}

resource "aws_cloudwatch_metric_alarm" "lambda_throttles" {
  alarm_name          = "log-distributor-throttles"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = "2"
  metric_name         = "Throttles"
  namespace           = "AWS/Lambda"
  period              = "300"
  statistic           = "Sum"
  threshold           = "0"
  alarm_description   = "This metric monitors Lambda function throttles"
  alarm_actions       = [aws_sns_topic.alerts.arn]

  dimensions = {
    FunctionName = aws_lambda_function.log_distributor.function_name
  }

  tags = {
    Name        = "log-distributor-throttles"
    Environment = "production"
  }
}

# Lambda insights for enhanced monitoring (optional)
resource "aws_lambda_layer_version" "lambda_insights" {
  count           = var.enable_lambda_insights ? 1 : 0
  filename        = "lambda-insights-extension.zip"
  layer_name      = "lambda-insights"
  description     = "CloudWatch Lambda Insights extension"
  
  compatible_runtimes = ["python3.11"]
  
  source_code_hash = filebase64sha256("lambda-insights-extension.zip")
}

# X-Ray tracing configuration
resource "aws_lambda_function_event_invoke_config" "log_distributor" {
  function_name = aws_lambda_function.log_distributor.function_name

  destination_config {
    on_failure {
      destination = aws_sqs_queue.lambda_dlq.arn
    }
    on_success {
      destination = aws_sns_topic.log_delivery_success.arn
    }
  }

  maximum_event_age_in_seconds = 3600  # 1 hour
  maximum_retry_attempts       = 2
}

# SNS topic for successful log delivery notifications (optional)
resource "aws_sns_topic" "log_delivery_success" {
  name = "log-delivery-success"
  
  kms_master_key_id = "alias/aws/sns"

  tags = {
    Name        = "log-delivery-success"
    Environment = "production"
    Purpose     = "multi-tenant-logging"
  }
}

# Lambda function for DLQ processing (optional)
resource "aws_lambda_function" "dlq_processor" {
  count            = var.enable_dlq_processor ? 1 : 0
  filename         = "dlq_processor.zip"
  function_name    = "log-distributor-dlq-processor"
  role            = aws_iam_role.dlq_processor_role[0].arn
  handler         = "dlq_processor.lambda_handler"
  runtime         = "python3.11"
  timeout         = 300
  memory_size     = 512

  environment {
    variables = {
      ALERT_SNS_TOPIC = aws_sns_topic.alerts.arn
      RETRY_QUEUE_URL = aws_sqs_queue.log_delivery.id
    }
  }

  tags = {
    Name        = "dlq-processor"
    Environment = "production"
    Purpose     = "multi-tenant-logging"
  }
}

# IAM role for DLQ processor
resource "aws_iam_role" "dlq_processor_role" {
  count = var.enable_dlq_processor ? 1 : 0
  name  = "DLQProcessorRole"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "lambda.amazonaws.com"
        }
      }
    ]
  })

  tags = {
    Name        = "DLQProcessorRole"
    Environment = "production"
    Purpose     = "multi-tenant-logging"
  }
}

# Attach basic execution role for DLQ processor
resource "aws_iam_role_policy_attachment" "dlq_processor_basic" {
  count      = var.enable_dlq_processor ? 1 : 0
  role       = aws_iam_role.dlq_processor_role[0].name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}