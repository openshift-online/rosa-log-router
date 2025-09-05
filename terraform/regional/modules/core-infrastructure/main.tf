# Core infrastructure for multi-tenant logging - S3, DynamoDB, KMS, and IAM

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
    Name        = "${var.project_name}-${var.environment}"
    Project     = var.project_name
    Environment = var.environment
    ManagedBy   = "terraform"
  })
}

# KMS Key for encryption (conditional)
resource "aws_kms_key" "logging_kms_key" {
  count                   = var.enable_s3_encryption ? 1 : 0
  description             = "KMS key for multi-tenant logging encryption"
  enable_key_rotation     = true
  deletion_window_in_days = 7

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "Enable IAM User Permissions"
        Effect = "Allow"
        Principal = {
          AWS = "arn:aws:iam::${data.aws_caller_identity.current.account_id}:root"
        }
        Action   = "kms:*"
        Resource = "*"
      },
      {
        Sid    = "Allow use of the key for S3"
        Effect = "Allow"
        Principal = {
          Service = "s3.amazonaws.com"
        }
        Action = [
          "kms:Decrypt",
          "kms:GenerateDataKey"
        ]
        Resource = "*"
      },
      {
        Sid    = "Allow use of the key for Lambda"
        Effect = "Allow"
        Principal = {
          Service = "lambda.amazonaws.com"
        }
        Action = [
          "kms:Decrypt",
          "kms:GenerateDataKey"
        ]
        Resource = "*"
      }
    ]
  })

  tags = merge(local.common_tags, {
    Name = "${var.project_name}-${var.environment}-kms-key"
  })
}

resource "aws_kms_alias" "logging_kms_key_alias" {
  count         = var.enable_s3_encryption ? 1 : 0
  name          = "alias/${var.project_name}-${var.environment}-logging"
  target_key_id = aws_kms_key.logging_kms_key[0].key_id
}

# SNS topic for log delivery notifications
resource "aws_sns_topic" "log_delivery_topic" {
  name = "${var.project_name}-${var.environment}-log-delivery"
  tags = local.common_tags
}

# Central S3 Bucket for log storage
resource "aws_s3_bucket" "central_logging_bucket" {
  bucket = "${var.project_name}-${var.environment}-${data.aws_caller_identity.current.account_id}-${data.aws_region.current.name}"
  tags   = merge(local.common_tags, {
    Name = "${var.project_name}-${var.environment}-central-logging"
  })
}

resource "aws_s3_bucket_server_side_encryption_configuration" "central_logging_bucket_encryption" {
  bucket = aws_s3_bucket.central_logging_bucket.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm     = var.enable_s3_encryption ? "aws:kms" : "AES256"
      kms_master_key_id = var.enable_s3_encryption ? aws_kms_key.logging_kms_key[0].arn : null
    }
    bucket_key_enabled = var.enable_s3_encryption
  }
}

resource "aws_s3_bucket_public_access_block" "central_logging_bucket_pab" {
  bucket = aws_s3_bucket.central_logging_bucket.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_lifecycle_configuration" "central_logging_bucket_lifecycle" {
  bucket = aws_s3_bucket.central_logging_bucket.id

  rule {
    id     = "DeleteAfterNDays"
    status = "Enabled"

    filter {} # Empty filter applies to all objects

    expiration {
      days = var.s3_delete_after_days
    }
  }
}

# SNS topic policy to allow S3 to publish messages
resource "aws_sns_topic_policy" "log_delivery_topic_policy" {
  arn = aws_sns_topic.log_delivery_topic.arn

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "AllowS3Publish"
        Effect = "Allow"
        Principal = {
          Service = "s3.amazonaws.com"
        }
        Action   = "SNS:Publish"
        Resource = aws_sns_topic.log_delivery_topic.arn
        Condition = {
          StringEquals = {
            "aws:SourceAccount" = data.aws_caller_identity.current.account_id
          }
          ArnEquals = {
            "aws:SourceArn" = aws_s3_bucket.central_logging_bucket.arn
          }
        }
      }
    ]
  })
}

resource "aws_s3_bucket_notification" "central_logging_bucket_notification" {
  bucket = aws_s3_bucket.central_logging_bucket.id

  topic {
    topic_arn = aws_sns_topic.log_delivery_topic.arn
    events    = ["s3:ObjectCreated:*"]

    filter_suffix = ".gz"
  }

  depends_on = [aws_sns_topic_policy.log_delivery_topic_policy]
}

# S3 Access Log Group
resource "aws_cloudwatch_log_group" "s3_access_log_group" {
  name              = "/aws/s3/${var.project_name}-${var.environment}-access"
  retention_in_days = 30
  tags              = local.common_tags
}

# DynamoDB Table for tenant configurations
resource "aws_dynamodb_table" "tenant_config_table" {
  name           = "${var.project_name}-${var.environment}-tenant-configs"
  billing_mode   = "PAY_PER_REQUEST"
  hash_key       = "tenant_id"

  attribute {
    name = "tenant_id"
    type = "S"
  }

  attribute {
    name = "account_id"
    type = "S"
  }

  attribute {
    name = "status"
    type = "S"
  }

  attribute {
    name = "target_region"
    type = "S"
  }

  global_secondary_index {
    name     = "AccountIdIndex"
    hash_key = "account_id"
    projection_type = "ALL"
  }

  global_secondary_index {
    name     = "StatusIndex"
    hash_key = "status"
    projection_type = "ALL"
  }

  global_secondary_index {
    name     = "TargetRegionIndex"
    hash_key = "target_region"
    projection_type = "ALL"
  }

  point_in_time_recovery {
    enabled = true
  }

  server_side_encryption {
    enabled  = true
    kms_key_arn = var.enable_s3_encryption ? aws_kms_key.logging_kms_key[0].arn : null
  }

  tags = merge(local.common_tags, {
    Name = "${var.project_name}-${var.environment}-tenant-configs"
  })
}

# Central S3 Writer Role for cross-account S3 access
resource "aws_iam_role" "central_s3_writer_role" {
  name = "${var.project_name}-${var.environment}-central-s3-writer-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          AWS = "arn:aws:iam::${data.aws_caller_identity.current.account_id}:root"
        }
        Action = "sts:AssumeRole"
      }
    ]
  })

  tags = local.common_tags
}

resource "aws_iam_role_policy" "central_s3_writer_policy" {
  name = "S3WriterPolicy"
  role = aws_iam_role.central_s3_writer_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "s3:PutObject",
          "s3:PutObjectAcl"
        ]
        Resource = "${aws_s3_bucket.central_logging_bucket.arn}/*"
      },
      {
        Effect = "Allow"
        Action = [
          "s3:ListBucket",
          "s3:GetBucketLocation"
        ]
        Resource = aws_s3_bucket.central_logging_bucket.arn
      },
      {
        Effect = "Allow"
        Action = [
          "kms:Decrypt",
          "kms:GenerateDataKey"
        ]
        Resource = var.enable_s3_encryption ? aws_kms_key.logging_kms_key[0].arn : "*"
        Condition = {
          StringEquals = {
            "kms:ViaService" = "s3.${data.aws_region.current.name}.amazonaws.com"
          }
        }
      }
    ]
  })
}

# Managed Policy for Vector agents to assume S3 writer role
resource "aws_iam_policy" "vector_assume_role_policy" {
  name        = "${var.project_name}-${var.environment}-vector-assume-role-policy"
  description = "Policy allowing Vector agents to assume the central S3 writer role"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = "sts:AssumeRole"
        Resource = aws_iam_role.central_s3_writer_role.arn
      }
    ]
  })
}

# Regional IAM Role for accessing regional resources
resource "aws_iam_role" "regional_log_processor_role" {
  name = "${var.project_name}-${var.environment}-regional-processor-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          Service = "lambda.amazonaws.com"
        }
        Action = "sts:AssumeRole"
      },
      {
        Effect = "Allow"
        Principal = {
          AWS = var.central_log_distribution_role_arn
        }
        Action = "sts:AssumeRole"
      }
    ]
  })

  tags = local.common_tags
}

resource "aws_iam_role_policy_attachment" "regional_processor_basic" {
  role       = aws_iam_role.regional_log_processor_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_role_policy_attachment" "regional_processor_sqs" {
  role       = aws_iam_role.regional_log_processor_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaSQSQueueExecutionRole"
}

resource "aws_iam_role_policy" "regional_processor_policy" {
  name = "RegionalProcessorPolicy"
  role = aws_iam_role.regional_log_processor_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "dynamodb:GetItem",
          "dynamodb:Query",
          "dynamodb:BatchGetItem"
        ]
        Resource = aws_dynamodb_table.tenant_config_table.arn
      },
      {
        Effect = "Allow"
        Action = "dynamodb:Query"
        Resource = "${aws_dynamodb_table.tenant_config_table.arn}/index/*"
      },
      {
        Effect = "Allow"
        Action = "s3:GetObject"
        Resource = "${aws_s3_bucket.central_logging_bucket.arn}/*"
      },
      {
        Effect = "Allow"
        Action = [
          "kms:Decrypt",
          "kms:GenerateDataKey"
        ]
        Resource = var.enable_s3_encryption ? aws_kms_key.logging_kms_key[0].arn : "*"
      },
      {
        Effect = "Allow"
        Action = [
          "xray:PutTraceSegments",
          "xray:PutTelemetryRecords"
        ]
        Resource = "*"
      }
    ]
  })
}