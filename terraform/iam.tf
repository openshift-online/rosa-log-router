# IAM role for Kinesis Data Firehose
resource "aws_iam_role" "firehose_role" {
  name = "FirehoseDeliveryRole"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "firehose.amazonaws.com"
        }
      }
    ]
  })

  tags = {
    Name        = "FirehoseDeliveryRole"
    Environment = "production"
    Purpose     = "multi-tenant-logging"
  }
}

# IAM policy for Firehose to access S3
resource "aws_iam_role_policy" "firehose_s3_policy" {
  name = "FirehoseDeliveryRoleS3Policy"
  role = aws_iam_role.firehose_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "s3:AbortMultipartUpload",
          "s3:GetBucketLocation",
          "s3:GetObject",
          "s3:ListBucket",
          "s3:ListBucketMultipartUploads",
          "s3:PutObject"
        ]
        Resource = [
          aws_s3_bucket.central_logging.arn,
          "${aws_s3_bucket.central_logging.arn}/*",
          aws_s3_bucket.central_logging_backup.arn,
          "${aws_s3_bucket.central_logging_backup.arn}/*"
        ]
      }
    ]
  })
}

# IAM policy for Firehose to access Glue
resource "aws_iam_role_policy" "firehose_glue_policy" {
  name = "FirehoseDeliveryRoleGluePolicy"
  role = aws_iam_role.firehose_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "glue:GetTable",
          "glue:GetTableVersion",
          "glue:GetTableVersions"
        ]
        Resource = [
          "arn:aws:glue:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:catalog",
          "arn:aws:glue:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:database/${aws_glue_catalog_database.central_logging.name}",
          "arn:aws:glue:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:table/${aws_glue_catalog_database.central_logging.name}/${aws_glue_catalog_table.central_logging.name}"
        ]
      }
    ]
  })
}

# Central log distribution role for cross-account access
resource "aws_iam_role" "central_log_distribution_role" {
  name = "CentralLogDistributionRole"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          AWS = aws_iam_role.log_distributor_role.arn
        }
      }
    ]
  })

  tags = {
    Name        = "CentralLogDistributionRole"
    Environment = "production"
    Purpose     = "multi-tenant-logging"
    Role        = "log-distribution"
  }
}

# IAM policy for central log distribution role
resource "aws_iam_role_policy" "central_log_distribution_policy" {
  name = "CentralLogDistributionPolicy"
  role = aws_iam_role.central_log_distribution_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "sts:AssumeRole",
          "sts:TagSession"
        ]
        Resource = "*"
        Condition = {
          StringEquals = {
            "aws:RequestedRegion" = data.aws_region.current.name
          }
          StringLike = {
            "aws:ResourceTag/Purpose" = "CrossAccountLogDelivery"
          }
        }
      }
    ]
  })
}

# IAM role for Lambda log distributor
resource "aws_iam_role" "log_distributor_role" {
  name = "LogDistributorRole"

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
    Name        = "LogDistributorRole"
    Environment = "production"
    Purpose     = "multi-tenant-logging"
  }
}

# Attach basic Lambda execution policy
resource "aws_iam_role_policy_attachment" "log_distributor_basic" {
  role       = aws_iam_role.log_distributor_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

# IAM policy for Lambda to access required services
resource "aws_iam_role_policy" "log_distributor_policy" {
  name = "LogDistributorPolicy"
  role = aws_iam_role.log_distributor_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "sqs:ReceiveMessage",
          "sqs:DeleteMessage",
          "sqs:GetQueueAttributes"
        ]
        Resource = aws_sqs_queue.log_delivery.arn
      },
      {
        Effect = "Allow"
        Action = [
          "s3:GetObject"
        ]
        Resource = "${aws_s3_bucket.central_logging.arn}/*"
      },
      {
        Effect = "Allow"
        Action = [
          "dynamodb:GetItem",
          "dynamodb:Query"
        ]
        Resource = aws_dynamodb_table.tenant_configurations.arn
      },
      {
        Effect = "Allow"
        Action = [
          "sts:AssumeRole",
          "sts:TagSession"
        ]
        Resource = aws_iam_role.central_log_distribution_role.arn
        Condition = {
          StringEquals = {
            "aws:RequestedRegion" = data.aws_region.current.name
          }
        }
      }
    ]
  })
}

# IAM role for Vector in EKS
resource "aws_iam_role" "vector_logs_role" {
  name = "VectorLogsRole"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          Federated = "arn:aws:iam::${data.aws_caller_identity.current.account_id}:oidc-provider/${var.eks_oidc_issuer}"
        }
        Action = "sts:AssumeRoleWithWebIdentity"
        Condition = {
          StringEquals = {
            "${var.eks_oidc_issuer}:sub" = "system:serviceaccount:logging:vector-logs"
            "${var.eks_oidc_issuer}:aud" = "sts.amazonaws.com"
          }
        }
      }
    ]
  })

  tags = {
    Name        = "VectorLogsRole"
    Environment = "production"
    Purpose     = "multi-tenant-logging"
  }
}

# IAM policy for Vector to access Kinesis Firehose
resource "aws_iam_role_policy" "vector_firehose_policy" {
  name = "VectorFirehosePolicy"
  role = aws_iam_role.vector_logs_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "firehose:PutRecord",
          "firehose:PutRecordBatch"
        ]
        Resource = aws_kinesis_firehose_delivery_stream.central_logging.arn
      }
    ]
  })
}

# Data sources
data "aws_caller_identity" "current" {}
data "aws_region" "current" {}