# SNS topic for log delivery hub (hub and spoke pattern)
resource "aws_sns_topic" "log_delivery_hub" {
  name = "log-delivery-hub"

  # Enable server-side encryption
  kms_master_key_id = "alias/aws/sns"

  tags = {
    Name        = "log-delivery-hub"
    Environment = "production"
    Purpose     = "multi-tenant-logging"
  }
}

# SNS topic policy to allow S3 to publish messages
resource "aws_sns_topic_policy" "log_delivery_hub" {
  arn = aws_sns_topic.log_delivery_hub.arn

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "AllowS3Publish"
        Effect = "Allow"
        Principal = {
          Service = "s3.amazonaws.com"
        }
        Action = "SNS:Publish"
        Resource = aws_sns_topic.log_delivery_hub.arn
        Condition = {
          StringEquals = {
            "aws:SourceAccount" = data.aws_caller_identity.current.account_id
          }
          ArnEquals = {
            "aws:SourceArn" = aws_s3_bucket.central_logging.arn
          }
        }
      }
    ]
  })
}

# SQS queue for log delivery processing
resource "aws_sqs_queue" "log_delivery" {
  name = "log-delivery-queue"

  # Message retention period (14 days)
  message_retention_seconds = 1209600

  # Visibility timeout (6 times the Lambda timeout)
  visibility_timeout_seconds = 900

  # Receive wait time for long polling
  receive_wait_time_seconds = 20

  # Enable server-side encryption
  kms_master_key_id = "alias/aws/sqs"

  # Redrive policy for dead letter queue
  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.log_delivery_dlq.arn
    maxReceiveCount     = 3
  })

  tags = {
    Name        = "log-delivery-queue"
    Environment = "production"
    Purpose     = "multi-tenant-logging"
  }
}

# Dead Letter Queue for failed messages
resource "aws_sqs_queue" "log_delivery_dlq" {
  name = "log-delivery-dlq"

  # Longer retention for DLQ messages (14 days)
  message_retention_seconds = 1209600

  # Enable server-side encryption
  kms_master_key_id = "alias/aws/sqs"

  tags = {
    Name        = "log-delivery-dlq"
    Environment = "production"
    Purpose     = "multi-tenant-logging"
  }
}

# SQS queue policy
resource "aws_sqs_queue_policy" "log_delivery" {
  queue_url = aws_sqs_queue.log_delivery.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "AllowSNSMessages"
        Effect = "Allow"
        Principal = {
          Service = "sns.amazonaws.com"
        }
        Action = "sqs:SendMessage"
        Resource = aws_sqs_queue.log_delivery.arn
        Condition = {
          ArnEquals = {
            "aws:SourceArn" = aws_sns_topic.log_delivery_hub.arn
          }
        }
      }
    ]
  })
}

# SNS subscription: SNS topic to SQS queue
resource "aws_sns_topic_subscription" "log_delivery_queue" {
  topic_arn = aws_sns_topic.log_delivery_hub.arn
  protocol  = "sqs"
  endpoint  = aws_sqs_queue.log_delivery.arn

  # Filter policy to only receive S3 ObjectCreated events for log files
  filter_policy = jsonencode({
    eventSource = ["aws:s3"]
    eventName   = ["ObjectCreated:Put", "ObjectCreated:Post", "ObjectCreated:CompleteMultipartUpload"]
  })
}

# SNS topic for alerts and monitoring
resource "aws_sns_topic" "alerts" {
  name = "logging-pipeline-alerts"

  # Enable server-side encryption
  kms_master_key_id = "alias/aws/sns"

  tags = {
    Name        = "logging-pipeline-alerts"
    Environment = "production"
    Purpose     = "multi-tenant-logging"
  }
}

# Optional: SNS subscription for analytics (example of extensibility)
resource "aws_sns_topic_subscription" "analytics_queue" {
  count     = var.enable_analytics ? 1 : 0
  topic_arn = aws_sns_topic.log_delivery_hub.arn
  protocol  = "sqs"
  endpoint  = aws_sqs_queue.analytics_queue[0].arn

  filter_policy = jsonencode({
    eventSource = ["aws:s3"]
    eventName   = ["ObjectCreated:Put"]
  })
}

# Optional: SQS queue for analytics processing
resource "aws_sqs_queue" "analytics_queue" {
  count = var.enable_analytics ? 1 : 0
  name  = "log-analytics-queue"

  message_retention_seconds  = 1209600
  visibility_timeout_seconds = 300
  receive_wait_time_seconds  = 20
  kms_master_key_id         = "alias/aws/sqs"

  tags = {
    Name        = "log-analytics-queue"
    Environment = "production"
    Purpose     = "multi-tenant-logging-analytics"
  }
}

# CloudWatch alarms for SQS monitoring
resource "aws_cloudwatch_metric_alarm" "sqs_queue_depth" {
  alarm_name          = "log-delivery-queue-depth"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = "2"
  metric_name         = "ApproximateNumberOfVisibleMessages"
  namespace           = "AWS/SQS"
  period              = "300"
  statistic           = "Average"
  threshold           = "100"
  alarm_description   = "This metric monitors SQS queue depth"
  alarm_actions       = [aws_sns_topic.alerts.arn]
  ok_actions          = [aws_sns_topic.alerts.arn]

  dimensions = {
    QueueName = aws_sqs_queue.log_delivery.name
  }

  tags = {
    Name        = "log-delivery-queue-depth"
    Environment = "production"
  }
}

resource "aws_cloudwatch_metric_alarm" "sqs_age_of_oldest_message" {
  alarm_name          = "log-delivery-message-age"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = "2"
  metric_name         = "ApproximateAgeOfOldestMessage"
  namespace           = "AWS/SQS"
  period              = "300"
  statistic           = "Average"
  threshold           = "600"  # 10 minutes
  alarm_description   = "This metric monitors the age of the oldest message in the queue"
  alarm_actions       = [aws_sns_topic.alerts.arn]
  ok_actions          = [aws_sns_topic.alerts.arn]

  dimensions = {
    QueueName = aws_sqs_queue.log_delivery.name
  }

  tags = {
    Name        = "log-delivery-message-age"
    Environment = "production"
  }
}

resource "aws_cloudwatch_metric_alarm" "dlq_message_count" {
  alarm_name          = "log-delivery-dlq-messages"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = "1"
  metric_name         = "ApproximateNumberOfVisibleMessages"
  namespace           = "AWS/SQS"
  period              = "300"
  statistic           = "Average"
  threshold           = "0"
  alarm_description   = "This metric monitors messages in the dead letter queue"
  alarm_actions       = [aws_sns_topic.alerts.arn]

  dimensions = {
    QueueName = aws_sqs_queue.log_delivery_dlq.name
  }

  tags = {
    Name        = "log-delivery-dlq-messages"
    Environment = "production"
  }
}