# SQS infrastructure for multi-tenant log distribution pipeline

terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }
}

# Local values
locals {
  common_tags = merge(var.tags, {
    Project     = var.project_name
    Environment = var.environment
    ManagedBy   = "terraform"
    StackType   = "sqs-stack"
  })
}

# Dead Letter Queue for failed messages
resource "aws_sqs_queue" "log_delivery_dlq" {
  name                      = "${var.project_name}-${var.environment}-log-delivery-dlq"
  message_retention_seconds = 1209600 # 14 days

  tags = local.common_tags
}

# SQS queue for log delivery processing
resource "aws_sqs_queue" "log_delivery_queue" {
  name                       = "${var.project_name}-${var.environment}-log-delivery-queue"
  message_retention_seconds  = 1209600 # 14 days
  visibility_timeout_seconds = 900     # 15 minutes
  receive_wait_time_seconds  = 20      # Long polling

  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.log_delivery_dlq.arn
    maxReceiveCount     = 3
  })

  tags = local.common_tags
}

# SQS queue policy to allow SNS to send messages
resource "aws_sqs_queue_policy" "log_delivery_queue_policy" {
  queue_url = aws_sqs_queue.log_delivery_queue.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "AllowSNSMessages"
        Effect = "Allow"
        Principal = {
          Service = "sns.amazonaws.com"
        }
        Action   = "sqs:SendMessage"
        Resource = aws_sqs_queue.log_delivery_queue.arn
        Condition = {
          ArnEquals = {
            "aws:SourceArn" = var.log_delivery_topic_arn
          }
        }
      }
    ]
  })
}

# SNS subscription: SNS topic to SQS queue
resource "aws_sns_topic_subscription" "log_delivery_queue_subscription" {
  topic_arn = var.log_delivery_topic_arn
  protocol  = "sqs"
  endpoint  = aws_sqs_queue.log_delivery_queue.arn

  depends_on = [aws_sqs_queue_policy.log_delivery_queue_policy]
}