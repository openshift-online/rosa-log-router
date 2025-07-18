# Outputs for the multi-tenant logging infrastructure

# Core Infrastructure Outputs
output "kinesis_firehose_stream_name" {
  description = "Name of the Kinesis Data Firehose stream"
  value       = aws_kinesis_firehose_delivery_stream.central_logging.name
}

output "kinesis_firehose_stream_arn" {
  description = "ARN of the Kinesis Data Firehose stream"
  value       = aws_kinesis_firehose_delivery_stream.central_logging.arn
}

output "central_logging_bucket_name" {
  description = "Name of the central logging S3 bucket"
  value       = aws_s3_bucket.central_logging.bucket
}

output "central_logging_bucket_arn" {
  description = "ARN of the central logging S3 bucket"
  value       = aws_s3_bucket.central_logging.arn
}

# SNS/SQS Outputs
output "log_delivery_hub_topic_arn" {
  description = "ARN of the SNS topic for log delivery hub"
  value       = aws_sns_topic.log_delivery_hub.arn
}

output "log_delivery_queue_url" {
  description = "URL of the SQS queue for log delivery"
  value       = aws_sqs_queue.log_delivery.id
}

output "log_delivery_queue_arn" {
  description = "ARN of the SQS queue for log delivery"
  value       = aws_sqs_queue.log_delivery.arn
}

output "log_delivery_dlq_url" {
  description = "URL of the DLQ for log delivery"
  value       = aws_sqs_queue.log_delivery_dlq.id
}

# Lambda Outputs
output "log_distributor_function_name" {
  description = "Name of the log distributor Lambda function"
  value       = aws_lambda_function.log_distributor.function_name
}

output "log_distributor_function_arn" {
  description = "ARN of the log distributor Lambda function"
  value       = aws_lambda_function.log_distributor.arn
}

output "log_distributor_role_arn" {
  description = "ARN of the log distributor Lambda execution role"
  value       = aws_iam_role.log_distributor_role.arn
}

# DynamoDB Outputs
output "tenant_config_table_name" {
  description = "Name of the tenant configuration DynamoDB table"
  value       = aws_dynamodb_table.tenant_configurations.name
}

output "tenant_config_table_arn" {
  description = "ARN of the tenant configuration DynamoDB table"
  value       = aws_dynamodb_table.tenant_configurations.arn
}

# IAM Outputs
output "vector_logs_role_arn" {
  description = "ARN of the Vector logs IAM role for EKS"
  value       = aws_iam_role.vector_logs_role.arn
}

output "firehose_role_arn" {
  description = "ARN of the Firehose delivery IAM role"
  value       = aws_iam_role.firehose_role.arn
}

# Monitoring Outputs
output "alerts_topic_arn" {
  description = "ARN of the SNS topic for alerts"
  value       = aws_sns_topic.alerts.arn
}

output "cloudwatch_dashboard_url" {
  description = "URL to the CloudWatch dashboard"
  value       = "https://${var.aws_region}.console.aws.amazon.com/cloudwatch/home?region=${var.aws_region}#dashboards:name=multi-tenant-logging"
}

# Glue Catalog Outputs
output "glue_database_name" {
  description = "Name of the Glue catalog database"
  value       = aws_glue_catalog_database.central_logging.name
}

output "glue_table_name" {
  description = "Name of the Glue catalog table"
  value       = aws_glue_catalog_table.central_logging.name
}

# Configuration Outputs for Customers
output "customer_onboarding_info" {
  description = "Information needed for customer onboarding"
  value = {
    central_log_distributor_role_arn = aws_iam_role.log_distributor_role.arn
    cloudformation_template_url      = "https://raw.githubusercontent.com/your-org/logloglog/main/cloudformation/customer-account-template.yaml"
    supported_regions               = [var.aws_region, var.backup_region]
    firehose_stream_name           = aws_kinesis_firehose_delivery_stream.central_logging.name
  }
}

# Vector Configuration Outputs
output "vector_configuration" {
  description = "Configuration parameters for Vector agents"
  value = {
    kinesis_stream_name = aws_kinesis_firehose_delivery_stream.central_logging.name
    aws_region         = var.aws_region
    iam_role_arn       = aws_iam_role.vector_logs_role.arn
  }
}

# Cost Monitoring Outputs
output "cost_allocation_tags" {
  description = "Tags for cost allocation and monitoring"
  value = {
    Project     = var.project_name
    Environment = var.environment
    CostCenter  = var.cost_center
  }
}

# Security Outputs
output "s3_bucket_encryption_status" {
  description = "Encryption status of S3 buckets"
  value = {
    central_logging_bucket = "AES256"
    backup_bucket         = "AES256"
  }
}

# Performance Metrics Outputs
output "performance_metrics" {
  description = "Key performance metrics and limits"
  value = {
    firehose_buffer_size_mb    = var.firehose_buffer_size_mb
    firehose_buffer_interval   = var.firehose_buffer_interval_seconds
    lambda_reserved_concurrency = var.lambda_reserved_concurrency
    lambda_timeout_seconds     = aws_lambda_function.log_distributor.timeout
    sqs_visibility_timeout     = aws_sqs_queue.log_delivery.visibility_timeout_seconds
  }
}

# Networking Outputs (if VPC is used)
output "vpc_endpoints" {
  description = "VPC endpoints for AWS services (if enabled)"
  value = var.enable_vpc_endpoints ? {
    s3_endpoint       = "vpce-s3-${var.aws_region}"
    dynamodb_endpoint = "vpce-dynamodb-${var.aws_region}"
    sns_endpoint      = "vpce-sns-${var.aws_region}"
    sqs_endpoint      = "vpce-sqs-${var.aws_region}"
  } : {}
}

# Analytics Outputs (if enabled)
output "analytics_configuration" {
  description = "Analytics pipeline configuration (if enabled)"
  value = var.enable_analytics ? {
    analytics_queue_url = aws_sqs_queue.analytics_queue[0].id
    analytics_queue_arn = aws_sqs_queue.analytics_queue[0].arn
  } : {}
}

# Backup and DR Outputs
output "backup_configuration" {
  description = "Backup and disaster recovery configuration"
  value = {
    s3_versioning_enabled = true
    cross_region_replication_enabled = var.enable_cross_region_replication
    backup_region = var.backup_region
    point_in_time_recovery_enabled = true
  }
}

# Documentation URLs
output "documentation_links" {
  description = "Links to relevant documentation and resources"
  value = {
    design_document = "https://github.com/your-org/logloglog/blob/main/DESIGN.md"
    runbook        = "https://github.com/your-org/logloglog/blob/main/docs/runbook.md"
    troubleshooting = "https://github.com/your-org/logloglog/blob/main/docs/troubleshooting.md"
    customer_guide = "https://github.com/your-org/logloglog/blob/main/docs/customer-onboarding.md"
  }
}

# Terraform State Information
output "terraform_state_info" {
  description = "Information about Terraform state management"
  value = {
    terraform_version = ">= 1.0"
    provider_versions = {
      aws = ">= 5.0"
    }
    state_backend_recommended = "S3 with DynamoDB locking"
  }
}