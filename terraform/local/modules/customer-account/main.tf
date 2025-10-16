# Customer account module - reusable for each customer
# Creates the customer-side resources: S3 bucket, IAM role

terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }
}

# S3 bucket for log delivery in customer account
resource "aws_s3_bucket" "log_delivery_bucket" {
  bucket = "${var.customer_name}-logs"

  # Remove tags for LocalStack compatibility (tagging causes timeouts)
  # tags   = var.tags
}

# Bucket policy allowing central role to write logs
resource "aws_s3_bucket_policy" "allow_central_role" {
  bucket = aws_s3_bucket.log_delivery_bucket.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "AllowCentralRoleWrite"
        Effect = "Allow"
        Principal = {
          AWS = "arn:aws:iam::${var.central_account_id}:role/ROSA-CentralLogDistributionRole-12345678"
        }
        Action = [
          "s3:PutObject",
          "s3:PutObjectAcl"
        ]
        Resource = "${aws_s3_bucket.log_delivery_bucket.arn}/*"
      }
    ]
  })
}

# IAM role that central account can assume (mirrors customer-log-distribution-role.yaml)
resource "aws_iam_role" "log_distribution_role" {
  name = "CustomerLogDistribution-us-east-1"

  # Trust policy: allow central account to assume this role
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Principal = {
        AWS = "arn:aws:iam::${var.central_account_id}:root"
      }
      Action = "sts:AssumeRole"
      Condition = {
        StringEquals = {
          "sts:ExternalId" = var.central_account_id
        }
      }
    }]
  })

  tags = var.tags
}

# Policy allowing writes to customer's S3 bucket
resource "aws_iam_role_policy" "s3_write_policy" {
  name = "S3WriteAccess"
  role = aws_iam_role.log_distribution_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "AllowS3Write"
        Effect = "Allow"
        Action = [
          "s3:PutObject",
          "s3:PutObjectAcl"
        ]
        Resource = "${aws_s3_bucket.log_delivery_bucket.arn}/*"
      },
      {
        Sid    = "AllowS3ListBucket"
        Effect = "Allow"
        Action = [
          "s3:ListBucket"
        ]
        Resource = aws_s3_bucket.log_delivery_bucket.arn
      }
    ]
  })
}

# Policy allowing writes to customer's CloudWatch Logs (optional)
resource "aws_iam_role_policy" "cloudwatch_write_policy" {
  name = "CloudWatchWriteAccess"
  role = aws_iam_role.log_distribution_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid    = "AllowCloudWatchLogs"
      Effect = "Allow"
      Action = [
        "logs:CreateLogGroup",
        "logs:CreateLogStream",
        "logs:PutLogEvents",
        "logs:DescribeLogStreams"
      ]
      Resource = "arn:aws:logs:*:${var.account_id}:log-group:/aws/logs/${var.customer_name}/*"
    }]
  })
}

# CloudWatch Log Group for the customer (optional)
resource "aws_cloudwatch_log_group" "customer_logs" {
  name              = "/aws/logs/${var.customer_name}/application"
  retention_in_days = 7
  tags              = var.tags
}
